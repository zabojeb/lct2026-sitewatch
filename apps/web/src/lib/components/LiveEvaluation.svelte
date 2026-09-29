<script lang="ts">
  import { fly } from 'svelte/transition';
  import { sha256Hex, uid } from '$lib/browser-crypto';
  import type { ModelPrediction } from '$lib/model';
  import {
    framesForWindow,
    type EquipmentCode,
    type PlanScenario,
    type ScenarioFrame,
  } from '$lib/model/scenario';
  import { plural } from '$lib/site/format';

  const count = (n: number, one: string, few: string, many: string) =>
    `${n} ${plural(n, [one, few, many])}`;
  type RuleDraft = {
    equipment_class: EquipmentCode | '';
    expectation: 'required' | 'optional' | 'unexpected';
    min_count: number;
    max_count: string;
    min_confidence: number;
    persistence_frames: number;
    source: string;
  };
  type ManualCount = { equipment_class: EquipmentCode; count: number; source: string };
  type Frame = {
    id: string;
    camera_code: string;
    zone_code: string;
    captured_at: string;
    captured_at_source: string;
    image_sha256: string;
    model_version: string;
    detections: Array<{
      equipment_class: string | null;
      mapping_status: string;
      detector_score: number;
      classifier_score: number;
      bounding_box: ModelPrediction['detections'][number]['bounding_box'];
    }>;
    manual_counts: ManualCount[];
  };
  type Finding = {
    equipment_class: EquipmentCode;
    assessment: string;
    expectation: string;
    expected_min: number;
    expected_max: number | null;
    observed_count: number | null;
    rule_source: string;
    evidence_frame_ids: string[];
    evidence_sources: string[];
    explanation: string;
  };
  type Evaluation = {
    schema: string;
    status: 'insufficient_evidence' | 'review_required' | 'observed_consistency';
    findings: Finding[];
    unconfigured_observed: EquipmentCode[];
    schedule: {
      planned_percent_at_measurement: number;
      measured_percent: number;
      percentage_point_delta: number;
      variance_seconds: number;
      source: string;
    } | null;
    limitations: string[];
  };

  let {
    prediction,
    file,
    rulesStatus,
    scenario = null,
    sceneFrames = [],
  }: {
    prediction: ModelPrediction | null;
    file: File | null;
    rulesStatus: 'checking' | 'ready' | 'unavailable' | 'disabled';
    /** Ready stage, zone, camera and rules of the open demo scene, if it has one. */
    scenario?: PlanScenario | null;
    /** Every frame of the open scene with its model result and capture time. */
    sceneFrames?: ScenarioFrame[];
  } = $props();
  const assessmentLabels: Record<string, string> = {
    missing: 'нет в кадрах',
    below_minimum: 'меньше минимума',
    above_maximum: 'больше максимума',
    unexpected: 'не предусмотрена этапом',
    consistent: 'согласуется',
    insufficient_evidence: 'данных недостаточно',
  };
  /** Distinct evidence sources; the model hash is shown as its recognition mode. */
  const sourcesSummary = (sources: string[]) =>
    [
      ...new Set(
        sources.map((line) =>
          line.replace(/yolo-(\d+)-[0-9a-f]+\+convnext-[0-9a-f]+/, 'YOLO $1 + ConvNeXt'),
        ),
      ),
    ].join('; ');
  const recognisedSceneFrames = $derived(sceneFrames.filter((frame) => frame.prediction).length);
  let scenarioNote = $state('');
  const labels: Record<EquipmentCode, string> = {
    dump_truck: 'Самосвал',
    excavator: 'Экскаватор',
    road_roller: 'Каток',
    loader_crane: 'Кран-манипулятор',
    concrete_mixer: 'Автобетоносмеситель',
    bulldozer: 'Бульдозер',
    truck: 'Грузовик',
    mobile_crane: 'Автокран',
    tower_crane: 'Башенный кран',
    piling_rig: 'Буровая / сваебойная установка',
    concrete_pump: 'Бетононасос',
    bucket_loader: 'Ковшовый погрузчик',
  };
  const codes = Object.keys(labels) as EquipmentCode[];
  /** Emptied `type=number` inputs bind to null; treat it like an empty field, not zero. */
  const filled = (value: string | number | null | undefined) =>
    value !== '' && value !== undefined && value !== null;
  const wholeNumber = (value: unknown) => Number.isInteger(Number(value)) && Number(value) >= 0;
  let capturedAt = $state('');
  let captureSource = $state('');
  let frames = $state<Frame[]>([]);
  let selectedFrameId = $state('');
  let stageName = $state('');
  let zoneCode = $state('');
  let cameraCode = $state('');
  let plannedStart = $state('');
  let plannedEnd = $state('');
  let observable = $state(false);
  let coveragePercent = $state('');
  let coverageSource = $state('');
  let rules = $state<RuleDraft[]>([
    {
      equipment_class: '',
      expectation: 'required',
      min_count: 1,
      max_count: '',
      min_confidence: 0.5,
      persistence_frames: 3,
      source: '',
    },
  ]);
  let manualClass = $state<EquipmentCode>('excavator');
  let manualCount = $state('');
  let manualSource = $state('');
  let progressPercent = $state('');
  let progressAt = $state('');
  let progressSource = $state('');
  let busy = $state(false);
  let error = $state('');
  let evaluation = $state<Evaluation | null>(null);
  let evaluatedInput = $state<Record<string, unknown> | null>(null);
  let evaluatedKey = $state('');
  const currentKey = $derived(
    JSON.stringify({
      frames,
      stageName,
      zoneCode,
      cameraCode,
      plannedStart,
      plannedEnd,
      observable,
      coveragePercent,
      coverageSource,
      rules,
      progressPercent,
      progressAt,
      progressSource,
    }),
  );
  const currentEvaluation = $derived(evaluatedKey === currentKey ? evaluation : null);
  const selectedFrame = $derived(frames.find((frame) => frame.id === selectedFrameId));

  async function fillFromScenario() {
    if (!scenario || busy) return;
    busy = true;
    error = '';
    try {
      const { kept, tooClose, outside } = framesForWindow(sceneFrames);
      if (!kept.length) throw new Error('Сначала распознайте кадры сцены.');
      stageName = scenario.stage;
      zoneCode = scenario.zone;
      cameraCode = scenario.camera;
      plannedStart = scenario.plannedStart;
      plannedEnd = scenario.plannedEnd;
      observable = scenario.observable;
      coveragePercent = scenario.coverage ? String(scenario.coverage.percent) : '';
      coverageSource = scenario.coverage?.source ?? '';
      rules = scenario.rules.map((rule) => ({
        ...rule,
        max_count: rule.max_count === null ? '' : String(rule.max_count),
      }));
      captureSource = scenario.timeSource;
      frames = await Promise.all(
        kept.map(async (item) => ({
          id: uid(),
          camera_code: scenario.camera,
          zone_code: scenario.zone,
          captured_at: new Date(item.capturedAt!).toISOString(),
          captured_at_source: scenario.timeSource,
          image_sha256: await sha256Hex(await item.file!.arrayBuffer()),
          model_version: item.prediction!.model_version,
          detections: item.prediction!.detections.filter((detection) => detection.mapping_status === 'mapped').slice(0, 100).map((detection) => ({
            equipment_class: detection.equipment_class,
            mapping_status: detection.mapping_status,
            detector_score: detection.detector_score,
            classifier_score: detection.classifier_score,
            bounding_box: detection.bounding_box,
          })),
          manual_counts: [],
        })),
      );
      selectedFrameId = frames[0]?.id ?? '';
      evaluation = null;
      scenarioNote = [
        `В окне наблюдения — ${count(kept.length, 'кадр', 'кадра', 'кадров')} сцены.`,
        tooClose
          ? `${count(tooClose, 'кадр снят', 'кадра сняты', 'кадров сняты')} меньше чем через минуту после предыдущего и в окно не ${tooClose === 1 ? 'вошёл' : 'вошли'}: между кадрами окна должно быть от 1 до 60 минут.`
          : '',
        outside ? `Ещё ${count(outside, 'кадр', 'кадра', 'кадров')} — за пределами окна (разрыв больше часа или больше 20 кадров).` : '',
      ]
        .filter(Boolean)
        .join(' ');
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Не удалось заполнить проверку.';
    } finally {
      busy = false;
    }
  }

  /** `datetime-local` value in local time. */
  function localInput(date: Date) {
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  async function fillAndCheck() {
    await fillFromScenario();
    if (!error && frames.length) await evaluate();
  }

  async function addFrame() {
    if (!prediction || !file || busy) return;
    error = '';
    try {
      if (frames.length && frames[0].model_version !== prediction.model_version) {
        throw new Error('В окне уже есть кадры другого режима. Очистите окно перед сменой режима.');
      }
      if (!zoneCode.trim() || !cameraCode.trim()) {
        throw new Error('Перед добавлением кадра укажите код зоны и камеры.');
      }
      const time = new Date(capturedAt);
      if (Number.isNaN(time.getTime()) || !captureSource.trim()) {
        throw new Error('Укажите время кадра и его источник.');
      }
      const neighbours = frames.map((frame) => Math.abs(Date.parse(frame.captured_at) - time.getTime()));
      if (neighbours.some((gap) => gap < 60_000)) {
        throw new Error('Кадры окна должны быть сняты с интервалом от 1 до 60 минут: этот слишком близко к уже добавленному.');
      }
      if (neighbours.length && Math.min(...neighbours) > 60 * 60_000) {
        throw new Error('Между кадрами окна должно быть не больше 60 минут: этот кадр слишком далеко от остальных.');
      }
      const image_sha256 = await sha256Hex(await file.arrayBuffer());
      if (frames.some((frame) => frame.image_sha256 === image_sha256)) {
        throw new Error(
          'Этот файл уже добавлен. Повторный кадр не считается новым свидетельством.',
        );
      }
      if (frames.length >= 20) throw new Error('Окно ограничено 20 кадрами.');
      const frame: Frame = {
        id: uid(),
        camera_code: cameraCode.trim(),
        zone_code: zoneCode.trim(),
        captured_at: time.toISOString(),
        captured_at_source: captureSource.trim(),
        image_sha256,
        model_version: prediction.model_version,
        detections: prediction.detections.filter((detection) => detection.mapping_status === 'mapped').slice(0, 100).map((detection) => ({
          equipment_class: detection.equipment_class,
          mapping_status: detection.mapping_status,
          detector_score: detection.detector_score,
          classifier_score: detection.classifier_score,
          bounding_box: detection.bounding_box,
        })),
        manual_counts: [],
      };
      frames = [...frames, frame].sort((left, right) =>
        left.captured_at.localeCompare(right.captured_at),
      );
      selectedFrameId = frame.id;
      capturedAt = localInput(new Date(time.getTime() + 5 * 60_000));
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Не удалось добавить кадр.';
    }
  }

  function removeFrame(id: string) {
    frames = frames.filter((frame) => frame.id !== id);
    if (selectedFrameId === id) selectedFrameId = frames[0]?.id ?? '';
  }

  function saveManualCount() {
    if (
      !selectedFrame ||
      !manualSource.trim() ||
      !/^\d+$/.test(manualCount) ||
      Number(manualCount) > 100
    ) {
      error = 'Для ручного количества нужны целое число 0–100 и источник.';
      return;
    }
    frames = frames.map((frame) =>
      frame.id === selectedFrameId
        ? {
            ...frame,
            manual_counts: [
              ...frame.manual_counts.filter((item) => item.equipment_class !== manualClass),
              {
                equipment_class: manualClass,
                count: Number(manualCount),
                source: manualSource.trim(),
              },
            ],
          }
        : frame,
    );
    error = '';
  }

  async function evaluate() {
    if (busy || !frames.length || rulesStatus !== 'ready') return;
    error = '';
    busy = true;
    try {
      if (!stageName.trim() || !zoneCode.trim() || !cameraCode.trim()) {
        throw new Error('Укажите название этапа, код зоны и код камеры.');
      }
      if (
        !plannedStart ||
        !plannedEnd ||
        !Number.isFinite(Date.parse(plannedStart)) ||
        !Number.isFinite(Date.parse(plannedEnd))
      ) {
        throw new Error('Укажите обе плановые даты этапа.');
      }
      if (new Date(plannedEnd) <= new Date(plannedStart))
        throw new Error('Конец этапа должен быть позже начала.');
      if (
        frames.some(
          (frame) => frame.zone_code !== zoneCode.trim() || frame.camera_code !== cameraCode.trim(),
        )
      ) {
        throw new Error('Кадры должны относиться к указанным зоне и камере.');
      }
      if (rules.some((rule) => !rule.equipment_class || !rule.source.trim())) {
        throw new Error('Для каждого правила выберите класс техники и укажите документ-источник.');
      }
      if (new Set(rules.map((rule) => rule.equipment_class)).size !== rules.length) {
        throw new Error('Для одного класса техники можно задать только одно правило.');
      }
      if (
        rules.some(
          (rule) =>
            !wholeNumber(rule.persistence_frames) ||
            Number(rule.persistence_frames) < 1 ||
            (rule.expectation === 'required' &&
              (!wholeNumber(rule.min_count) || Number(rule.min_count) < 1)) ||
            (filled(rule.max_count) && !wholeNumber(rule.max_count)) ||
            !filled(rule.min_confidence),
        )
      ) {
        throw new Error(
          'В правилах нужны целые числа: минимум не меньше 1 для обязательной техники, кадров для вывода — от 1.',
        );
      }
      if (filled(coveragePercent) && !coverageSource.trim()) {
        throw new Error('Укажите источник оценки обзора зоны.');
      }
      if (filled(progressPercent) && (!progressAt || !progressSource.trim())) {
        throw new Error('Для замера готовности укажите время и источник.');
      }
      const request = {
        stage: {
          name: stageName.trim(),
          zone_code: zoneCode.trim(),
          planned_start: new Date(plannedStart).toISOString(),
          planned_end: new Date(plannedEnd).toISOString(),
          observable_from_camera: observable,
          rules: rules.map((rule) => ({
            equipment_class: rule.equipment_class,
            expectation: rule.expectation,
            min_count: rule.expectation === 'required' ? Number(rule.min_count) : 0,
            max_count:
              rule.expectation === 'unexpected'
                ? 0
                : !filled(rule.max_count)
                  ? null
                  : Number(rule.max_count),
            min_confidence: Number(rule.min_confidence),
            persistence_frames: Number(rule.persistence_frames),
            source: rule.source,
          })),
        },
        coverage: !filled(coveragePercent)
          ? null
          : { percent: Number(coveragePercent), source: coverageSource },
        frames,
        progress: !filled(progressPercent)
          ? null
          : {
              measured_at: new Date(progressAt).toISOString(),
              percent: Number(progressPercent),
              source: progressSource,
            },
      };
      const key = currentKey;
      const response = await fetch('/api/model/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error ?? 'Сервис правил отклонил данные.');
      if (result.schema !== 'sitewatch.evaluation.preview.v1')
        throw new Error('Несовместимый ответ сервиса правил.');
      evaluation = result as Evaluation;
      evaluatedInput = request;
      evaluatedKey = key;
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Не удалось проверить правила.';
    } finally {
      busy = false;
    }
  }

  function exportPreview() {
    if (!currentEvaluation || !evaluatedInput) return;
    const report = {
      schema: 'sitewatch.operator-preview.v1',
      exported_at: new Date().toISOString(),
      input: evaluatedInput,
      result: currentEvaluation,
      note: 'Предпросмотр по введённым оператором данным. Не является сохранённым алертом или актом работ. Исходные изображения не включены.',
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `sitewatch-preview-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
</script>

<section class="live-evaluation" aria-labelledby="evaluation-title">
  <div class="heading">
    <div>
      <h2 id="evaluation-title">Проверка по плану</h2>
      <p>
        Сервис правил сверяет технику на кадрах с этапом плана. Вывод будет, только если зона видна
        с камеры (обзор от 80 %) и в окне хватает кадров одной камеры с шагом 1–60 минут.
      </p>
    </div>
    <span class="frame-total">{frames.length} <small>{count(frames.length, 'кадр', 'кадра', 'кадров').split(' ')[1]} в окне</small></span>
  </div>
  {#if scenario}
    <div class="scenario">
      <div>
        <strong>{scenario.stage}</strong>
        <span
          >{scenario.camera} · {count(scenario.rules.length, 'правило', 'правила', 'правил')} с источниками:
          {scenario.rules.map((rule) => labels[rule.equipment_class]).join(' + ')}</span
        >
      </div>
      <button class="button primary" disabled={busy || !recognisedSceneFrames || rulesStatus !== 'ready'} onclick={fillAndCheck}
        >{!recognisedSceneFrames ? 'Сначала распознайте кадры' : busy ? 'Проверяем…' : 'Заполнить и проверить'}</button
      >
    </div>
    {#if scenarioNote}<p class="scenario-note" role="status">{scenarioNote}</p>{/if}
  {/if}
  {#if rulesStatus === 'unavailable' || rulesStatus === 'disabled'}
    <p class="evaluation-error" role="status">
      Сервис правил {rulesStatus === 'disabled' ? 'не включён' : 'не отвечает'}: проверка по плану
      недоступна.
    </p>
  {/if}
  {#if error}<p class="evaluation-error" role="alert">{error}</p>{/if}
  {#if currentEvaluation}
    <div class="evaluation-result" aria-live="polite" in:fly={{ y: 16, duration: 280 }}>
      <div class="result-head">
        <span
          >РЕЗУЛЬТАТ / {currentEvaluation.status === 'review_required'
            ? 'НУЖНА ПРОВЕРКА'
            : currentEvaluation.status === 'observed_consistency'
              ? 'НАБЛЮДАЕМОЕ СОГЛАСУЕТСЯ'
              : 'НЕДОСТАТОЧНО ДАННЫХ'}</span
        ><strong
          >{count(currentEvaluation.findings.length, 'правило', 'правила', 'правил')}</strong
        >
      </div>
      <div class="result-list">
        {#each currentEvaluation.findings as finding}<article
            class:flag={['missing', 'below_minimum', 'above_maximum', 'unexpected'].includes(
              finding.assessment,
            )}
          >
            <div>
              <strong>{labels[finding.equipment_class]}</strong><span
                >{assessmentLabels[finding.assessment] ?? finding.assessment}</span
              >
            </div>
            <p>{finding.explanation}</p>
            <small
              >План: минимум {finding.expected_min}{finding.expected_max === null
                ? ''
                : ` · максимум ${finding.expected_max}`} / наблюдение: {finding.observed_count ??
                'нет данных'} · правило: {finding.rule_source} · кадры: {finding.evidence_frame_ids
                .length}</small
            >
            <small class="evidence-sources">{sourcesSummary(finding.evidence_sources)}</small>
          </article>{/each}
      </div>
      {#if currentEvaluation.unconfigured_observed.length}<p class="unconfigured">
          В кадрах есть техника вне перечня этапа: {currentEvaluation.unconfigured_observed
            .map((code) => labels[code])
            .join(', ')}. Проверьте соседний этап и добавьте правило с источником — это ещё не
          отклонение.
        </p>{/if}
      {#if currentEvaluation.schedule}<div class="schedule-result">
          <strong
            >{currentEvaluation.schedule.variance_seconds >= 0 ? '+' : '−'}{(
              Math.abs(currentEvaluation.schedule.variance_seconds) / 3600
            ).toFixed(1)} ч</strong
          >
          <div>
            расхождение с линейным планом по ручному замеру {currentEvaluation.schedule
              .measured_percent}%<small
              >{currentEvaluation.schedule.source} · положительное значение — отставание</small
            >
          </div>
        </div>{/if}
      <ul>
        {#each currentEvaluation.limitations as limitation}<li>{limitation}</li>{/each}
      </ul>
      <div class="export-row">
        <button class="button secondary" onclick={exportPreview}
          >Экспортировать проверку в JSON</button
        >
        <span>Содержит входные данные, источники и вывод. Без исходных снимков.</span>
      </div>
    </div>
  {/if}
  <details class="manual" open={!scenario}>
    <summary>{scenario ? 'Настроить вручную' : 'Этап, правила и кадры'}</summary>
  <div class="columns">
    <div class="column">
      <h3>01. Контекст этапа</h3>
      <div class="fields two">
        <label
          >Название этапа<input
            bind:value={stageName}
            maxlength="200"
            placeholder="По вашему графику работ"
          /></label
        >
        <label
          >Код зоны<input
            bind:value={zoneCode}
            maxlength="80"
            placeholder="Из вашего проекта"
            disabled={frames.length > 0}
          /></label
        >
        <label
          >Код камеры<input
            bind:value={cameraCode}
            maxlength="80"
            placeholder="Например, КАМ-04"
            disabled={frames.length > 0}
          /></label
        >
        <label class="check"
          ><input type="checkbox" bind:checked={observable} /> Зона видна с этой камеры</label
        >
        <label>Плановое начало<input type="datetime-local" bind:value={plannedStart} /></label>
        <label>Плановое завершение<input type="datetime-local" bind:value={plannedEnd} /></label>
        <label
          >Обзор зоны, % <input
            type="number"
            min="0"
            max="100"
            step="1"
            bind:value={coveragePercent}
            placeholder="Не подтверждён"
          /></label
        >
        <label
          >Источник оценки обзора<input
            bind:value={coverageSource}
            placeholder="Оператор / схема камеры"
          /></label
        >
      </div>
      <h3>02. Техника и основания</h3>
      <div class="rules">
        {#each rules as rule, index}
          <div class="rule">
            <div class="rule-head">
              <span>ПРАВИЛО {String(index + 1).padStart(2, '0')}</span><button
                aria-label="Удалить правило"
                disabled={rules.length === 1}
                onclick={() => (rules = rules.filter((_, at) => at !== index))}>×</button
              >
            </div>
            <div class="fields two">
              <label
                >Класс<select bind:value={rule.equipment_class}
                  ><option value="">Выберите технику</option>{#each codes as code}<option
                      value={code}>{labels[code]}</option
                    >{/each}</select
                ></label
              >
              <label
                >Ожидание<select bind:value={rule.expectation}
                  ><option value="required">Обязательная</option><option value="optional"
                    >Возможная</option
                  ><option value="unexpected">Неожиданная</option></select
                ></label
              >
              <label
                >Минимум<input
                  type="number"
                  min="0"
                  max="100"
                  bind:value={rule.min_count}
                  disabled={rule.expectation !== 'required'}
                /></label
              >
              <label
                >Максимум<input
                  type="number"
                  min="0"
                  max="100"
                  bind:value={rule.max_count}
                  disabled={rule.expectation === 'unexpected'}
                  placeholder="Без ограничения"
                /></label
              >
              <label
                >Мин. score<input
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  bind:value={rule.min_confidence}
                /></label
              >
              <label
                >Кадров для вывода<input
                  type="number"
                  min="1"
                  max="20"
                  bind:value={rule.persistence_frames}
                /></label
              >
              <label class="wide"
                >Источник правила<input
                  bind:value={rule.source}
                  maxlength="1000"
                  placeholder="ППР, ведомость механизации или решение инженера"
                /></label
              >
            </div>
          </div>
        {/each}
      </div>
      <button
        class="text-button"
        disabled={rules.length >= codes.length}
        onclick={() =>
          (rules = [
            ...rules,
            {
              equipment_class: '',
              expectation: 'required',
              min_count: 1,
              max_count: '',
              min_confidence: 0.5,
              persistence_frames: 3,
              source: '',
            },
          ])}>+ Добавить технику</button
      >
    </div>
    <div class="column evidence-column">
      <h3>03. Свидетельства и замеры</h3>
      <p class="hint">
        Переключайте кадры обработанной серии выше и добавляйте снимки одной камеры. Время между
        соседними кадрами для временного правила — 1–60 минут; источник времени обязателен.
      </p>
      <div class="fields two">
        <label>Время текущего кадра<input type="datetime-local" bind:value={capturedAt} /></label>
        <label
          >Источник времени<input
            bind:value={captureSource}
            placeholder="Метка камеры / EXIF / оператор"
          /></label
        >
      </div>
      <button class="add-frame" disabled={!prediction || !file || busy} onclick={addFrame}
        >+ Добавить результат модели в окно</button
      >
      {#if frames.length}
        <button class="clear-window" onclick={() => { frames = []; selectedFrameId = ''; evaluation = null; }}>
          Очистить окно наблюдений
        </button>
        <div class="timeline">
          {#each frames as frame, index}
            <div class="frame-row">
              <div>
                <strong
                  >{String(index + 1).padStart(2, '0')} / {new Date(
                    frame.captured_at,
                  ).toLocaleString('ru-RU')}</strong
                ><small
                  >{count(frame.detections.length, 'объект', 'объекта', 'объектов')} · {count(
                    frame.manual_counts.length,
                    'ручное уточнение',
                    'ручных уточнения',
                    'ручных уточнений',
                  )} · {frame.camera_code} / {frame.zone_code}</small
                >
              </div>
              <button aria-label={`Удалить кадр ${index + 1}`} onclick={() => removeFrame(frame.id)}
                >×</button
              >
            </div>
          {/each}
        </div>
        <div class="manual">
          <h4>Ручное уточнение количества</h4>
          <p class="hint">Сохраняется отдельно от результата модели, с обязательным источником.</p>
          <div class="fields two">
            <label
              >Кадр<select bind:value={selectedFrameId}
                >{#each frames as frame, index}<option value={frame.id}>Кадр {index + 1}</option
                  >{/each}</select
              ></label
            >
            <label
              >Техника<select bind:value={manualClass}
                >{#each codes as code}<option value={code}>{labels[code]}</option>{/each}</select
              ></label
            >
            <label
              >Количество<input type="number" min="0" max="100" bind:value={manualCount} /></label
            >
            <label
              >Источник<input bind:value={manualSource} placeholder="Подсчёт оператора" /></label
            >
          </div>
          <button class="text-button" onclick={saveManualCount}>Сохранить уточнение</button>
          {#if selectedFrame?.manual_counts.length}
            <div class="overrides">
              {#each selectedFrame.manual_counts as count}<span
                  >{labels[count.equipment_class]}: {count.count} · {count.source}
                  <button
                    aria-label={`Убрать уточнение ${labels[count.equipment_class]}`}
                    onclick={() =>
                      (frames = frames.map((frame) =>
                        frame.id === selectedFrameId
                          ? {
                              ...frame,
                              manual_counts: frame.manual_counts.filter(
                                (item) => item.equipment_class !== count.equipment_class,
                              ),
                            }
                          : frame,
                      ))}>×</button
                  ></span
                >{/each}
            </div>
          {/if}
        </div>
      {/if}
      <div class="progress">
        <h4>Готовность по ручному замеру <small>НЕ ОЦЕНКА ПО ФОТО</small></h4>
        <div class="fields two">
          <label
            >Выполнено, %<input
              type="number"
              min="0"
              max="100"
              step="0.1"
              bind:value={progressPercent}
              placeholder="Не измерено"
            /></label
          >
          <label>Время замера<input type="datetime-local" bind:value={progressAt} /></label>
          <label class="wide"
            >Источник замера<input
              bind:value={progressSource}
              placeholder="Акт / инженер / журнал работ"
            /></label
          >
        </div>
      </div>
    </div>
  </div>
  <div class="action-row">
    <div>
      <strong>Найденная техника — повод для проверки, а не нарушение.</strong><span
        >Проверку выполняет отдельный сервис правил; изображения ему не передаются.</span
      >
    </div>
    <button
      class="button primary"
      disabled={!frames.length || busy || rulesStatus !== 'ready'}
      onclick={evaluate}>{busy ? 'Проверяем…' : 'Проверить по плану'}</button
    >
  </div>
  </details>
</section>

<style>
  .scenario {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    margin: 0 0 16px;
    padding: 16px 18px;
    border: 1px solid var(--accent);
    border-radius: 12px;
    background: var(--accent-soft);
  }
  .scenario strong {
    display: block;
    font-size: 13px;
  }
  .scenario span {
    display: block;
    margin-top: 4px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.5;
  }
  .scenario .button {
    flex: none;
  }
  .manual {
    margin-top: 18px;
    border-top: 1px solid var(--line);
    padding-top: 14px;
  }
  .manual > summary {
    width: fit-content;
    cursor: pointer;
    color: var(--muted);
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 14px;
  }
  .manual > summary:hover {
    color: var(--text);
  }
  .scenario-note {
    margin: -10px 0 22px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.5;
  }
  @media (max-width: 720px) {
    .scenario {
      display: block;
    }
    .scenario .button {
      margin-top: 12px;
      width: 100%;
    }
  }
  .clear-window {
    margin-top: 10px;
    color: var(--muted);
    font-size: 11px;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .clear-window:hover { color: var(--text); }
  .export-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 14px;
    margin-top: 26px;
  }
  .export-row span {
    color: var(--muted);
    font-size: 11px;
    line-height: 1.5;
  }
  .live-evaluation {
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surface);
    padding: clamp(18px, 2.4vw, 32px);
  }
  .rule-head,
  .result-head {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    font:
      11px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    letter-spacing: 0.1em;
    color: var(--muted);
  }
  .heading {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 30px;
    padding: 0 0 20px;
  }
  h2 {
    margin: 0;
    font-size: clamp(30px, 3vw, 46px);
    letter-spacing: -0.06em;
    line-height: 1;
  }
  .heading p {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.6;
    max-width: 63ch;
    margin: 14px 0 0;
  }
  .frame-total {
    white-space: nowrap;
    font-size: 42px;
    line-height: 1;
    font-weight: 700;
    letter-spacing: -0.06em;
  }
  .frame-total small {
    display: block;
    margin-top: 8px;
    color: var(--muted);
    font:
      10px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    letter-spacing: 0.08em;
  }
  .columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    border: 1px solid var(--line);
  }
  .column {
    min-width: 0;
    padding: 28px;
  }
  .evidence-column {
    border-left: 1px solid var(--line);
  }
  h3 {
    font-size: 14px;
    margin: 0 0 18px;
    letter-spacing: -0.02em;
  }
  h3:not(:first-child) {
    border-top: 1px solid var(--line);
    padding-top: 26px;
    margin-top: 30px;
  }
  h4 {
    font-size: 13px;
    margin: 0 0 13px;
  }
  h4 small {
    font:
      9px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    color: var(--muted);
    letter-spacing: 0.08em;
    margin-left: 8px;
  }
  .fields {
    display: grid;
    gap: 12px;
  }
  .fields.two {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .fields label {
    display: grid;
    gap: 7px;
    color: var(--muted);
    font-size: 11px;
  }
  .fields .wide {
    grid-column: 1 / -1;
  }
  .fields input,
  .fields select {
    min-width: 0;
    width: 100%;
    border: 1px solid var(--line);
    background: var(--bg);
    color: var(--text);
    border-radius: 2px;
    padding: 10px 11px;
    font-size: 12px;
  }
  .fields input::placeholder {
    color: var(--muted);
    opacity: 0.8;
  }
  .fields .check {
    align-content: center;
    display: flex;
    align-items: center;
    gap: 9px;
    color: var(--text);
  }
  .fields .check input {
    width: auto;
  }
  .rules {
    display: grid;
    gap: 12px;
  }
  .rule {
    background: var(--bg);
    border: 1px solid var(--line);
    padding: 16px;
  }
  .rule-head {
    margin-bottom: 15px;
    align-items: center;
  }
  .rule-head button,
  .frame-row button,
  .overrides button {
    color: var(--muted);
    font-size: 20px;
    line-height: 1;
  }
  .rule-head button:hover,
  .frame-row button:hover,
  .overrides button:hover {
    color: var(--danger);
  }
  .text-button {
    color: var(--accent);
    font-size: 12px;
    font-weight: 700;
    margin-top: 14px;
    padding: 8px 0;
  }
  :global([data-theme='light']) .text-button {
    color: #4c622b;
  }
  .hint {
    color: var(--muted);
    font-size: 11px;
    line-height: 1.6;
    margin: -4px 0 16px;
  }
  .add-frame {
    width: 100%;
    text-align: left;
    margin: 15px 0 10px;
    border: 1px dashed var(--accent);
    color: var(--text);
    padding: 15px;
    font-size: 12px;
    font-weight: 700;
  }
  .add-frame:hover {
    background: var(--accent-soft);
  }
  .timeline {
    border-top: 1px solid var(--line);
  }
  .frame-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 1px solid var(--line);
    padding: 12px 0;
  }
  .frame-row strong,
  .frame-row small {
    display: block;
  }
  .frame-row strong {
    font-size: 11px;
  }
  .frame-row small {
    color: var(--muted);
    font-size: 10px;
    overflow-wrap: anywhere;
    margin-top: 4px;
  }
  .manual,
  .progress {
    border-top: 1px solid var(--line);
    margin-top: 22px;
    padding-top: 22px;
  }
  .overrides {
    display: grid;
    gap: 5px;
    margin-top: 11px;
    color: var(--muted);
    font-size: 11px;
  }
  .overrides button {
    font-size: 16px;
    vertical-align: middle;
  }
  .action-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 25px;
    border-top: 1px solid var(--line);
    margin-top: 28px;
    padding-top: 28px;
  }
  .action-row strong,
  .action-row span {
    display: block;
    font-size: 12px;
  }
  .action-row span {
    color: var(--muted);
    font-size: 11px;
    margin-top: 6px;
  }
  .action-row .button {
    white-space: nowrap;
  }
  .evaluation-error {
    color: var(--danger);
    font-size: 12px;
    margin: 16px 0 0;
  }
  .evaluation-result {
    margin-top: 16px;
    border: 1px solid var(--line);
    border-radius: 12px;
    overflow: hidden;
    background: var(--bg);
  }
  .result-head {
    padding: 18px 20px;
    border-bottom: 1px solid var(--line);
    color: var(--text);
  }
  .result-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .result-list article {
    padding: 20px;
    border-bottom: 1px solid var(--line);
    border-right: 1px solid var(--line);
  }
  .result-list article.flag {
    border-left: 3px solid var(--warning);
  }
  .result-list article div {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 12px;
  }
  .result-list article div span {
    color: var(--muted);
    font:
      10px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
  }
  .result-list article p {
    color: var(--muted);
    font-size: 11px;
    line-height: 1.55;
  }
  .result-list article small {
    color: var(--muted);
    font-size: 10px;
    line-height: 1.5;
  }
  .result-list article small.evidence-sources {
    display: block;
    margin-top: 8px;
    overflow-wrap: anywhere;
  }
  .unconfigured {
    margin: 0;
    padding: 18px 20px;
    border-bottom: 1px solid var(--line);
    color: var(--warning);
    font-size: 12px;
    line-height: 1.6;
  }
  .schedule-result {
    display: flex;
    align-items: center;
    gap: 17px;
    padding: 20px;
    border-bottom: 1px solid var(--line);
  }
  .schedule-result > strong {
    font-size: 26px;
    white-space: nowrap;
  }
  .schedule-result div {
    font-size: 12px;
  }
  .schedule-result small {
    display: block;
    color: var(--muted);
    font-size: 10px;
    margin-top: 5px;
  }
  .evaluation-result ul {
    margin: 0;
    padding: 17px 25px 20px 38px;
    color: var(--muted);
    font-size: 10px;
    line-height: 1.7;
  }
  @media (max-width: 900px) {
    .columns {
      grid-template-columns: 1fr;
    }
    .evidence-column {
      border-left: 0;
      border-top: 1px solid var(--line);
    }
  }
  @media (max-width: 600px) {
    .heading {
      align-items: start;
    }
    .frame-total {
      font-size: 32px;
    }
    .columns {
      margin: 0 -12px;
    }
    .column {
      padding: 18px;
    }
    .fields.two,
    .result-list {
      grid-template-columns: 1fr;
    }
    .action-row {
      align-items: stretch;
      flex-direction: column;
    }
    .action-row .button {
      width: 100%;
      justify-content: center;
    }
  }
</style>
