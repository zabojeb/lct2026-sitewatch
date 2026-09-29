<script lang="ts">
  import { onMount, tick } from 'svelte';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import UploadSimpleIcon from 'phosphor-svelte/lib/UploadSimpleIcon';
  import Brand from '$lib/components/Brand.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import LiveEvaluation from '$lib/components/LiveEvaluation.svelte';
  import VisualInterpretation from '$lib/components/VisualInterpretation.svelte';
  import { detectionLabel, rawClassLabels, type ModelPrediction } from '$lib/model';
  import { archivePreview, saveArchivedRun, updateArchivedVisual, type ArchivedVisual } from '$lib/model/archive';
  import { frames as frameCount, objects as objectCount } from '$lib/site/format';

  type DemoPhoto = { id: string; src: string; filename: string };
  type DemoScene = { id: string; title: string; context: string; date: string | null; photos: DemoPhoto[]; planSuggestion?: string };
  type SourceFrame = {
    id: string;
    name: string;
    src: string;
    file: File | null;
    prediction: ModelPrediction | null;
  };

  let file = $state<File | null>(null);
  let preview = $state('');
  let prediction = $state<ModelPrediction | null>(null);
  let selected = $state<number | null>(null);
  let busy = $state(false);
  let error = $state('');
  let status = $state<'checking' | 'ready' | 'unavailable' | 'disabled'>('checking');
  let rulesStatus = $state<'checking' | 'ready' | 'unavailable' | 'disabled'>('checking');
  let vlmStatus = $state<'ready' | 'disabled'>('disabled');
  let recognitionMode = $state<'640' | '960'>('640');
  let scenes = $state<DemoScene[]>([]);
  let sceneId = $state('');
  let frames = $state<SourceFrame[]>([]);
  let frameIndex = $state(0);
  let loadingScene = $state(false);
  let progress = $state(0);
  let showPlan = $state(false);
  let currentAbort: AbortController | null = null;
  let sourceGeneration = 0;
  let ownUrls: string[] = [];
  let archivedRunId = $state('');
  let archiveMessage = $state('');
  const visualReports = new Map<string, ArchivedVisual>();
  let folderInput: HTMLInputElement;
  const maxBytes = 12 * 1024 * 1024;
  const acceptedTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
  const mappedCount = $derived(
    prediction?.detections.filter((d) => d.mapping_status === 'mapped').length ?? 0,
  );
  const sceneInventory = $derived.by(() => {
    const inventory = new Map<string, { label: string; frames: number; maxOnFrame: number }>();
    for (const frame of frames) {
      if (!frame.prediction) continue;
      const counts = new Map<string, number>();
      for (const detection of frame.prediction.detections) {
        if (detection.mapping_status === 'ignored' || detection.mapping_status === 'low_confidence') continue;
        counts.set(detection.raw_class, (counts.get(detection.raw_class) ?? 0) + 1);
      }
      for (const [code, count] of counts) {
        const current = inventory.get(code) ?? { label: rawClassLabels[code] ?? code, frames: 0, maxOnFrame: 0 };
        current.frames += 1;
        current.maxOnFrame = Math.max(current.maxOnFrame, count);
        inventory.set(code, current);
      }
    }
    return [...inventory.values()].sort((a, b) => b.frames - a.frames || b.maxOnFrame - a.maxOnFrame);
  });

  async function refreshStatus() {
    try {
      const response = await fetch('/api/model/status', { cache: 'no-store' });
      const result = (await response.json()) as {
        status: typeof status;
        rules_status?: typeof rulesStatus;
        vlm_status?: typeof vlmStatus;
      };
      status = result.status;
      rulesStatus = result.rules_status ?? 'unavailable';
      vlmStatus = result.vlm_status ?? 'disabled';
    } catch {
      status = 'unavailable';
      rulesStatus = 'unavailable';
      vlmStatus = 'disabled';
    }
  }

  function clearOwnUrls() {
    ownUrls.forEach((url) => URL.revokeObjectURL(url));
    ownUrls = [];
  }

  function showFrame(index: number) {
    if (index < 0 || index >= frames.length) return;
    frameIndex = index;
    const frame = frames[index];
    file = frame.file;
    preview = frame.src;
    prediction = frame.prediction;
    selected = null;
  }

  function chooseFiles(next: File[]) {
    if (busy) return;
    if (!next.length) return;
    if (next.length > 20) {
      error = 'В одной серии может быть до 20 кадров.';
      return;
    }
    if (next.some((candidate) => !acceptedTypes.has(candidate.type))) {
      error = 'Выберите только JPEG, PNG или WebP.';
      return;
    }
    if (next.some((candidate) => !candidate.size || candidate.size > maxBytes)) {
      error = 'Каждый файл должен быть не больше 12 МБ.';
      return;
    }
    sourceGeneration += 1;
    archivedRunId = '';
    archiveMessage = '';
    visualReports.clear();
    loadingScene = false;
    clearOwnUrls();
    sceneId = 'own';
    frames = next.map((candidate, index) => {
      const src = URL.createObjectURL(candidate);
      ownUrls.push(src);
      return { id: `own-${index}`, name: candidate.webkitRelativePath || candidate.name, src, file: candidate, prediction: null };
    });
    error = '';
    progress = 0;
    showFrame(0);
  }

  async function openScene(scene: DemoScene) {
    if (busy) return;
    const generation = ++sourceGeneration;
    archivedRunId = '';
    archiveMessage = '';
    visualReports.clear();
    clearOwnUrls();
    sceneId = scene.id;
    frames = scene.photos.map((photo) => ({
      id: photo.id, name: photo.filename, src: photo.src, file: null, prediction: null,
    }));
    loadingScene = true;
    error = '';
    progress = 0;
    showFrame(0);
    try {
      const loaded = await Promise.all(frames.map(async (frame) => {
        const response = await fetch(frame.src);
        if (!response.ok) throw new Error(`Не удалось открыть ${frame.name}.`);
        const blob = await response.blob();
        return { ...frame, file: new File([blob], `${frame.id}.webp`, { type: 'image/webp' }) };
      }));
      if (generation !== sourceGeneration) return;
      frames = loaded;
      showFrame(0);
    } catch (cause) {
      if (generation === sourceGeneration) error = cause instanceof Error ? cause.message : 'Сцена недоступна.';
    } finally {
      if (generation === sourceGeneration) loadingScene = false;
    }
  }

  function chooseMode(next: '640' | '960') {
    if (busy || next === recognitionMode) return;
    recognitionMode = next;
    archivedRunId = '';
    archiveMessage = '';
    visualReports.clear();
    frames = frames.map((frame) => ({ ...frame, prediction: null }));
    progress = 0;
    showFrame(frameIndex);
  }

  async function analyze() {
    if (!frames.length || frames.some((frame) => !frame.file) || busy) return;
    busy = true;
    error = '';
    archivedRunId = '';
    archiveMessage = '';
    visualReports.clear();
    const alreadyDone = frames.filter((frame) => frame.prediction?.recognition_mode === recognitionMode).length;
    if (alreadyDone === frames.length) {
      frames = frames.map((frame) => ({ ...frame, prediction: null }));
      showFrame(frameIndex);
      progress = 0;
    } else {
      progress = alreadyDone;
    }
    const mode = recognitionMode;
    const controller = new AbortController();
    currentAbort = controller;
    try {
      for (const [index, frame] of frames.entries()) {
        if (!frame.file) continue;
        if (frame.prediction?.recognition_mode === mode) continue;
        if (controller.signal.aborted) break;
        const body = new FormData();
        body.set('image', frame.file);
        body.set('recognition_mode', mode);
        const response = await fetch('/api/model/predict', { method: 'POST', body, signal: controller.signal });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error ?? `Не удалось обработать ${frame.name}.`);
        if (result.schema !== 'sitewatch.inference.v1' || result.recognition_mode !== mode || !Array.isArray(result.detections)) {
          throw new Error('Сервис вернул несовместимый результат.');
        }
        frames = frames.map((item, itemIndex) => itemIndex === index
          ? { ...item, prediction: result as ModelPrediction }
          : item);
        progress = frames.filter((item) => item.prediction?.recognition_mode === mode).length;
        if (frameIndex === index) prediction = result as ModelPrediction;
      }
    } catch (cause) {
      if (!controller.signal.aborted) error = cause instanceof Error ? cause.message : 'Не удалось обработать кадр.';
    } finally {
      currentAbort = null;
      busy = false;
      if (!controller.signal.aborted && progress === frames.length) {
        void saveCurrentRun([...frames], sceneId, recognitionMode, sourceGeneration);
      }
    }
  }

  async function saveCurrentRun(items: SourceFrame[], sourceId: string, mode: '640' | '960', generation: number) {
    try {
      const id = crypto.randomUUID();
      const reports = new Map(visualReports);
      const run = {
        id,
        createdAt: new Date().toISOString(),
        title: sourceId === 'own' ? (items[0]?.name.split('/')[0] || 'Свои кадры') : (scenes.find((scene) => scene.id === sourceId)?.title ?? 'Сцена'),
        origin: sourceId === 'own' ? 'upload' as const : 'demo' as const,
        recognitionMode: mode,
        frames: await Promise.all(items.map(async (item) => ({
          id: item.id,
          name: item.name,
          preview: await archivePreview(item.file!),
          prediction: item.prediction!,
          visual: reports.get(item.id),
        }))),
      };
      await saveArchivedRun(run);
      if (generation === sourceGeneration) for (const [frameId, visual] of visualReports) await updateArchivedVisual(id, frameId, visual);
      if (generation === sourceGeneration) {
        archivedRunId = id;
        archiveMessage = 'Результат сохранён в архиве этого браузера.';
      }
    } catch {
      if (generation === sourceGeneration) archiveMessage = 'Не удалось сохранить результат в браузере. Анализ доступен до закрытия страницы.';
    }
  }

  function onVisualReport(frameId: string, visual: ArchivedVisual) {
    visualReports.set(frameId, visual);
    if (archivedRunId) void updateArchivedVisual(archivedRunId, frameId, visual).catch(() => {
      archiveMessage = 'Анализ сохранён, но визуальный вывод не удалось обновить в локальном архиве.';
    });
  }

  function stopAnalysis() {
    currentAbort?.abort();
  }

  function downloadSceneReport() {
    const processed = frames.filter((frame) => frame.prediction);
    if (!processed.length) return;
    const report = {
      schema: 'sitewatch.scene-recognition.v1',
      scene: sceneId === 'own' ? 'user-upload' : sceneId,
      recognition_mode: recognitionMode,
      note: 'Распознавание техники, без заключения о выполнении этапа. Снимки не включены.',
      frames: processed.map((frame) => ({ filename: frame.name, prediction: frame.prediction })),
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `sitewatch-scene-${sceneId}-${recognitionMode}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function openPlan() {
    showPlan = true;
    await tick();
    document.getElementById('plan-review')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  onMount(() => {
    folderInput.setAttribute('webkitdirectory', '');
    void refreshStatus();
    fetch('/demo-scenes/scenes.json')
      .then(async (response) => {
        if (!response.ok) throw new Error('Подборка сцен недоступна.');
        scenes = (await response.json()) as DemoScene[];
        const initial = scenes.find((scene) => scene.id === '4') ?? scenes[0];
        if (initial && !sceneId) await openScene(initial);
      })
      .catch((cause) => (error = cause instanceof Error ? cause.message : 'Подборка сцен недоступна.'));
    return () => {
      clearOwnUrls();
    };
  });
</script>

<svelte:head>
  <title>Анализ сцен · SiteWatch</title>
  <meta name="robots" content="noindex" />
  <meta
    name="description"
    content="Живая проверка снимка моделью SiteWatch: детектор объектов и классификатор техники."
  />
</svelte:head>

<header class="model-header">
  <Brand compact />
  <nav aria-label="Разделы SiteWatch">
    <a href="/">Главная</a>
    <a href="/app/model" aria-current="page">Анализ сцен</a>
    <a href="/app/site">Архив <span>ДЕМО</span></a>
  </nav>
  <ThemeToggle />
</header>

<main id="main" class="model-workspace">
  <div class="intro">
    <div>
      <h1>Анализ сцен</h1>
      <p>Выберите готовую сцену или загрузите свои кадры. Модель найдёт технику на каждом снимке.</p>
    </div>
  </div>

  <section class="scene-library" aria-label="Демонстрационные сцены">
    <div class="library-heading">
      <div><h2>Сцены</h2><p>Семь серий из подборки команды</p></div>
      <p>Можно открыть свою папку или выбрать отдельные снимки.</p>
    </div>
    <div class="scene-selector" role="group" aria-label="Выбор сцены">
      {#each scenes as scene (scene.id)}
        <button
          type="button"
          class:active={sceneId === scene.id}
          aria-pressed={sceneId === scene.id}
          disabled={busy}
          onclick={() => void openScene(scene)}
        >
          <img src={scene.photos[0].src} alt="" loading="lazy" />
          <span><strong>{scene.title}</strong><small>{frameCount(scene.photos.length)}</small></span>
        </button>
      {/each}
    </div>
    {#if frames.length}
      <div class="scene-context">
        <strong>{sceneId === 'own' ? 'Своя серия' : scenes.find((scene) => scene.id === sceneId)?.title}</strong>
        <span>{frameCount(frames.length)} · обработано: {frameCount(frames.filter((frame) => frame.prediction).length)}</span>
      </div>
      <div class="frame-selector" role="group" aria-label="Кадры серии">
        {#each frames as frame, index (frame.id)}
          <button
            type="button"
            class:active={frameIndex === index}
            aria-pressed={frameIndex === index}
            aria-label={`Кадр ${index + 1}: ${frame.name}`}
            onclick={() => showFrame(index)}
          >
            <img src={frame.src} alt="" loading="lazy" />
            <span>{String(index + 1).padStart(2, '0')}</span>
            {#if frame.prediction}<i aria-label="Распознан" title="Распознан"></i>{/if}
          </button>
        {/each}
      </div>
    {/if}
  </section>

  <div class="model-grid">
    <section class="upload-panel" aria-labelledby="source-title">
      <div class="section-caption">
        <span>НАСТРОЙКИ АНАЛИЗА</span><span>JPEG · PNG · WEBP / ≤12 МБ</span>
      </div>
      <h2 id="source-title">Как распознавать</h2>
      <div class="mode-field">
        <span>Режим распознавания</span>
        <div class="mode-switch" role="group" aria-label="Режим распознавания">
          <button type="button" class:active={recognitionMode === '640'} aria-pressed={recognitionMode === '640'} disabled={busy} onclick={() => chooseMode('640')}>
            <strong>Recognition Medium</strong><small>YOLO 640</small>
          </button>
          <button type="button" class:active={recognitionMode === '960'} aria-pressed={recognitionMode === '960'} disabled={busy} onclick={() => chooseMode('960')}>
            <strong>Recognition Max</strong><small>YOLO 960</small>
          </button>
        </div>
      </div>
      <label class="upload-target">
        <UploadSimpleIcon size={32} />
        <strong>Добавить свои кадры</strong>
        <span
          >Один файл или серия до 20 снимков · JPEG, PNG, WebP</span
        >
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          disabled={busy}
          onchange={(event) => chooseFiles(Array.from(event.currentTarget.files ?? []))}
        />
      </label>
      <button type="button" class="folder-button" disabled={busy} onclick={() => folderInput.click()}>Выбрать папку с кадрами <ArrowRightIcon size={15} /></button>
      <input class="folder-input" type="file" accept="image/jpeg,image/png,image/webp" multiple bind:this={folderInput} onchange={(event) => chooseFiles(Array.from(event.currentTarget.files ?? []))} />
      <p class="source-note">Кадры из разных камер показываем вместе, но не считаем последовательными наблюдениями.</p>
      <div class="run-actions">
        <button
          class="button primary run"
          disabled={!frames.length || loadingScene || frames.some((frame) => !frame.file) || busy || status !== 'ready'}
          onclick={analyze}
        >
          {!frames.length
            ? 'Выберите кадры'
            : busy
            ? `Распознаём ${Math.min(progress + 1, frames.length)} / ${frames.length}…`
            : progress > 0 && progress < frames.length
              ? `Продолжить · осталось ${frameCount(frames.length - progress)}`
              : progress === frames.length && frames.length > 0
                ? 'Распознать заново'
                : `Распознать ${frameCount(frames.length)}`}
          <ArrowRightIcon size={17} />
        </button>
        {#if busy}<button type="button" class="stop-run" onclick={stopAnalysis}>Остановить</button>{/if}
      </div>
      {#if progress > 0}<p class="progress-note" role="status">Обработано {frameCount(progress)} из {frameCount(frames.length)} · {recognitionMode === '640' ? 'Medium' : 'Max'}</p>{/if}
      {#if archiveMessage}<p class="progress-note" role="status">{archiveMessage} {#if archivedRunId}<a href="/app/site/history">Открыть архив ↗</a>{/if}</p>{/if}
      {#if frames.some((frame) => frame.prediction)}
        <button type="button" class="export-scene" onclick={downloadSceneReport}>Скачать результаты сцены в JSON</button>
      {/if}
      {#if status === 'disabled'}
        <p class="message">
          Для запуска включите <code>INFERENCE_DEMO_ENABLED=true</code> и поднимите inference-сервис.
        </p>
      {:else if status === 'unavailable'}
        <p class="message">Сервис не отвечает. Проверьте веса, контейнер и внутренний токен.</p>
      {/if}
      {#if status === 'unavailable' || rulesStatus === 'unavailable'}
        <button class="retry" onclick={refreshStatus}>Проверить соединение ещё раз</button>
      {/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="privacy">
        После анализа браузер сохраняет уменьшенные копии кадров и результаты для локального архива. Исходные файлы на сервере не хранятся. После распознавания выбранный кадр
        автоматически отправляется в OpenRouter для визуального описания, если VLM подключена.
      </div>
    </section>

    <section class="result-panel" aria-labelledby="result-title">
      <div class="section-caption">
        <span>РЕЗУЛЬТАТ</span><span
          >{prediction ? objectCount(prediction.detections.length).toUpperCase() : 'ОЖИДАЕТ КАДР'}</span
        >
      </div>
      <h2 id="result-title">{frames.length ? `Кадр ${frameIndex + 1} из ${frames.length}` : 'Обнаруженная техника'}</h2>
      <VisualInterpretation {file} {prediction} available={vlmStatus === 'ready'} frameId={frames[frameIndex]?.id ?? ''} {sceneId} planSuggestion={scenes.find((scene) => scene.id === sceneId)?.planSuggestion ?? ''} onReport={onVisualReport} />
      {#if preview}
        <div class="image-shell">
          <div class="image-plane">
            <img src={preview} alt="Загруженный кадр для проверки моделью" />
            {#if prediction}
              {#each prediction.detections as detection, index}
                <button
                  class="box"
                  class:other={detection.mapping_status !== 'mapped'}
                  class:selected={selected === index}
                  style:left={`${detection.bounding_box.x_min * 100}%`}
                  style:top={`${detection.bounding_box.y_min * 100}%`}
                  style:width={`${(detection.bounding_box.x_max - detection.bounding_box.x_min) * 100}%`}
                  style:height={`${(detection.bounding_box.y_max - detection.bounding_box.y_min) * 100}%`}
                  aria-label={`${detectionLabel(detection)}, score классификатора ${detection.classifier_score.toFixed(3)}`}
                  aria-pressed={selected === index}
                  onclick={() => (selected = selected === index ? null : index)}
                  ><span class:quiet={index > 7 && selected !== index}>{detectionLabel(detection)}</span></button
                >
              {/each}
            {/if}
          </div>
        </div>
      {:else}
        <div class="empty-frame">
          <span>NO IMAGE / NO INFERENCE</span>
          <p>Рамки объектов появятся здесь после анализа.</p>
        </div>
      {/if}
      {#if prediction}
        <div class="result-provenance">{recognitionMode === '640' ? 'Recognition Medium · YOLO 640' : 'Recognition Max · YOLO 960'} <span>{prediction.model_version}</span></div>
        <div class="result-summary">
          <strong>{mappedCount.toString().padStart(2, '0')}</strong><span
            >сопоставлено с текущими классами правил</span
          >
          <strong>{(prediction.detections.length - mappedCount).toString().padStart(2, '0')}</strong
          ><span>остальные: other, человек или низкая уверенность</span>
        </div>
        {#if prediction.detections.length}
          <div class="detection-list">
            {#each prediction.detections as detection, index}
              <button
                class:active={selected === index}
                onclick={() => (selected = selected === index ? null : index)}
              >
                <span class="index">{String(index + 1).padStart(2, '0')}</span>
                <span class="name"
                  ><strong>{detectionLabel(detection)}</strong><small
                    >{detection.equipment_class ?? detection.mapping_status} · {detection.raw_class}</small
                  ></span
                >
                <span class="scores"
                  ><b>{detection.classifier_score.toFixed(3)}</b><small
                    >score класса · детектор {detection.detector_score.toFixed(3)}</small
                  ></span
                >
              </button>
            {/each}
          </div>
        {:else}
          <p class="no-objects">
            Объекты не найдены при текущем пороге детектора. Это не доказывает, что техники на
            площадке нет.
          </p>
        {/if}
      {/if}
      {#if sceneInventory.length}
        <div class="scene-inventory">
          <div><strong>По всей серии</strong><span>Максимум на одном кадре, без сложения разных камер</span></div>
          <ul>{#each sceneInventory.slice(0, 8) as item}<li><b>{item.label}</b><span>до {item.maxOnFrame} · {frameCount(item.frames)}</span></li>{/each}</ul>
        </div>
        <button type="button" class="to-plan" onclick={openPlan}>Сравнить с планом <ArrowRightIcon size={16} /></button>
      {/if}
    </section>
  </div>
  <section id="plan-review" class="plan-entry" aria-label="Проверка по плану">
    {#if showPlan}
      <LiveEvaluation {prediction} {file} {rulesStatus} />
    {:else}
      <div>
        <h2>Проверка по плану</h2>
        <p>Добавьте этап из графика, правила техники и кадры одной камеры с временем съёмки.</p>
      </div>
      <button type="button" class="button secondary" onclick={openPlan}>Настроить проверку <ArrowRightIcon size={16} /></button>
    {/if}
  </section>
  <aside class="evidence-note">
    <span>ВАЖНО / ГРАНИЦЫ ВЫВОДА</span>
    <p>
      Это результат моделей, а не вердикт о стройке. Для отклонения от графика нужны наблюдаемость
      зоны, актуальный этап, правила количества техники и подтверждение во времени. Уверенности
      моделей не откалиброваны как вероятности.
    </p>
  </aside>
</main>

<style>
  .model-header {
    min-height: 76px;
    padding: 0 clamp(20px, 4vw, 72px);
    display: flex;
    align-items: center;
    gap: 28px;
    border-bottom: 1px solid var(--line);
  }
  .model-header nav {
    margin-left: auto;
    display: flex;
    align-items: stretch;
    gap: 24px;
    font-size: 13px;
  }
  .model-header nav a {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 76px;
    border-bottom: 2px solid transparent;
    color: var(--muted);
  }
  .model-header nav a:hover, .model-header nav a[aria-current='page'] { color: var(--text); }
  .model-header nav a[aria-current='page'] { border-bottom-color: var(--accent); }
  .model-header nav span { font-size: 9px; letter-spacing: .06em; color: var(--muted); }
  @media (max-width: 540px) {
    .model-header { gap: 12px; }
    .model-header nav { gap: 12px; font-size: 11px; }
    .model-header nav span { display: none; }
  }
  .model-workspace {
    max-width: 1740px;
    margin: 0 auto;
    padding: 30px clamp(16px, 2.3vw, 42px) 80px;
  }
  .section-caption,
  .evidence-note > span {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    color: var(--muted);
  }
  .intro {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 28px;
    padding-bottom: 27px;
  }
  h1 {
    font-size: clamp(32px, 3vw, 46px);
    letter-spacing: -0.06em;
    line-height: 0.98;
    font-weight: 700;
  }
  .intro p {
    color: var(--muted);
    margin-top: 9px;
    font-size: 13px;
    line-height: 1.5;
    max-width: 74ch;
  }
  .model-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.65fr) minmax(320px, 0.8fr);
    border: 1px solid var(--line);
    background: var(--surface);
  }
  .upload-panel,
  .result-panel {
    min-width: 0;
    padding: clamp(20px, 2vw, 30px);
  }
  .upload-panel {
    order: 2;
    border-left: 1px solid var(--line);
    background: color-mix(in srgb, var(--raised) 34%, var(--surface));
  }
  .result-panel { order: 1; }
  .section-caption {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 13px;
    border-bottom: 1px solid var(--line);
  }
  .section-caption span:last-child {
    color: var(--muted);
    text-align: right;
  }
  h2 {
    font-size: clamp(21px, 1.9vw, 27px);
    letter-spacing: -0.055em;
    line-height: 1.12;
    margin-top: 20px;
  }
  .upload-panel > p {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.6;
    margin-top: 12px;
    max-width: 42ch;
  }
  .upload-target {
    position: relative;
    cursor: pointer;
    margin-top: 18px;
    border: 1px dashed var(--muted);
    min-height: 126px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 10px;
    background: var(--bg);
  }
  .upload-target:hover {
    border-color: var(--accent);
  }
  .upload-target :global(svg) {
    color: var(--text);
    margin-bottom: 4px;
  }
  .upload-target strong {
    font-size: 15px;
    max-width: 100%;
    overflow-wrap: anywhere;
  }
  .upload-target span {
    color: var(--muted);
    font-size: 12px;
  }
  .upload-target input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
  }
  .upload-target:focus-within {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }
  .run {
    width: 100%;
    justify-content: space-between;
    margin-top: 18px;
  }
  .stop-run {
    margin-top: 10px;
    color: var(--muted);
    font-size: 12px;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .stop-run:hover { color: var(--text); }
  .message,
  .error {
    margin-top: 18px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--warning);
  }
  .error {
    color: var(--danger);
  }
  .retry {
    margin-top: 10px;
    padding: 5px 0;
    color: var(--accent);
    font-size: 12px;
    border-bottom: 1px solid currentColor;
  }
  .retry:hover {
    color: var(--text);
  }
  code {
    font-size: 11px;
  }
  .privacy {
    margin-top: 22px;
    padding-top: 13px;
    border-top: 1px solid var(--line);
    color: var(--muted);
    font-size: 11px;
    line-height: 1.6;
  }
  .result-panel h2 {
    margin-bottom: 16px;
  }
  .image-shell {
    background: #10120f;
    border: 1px solid var(--line);
    padding: 8px;
    min-height: 370px;
    display: grid;
    place-items: center;
  }
  .image-plane {
    position: relative;
    width: fit-content;
    max-width: 100%;
    margin: auto;
  }
  .image-plane img {
    display: block;
    max-width: 100%;
    max-height: min(57vh, 640px);
    width: auto;
    height: auto;
  }
  .box {
    position: absolute;
    border: 2px solid var(--accent);
    padding: 0;
  }
  .box.other {
    border-color: var(--warning);
  }
  .box.selected {
    outline: 2px solid white;
    outline-offset: 3px;
  }
  .box span {
    position: absolute;
    left: -2px;
    bottom: 100%;
    background: var(--accent);
    color: var(--accent-ink);
    font-size: 10px;
    font-weight: 800;
    white-space: nowrap;
    padding: 4px 7px;
  }
  .box span.quiet { display: none; }
  .box.other span {
    background: var(--warning);
    color: var(--bg);
  }
  .empty-frame {
    aspect-ratio: 1.55;
    border: 1px dashed var(--line);
    background: repeating-linear-gradient(
      135deg,
      transparent 0 12px,
      color-mix(in srgb, var(--line) 16%, transparent) 12px 13px
    );
    display: grid;
    place-content: center;
    text-align: center;
    gap: 12px;
  }
  .empty-frame span {
    color: var(--muted);
    font:
      11px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    letter-spacing: 0.12em;
  }
  .empty-frame p {
    color: var(--muted);
    font-size: 12px;
  }
  .result-summary {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 16px;
    margin-top: 14px;
    align-items: center;
  }
  .result-summary strong {
    font-size: 28px;
    letter-spacing: -0.06em;
  }
  .result-summary span {
    font-size: 12px;
    color: var(--muted);
  }
  .detection-list {
    margin-top: 16px;
    border-top: 1px solid var(--line);
    max-height: 280px;
    overflow-y: auto;
  }
  .detection-list button {
    width: 100%;
    text-align: left;
    display: grid;
    grid-template-columns: 36px minmax(0, 1fr) auto;
    gap: 14px;
    align-items: center;
    border-bottom: 1px solid var(--line);
    padding: 14px 5px;
  }
  .detection-list button:hover,
  .detection-list button.active {
    background: var(--raised);
  }
  .index {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--text);
    font-size: 12px;
  }
  .name,
  .scores {
    display: grid;
    gap: 3px;
  }
  .name strong {
    font-size: 13px;
  }
  .name small,
  .scores small {
    font-size: 10px;
    color: var(--muted);
  }
  .scores {
    text-align: right;
  }
  .scores b {
    font-size: 14px;
  }
  .no-objects {
    color: var(--muted);
    font-size: 13px;
    margin-top: 24px;
    line-height: 1.6;
  }
  .evidence-note {
    border-left: 2px solid var(--accent);
    padding: 0 0 0 20px;
    margin-top: 34px;
    max-width: 1050px;
  }
  .scene-library {
    border: 1px solid var(--line);
    border-bottom: 0;
    background: var(--surface);
    padding: 19px 20px 15px;
  }
  .library-heading {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 24px;
    margin-bottom: 15px;
  }
  .mode-field > span {
    color: var(--muted);
    font: 10px ui-monospace, SFMono-Regular, Menlo, monospace;
    letter-spacing: .1em;
    text-transform: uppercase;
  }
  .library-heading h2 { font-size: 19px; margin: 4px 0 0; }
  .library-heading p { max-width: 42ch; color: var(--muted); font-size: 11px; line-height: 1.5; }
  .scene-selector, .frame-selector { display: flex; gap: 8px; overflow-x: auto; scrollbar-width: thin; }
  .scene-selector { padding-bottom: 6px; }
  .scene-selector button {
    display: flex; align-items: center; gap: 9px; text-align: left;
    flex: 0 0 205px; min-width: 0; padding: 5px;
    border: 1px solid var(--line); background: var(--bg);
  }
  .scene-selector button:hover { border-color: var(--accent); }
  .scene-selector button.active { border-color: var(--accent); background: var(--accent-soft); }
  .scene-selector img { width: 50px; height: 49px; object-fit: cover; flex: 0 0 50px; }
  .scene-selector button span { min-width: 0; display: grid; gap: 5px; }
  .scene-selector strong { font-size: 11px; line-height: 1.17; font-weight: 720; }
  .scene-selector small { color: var(--muted); font-size: 10px; }
  .scene-context { display: flex; justify-content: space-between; gap: 12px; margin: 16px 0 9px; }
  .scene-context strong { font-size: 12px; }
  .scene-context span { color: var(--muted); font-size: 11px; }
  .frame-selector button { position: relative; flex: 0 0 72px; width: 72px; height: 52px; border: 2px solid transparent; padding: 0; background: var(--bg); }
  .frame-selector button.active { border-color: var(--accent); }
  .frame-selector img { width: 100%; height: 100%; object-fit: cover; }
  .frame-selector button span { position: absolute; bottom: 1px; right: 2px; padding: 2px 4px; background: #101810d9; color: #fff; font: 10px ui-monospace, monospace; }
  .frame-selector button i { position: absolute; left: 4px; top: 4px; width: 7px; height: 7px; background: var(--accent); border-radius: 50%; }
  .mode-field { margin-top: 23px; }
  .mode-switch { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--line); margin-top: 9px; }
  .mode-switch button { min-width: 0; padding: 11px 9px; text-align: left; background: var(--bg); }
  .mode-switch button + button { border-left: 1px solid var(--line); }
  .mode-switch button.active { background: var(--accent-soft); box-shadow: inset 0 3px 0 var(--accent); }
  .mode-switch strong, .mode-switch small { display: block; }
  .mode-switch strong { font-size: 11px; line-height: 1.2; }
  .mode-switch small { color: var(--muted); font: 10px ui-monospace, monospace; margin-top: 5px; }
  .folder-button { display: flex; justify-content: space-between; align-items: center; width: 100%; margin-top: 9px; color: var(--accent); font-size: 12px; font-weight: 720; }
  .folder-button:hover { color: var(--text); }
  .folder-input { display: none; }
  .source-note, .progress-note { color: var(--muted); font-size: 11px; line-height: 1.5; margin-top: 10px; }
  .result-provenance { display: flex; justify-content: space-between; gap: 12px; margin-top: 12px; color: var(--accent); font: 11px ui-monospace, monospace; }
  .result-provenance span { color: var(--muted); overflow-wrap: anywhere; text-align: right; }
  .export-scene { display: block; margin-top: 10px; color: var(--accent); font-size: 11px; text-align: left; }
  .export-scene:hover { color: var(--text); }
  .scene-inventory { margin-top: 21px; border-top: 1px solid var(--line); padding-top: 15px; }
  .scene-inventory > div { display: flex; justify-content: space-between; gap: 15px; align-items: baseline; }
  .scene-inventory > div strong { font-size: 13px; }
  .scene-inventory > div span { color: var(--muted); font-size: 10px; text-align: right; }
  .scene-inventory ul { display: flex; flex-wrap: wrap; list-style: none; padding: 0; margin: 11px 0 0; gap: 6px; }
  .scene-inventory li { display: flex; gap: 8px; align-items: center; padding: 7px 9px; background: var(--raised); border: 1px solid var(--line); font-size: 11px; }
  .scene-inventory li span { color: var(--muted); font: 10px ui-monospace, monospace; }
  .to-plan { display: inline-flex; gap: 9px; align-items: center; margin-top: 18px; color: var(--accent); font-size: 12px; font-weight: 750; }
  .to-plan:hover { color: var(--text); }
  #plan-review { scroll-margin-top: 20px; }
  .plan-entry:not(:has(.live-evaluation)) {
    margin-top: 24px;
    padding: 24px 28px;
    border: 1px solid var(--line);
    background: var(--surface);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
  }
  .plan-entry h2 { margin: 0; }
  .plan-entry p { margin-top: 7px; color: var(--muted); font-size: 12px; line-height: 1.5; }
  @media (max-width: 650px) { .plan-entry:not(:has(.live-evaluation)) { align-items: stretch; flex-direction: column; } }
  .evidence-note p {
    margin-top: 8px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.7;
  }
  @media (max-width: 920px) {
    .model-grid {
      grid-template-columns: 1fr;
    }
    .upload-panel {
      border-left: 0;
      border-top: 1px solid var(--line);
    }
    .intro {
      align-items: start;
      flex-direction: column;
    }
    .library-heading p { display: none; }
  }
  @media (max-width: 560px) {
    .model-header {
      gap: 12px;
    }
    .section-caption {
      font-size: 9px;
    }
    .image-shell {
      padding: 4px;
    }
    .box span {
      max-width: 100px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }
</style>
