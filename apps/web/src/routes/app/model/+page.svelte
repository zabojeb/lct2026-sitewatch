<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { fade, fly, scale } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import UploadSimpleIcon from 'phosphor-svelte/lib/UploadSimpleIcon';
  import Brand from '$lib/components/Brand.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import LiveEvaluation from '$lib/components/LiveEvaluation.svelte';
  import VisualInterpretation from '$lib/components/VisualInterpretation.svelte';
  import { detectionLabel, rawClassLabels, type ModelPrediction } from '$lib/model';
  import { archivePreview, saveArchivedRun, updateArchivedVisual, type ArchivedVisual } from '$lib/model/archive';
  import { uid } from '$lib/browser-crypto';
  import type { PlanScenario } from '$lib/model/scenario';
  import { frames as frameCount, objects as objectCount } from '$lib/site/format';

  type DemoPhoto = { id: string; src: string; filename: string; capturedAt?: string };
  type DemoScene = { id: string; title: string; context: string; date: string | null; photos: DemoPhoto[]; planSuggestion?: string; check?: PlanScenario };
  type SourceFrame = {
    id: string;
    name: string;
    src: string;
    file: File | null;
    prediction: ModelPrediction | null;
    capturedAt?: string;
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
  const score = (value: number) => value.toFixed(2).replace('.', ',');
  const calm = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ms = (value: number) => (calm ? 0 : value);
  const recognised = $derived(frames.length > 0 && progress === frames.length);
  const mappingLabel: Record<string, string> = {
    mapped: 'учитывается в правилах',
    other: 'вне перечня правил',
    ignored: 'не учитывается',
    low_confidence: 'низкая уверенность',
  };
  let folderInput: HTMLInputElement;
  const maxBytes = 12 * 1024 * 1024;
  const acceptedTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
  const mappedCount = $derived(
    prediction?.detections.filter((d) => d.mapping_status === 'mapped').length ?? 0,
  );
  /** Machines on the open frame, grouped by the same label the boxes show. */
  const frameInventory = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const detection of prediction?.detections ?? []) {
      if (detection.mapping_status !== 'mapped') continue;
      const label = detectionLabel(detection);
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return [...counts].map(([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count);
  });
  const currentScene = $derived(scenes.find((scene) => scene.id === sceneId));
  const sceneInventory = $derived.by(() => {
    const inventory = new Map<string, { label: string; frames: number; maxOnFrame: number }>();
    for (const frame of frames) {
      if (!frame.prediction) continue;
      const counts = new Map<string, number>();
      for (const detection of frame.prediction.detections) {
        if (detection.mapping_status === 'ignored' || detection.mapping_status === 'low_confidence') continue;
        const label = detectionLabel(detection);
        counts.set(label, (counts.get(label) ?? 0) + 1);
      }
      for (const [code, count] of counts) {
        const current = inventory.get(code) ?? { label: code, frames: 0, maxOnFrame: 0 };
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

  function chooseFiles(picked: File[]) {
    if (busy) return;
    if (!picked.length) return;
    const next = picked
      .filter((candidate) => acceptedTypes.has(candidate.type))
      .sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name, 'ru', { numeric: true }));
    if (!next.length) {
      error = 'Выберите JPEG, PNG или WebP.';
      return;
    }
    if (next.length > 20) {
      error = 'За один раз — не больше 20 кадров.';
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
    if (busy || (scene.id === sceneId && frames.length)) return;
    const generation = ++sourceGeneration;
    archivedRunId = '';
    archiveMessage = '';
    visualReports.clear();
    clearOwnUrls();
    sceneId = scene.id;
    frames = scene.photos.map((photo) => ({
      id: photo.id, name: photo.filename, src: photo.src, file: null, prediction: null, capturedAt: photo.capturedAt,
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
        const type = blob.type.startsWith('image/') ? blob.type : 'image/webp';
        return { ...frame, file: new File([blob], `${frame.id}.${type.split('/')[1]}`, { type }) };
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
    sourceGeneration += 1;
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
    sourceGeneration += 1;
    archivedRunId = '';
    archiveMessage = '';
    const alreadyDone = frames.filter((frame) => frame.prediction?.recognition_mode === recognitionMode).length;
    if (alreadyDone === frames.length) {
      visualReports.clear();
      frames = frames.map((frame) => ({ ...frame, prediction: null }));
      showFrame(frameIndex);
      progress = 0;
    } else {
      progress = alreadyDone;
    }
    const mode = recognitionMode;
    const controller = new AbortController();
    currentAbort = controller;
    // Two requests in flight: the next frame uploads while the server is busy with the current one.
    const queue = frames.flatMap((frame, index) => (frame.file && frame.prediction?.recognition_mode !== mode ? [index] : []));
    const worker = async () => {
      while (queue.length && !controller.signal.aborted) {
        const index = queue.shift()!;
        const frame = frames[index];
        const body = new FormData();
        body.set('image', frame.file!);
        body.set('recognition_mode', mode);
        const response = await fetch('/api/model/predict', { method: 'POST', body, signal: controller.signal });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error ?? `Не удалось распознать ${frame.name}: сервис ответил ${response.status}.`);
        if (result.schema !== 'sitewatch.inference.v1' || result.recognition_mode !== mode || !Array.isArray(result.detections)) {
          throw new Error('Сервис вернул несовместимый результат.');
        }
        frames = frames.map((item, itemIndex) => itemIndex === index
          ? { ...item, prediction: result as ModelPrediction }
          : item);
        progress = frames.filter((item) => item.prediction?.recognition_mode === mode).length;
        if (frameIndex === index) prediction = result as ModelPrediction;
      }
    };
    // The first real failure stops the other request; a user "Стоп" is not a failure.
    let failure: unknown = null;
    const guard = (run: Promise<void>) => run.catch((cause) => {
      if (!failure && !(cause instanceof DOMException && cause.name === 'AbortError')) failure = cause;
      controller.abort();
    });
    try {
      await Promise.all([guard(worker()), guard(worker())]);
      if (failure) error = failure instanceof Error ? failure.message : 'Не удалось обработать кадр.';
    } finally {
      currentAbort = null;
      busy = false;
      if (!controller.signal.aborted && progress === frames.length) {
        void saveCurrentRun([...frames], sceneId, recognitionMode, sourceGeneration);
      }
    }
  }

  async function archiveFrame(item: SourceFrame, reports: Map<string, ArchivedVisual>) {
    return {
      id: item.id,
      name: item.name,
      preview: await archivePreview(item.file!),
      prediction: $state.snapshot(item.prediction!),
      visual: $state.snapshot(reports.get(item.id)),
    };
  }

  async function saveCurrentRun(items: SourceFrame[], sourceId: string, mode: '640' | '960', generation: number) {
    try {
      const id = uid();
      const reports = new Map(visualReports);
      const run = {
        id,
        createdAt: new Date().toISOString(),
        title: sourceId === 'own' ? (items[0]?.name.split('/')[0] || 'Свои кадры') : (scenes.find((scene) => scene.id === sourceId)?.title ?? 'Сцена'),
        origin: sourceId === 'own' ? 'upload' as const : 'demo' as const,
        recognitionMode: mode,
        frames: [] as Awaited<ReturnType<typeof archiveFrame>>[],
      };
      for (const item of items) run.frames.push(await archiveFrame(item, reports));
      await saveArchivedRun(run);
      if (generation === sourceGeneration) for (const [frameId, visual] of visualReports) await updateArchivedVisual(id, frameId, $state.snapshot(visual));
      if (generation === sourceGeneration) {
        archivedRunId = id;
        archiveMessage = 'Результат сохранён в архиве этого браузера.';
      }
    } catch (reason) {
      console.error('archive save failed', reason);
      if (generation === sourceGeneration) archiveMessage = 'Не удалось сохранить результат в браузере. Анализ доступен до закрытия страницы.';
    }
  }

  function onVisualReport(frameId: string, visual: ArchivedVisual) {
    visualReports.set(frameId, visual);
    if (archivedRunId) void updateArchivedVisual(archivedRunId, frameId, $state.snapshot(visual)).catch(() => {
      archiveMessage = 'Результат сохранён, но описание работ не удалось добавить в архив.';
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
    content="Распознавание техники на кадрах стройки: детектор объектов, классификатор техники и описание работ."
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
    <h1>Анализ сцен</h1>
    <p>Выберите сцену, распознайте технику и проверьте кадры по плану работ.</p>
  </div>

  <section class="scene-library" aria-label="Сцены">
    <div class="scene-selector" role="group" aria-label="Выбор сцены">
      <div class="own-card" class:active={sceneId === 'own'}>
        <UploadSimpleIcon size={22} />
        <span><strong>Свои кадры</strong><small>до 20 · JPEG, PNG, WebP</small></span>
        <span class="own-actions">
          <label class="own-pick"
            >Файлы<input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              disabled={busy}
              onchange={(event) => { chooseFiles(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = ''; }}
            /></label
          >
          <button type="button" class="own-pick" disabled={busy} onclick={() => folderInput.click()}>Папка</button>
        </span>
      </div>
      {#each scenes as scene (scene.id)}
        <button
          type="button"
          class="scene-card"
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
    <input class="folder-input" type="file" accept="image/jpeg,image/png,image/webp" multiple bind:this={folderInput} onchange={(event) => { chooseFiles(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = ''; }} />
  </section>

  <section class="workbench" aria-label="Распознавание">
    <ol class="steps" aria-label="Порядок работы">
      <li class:done={frames.length > 0} class:current={!frames.length}><i>1</i>Сцена</li>
      <li class:done={recognised} class:current={frames.length > 0 && !recognised}><i>2</i>Распознавание</li>
      <li class:done={showPlan} class:current={recognised && !showPlan}><i>3</i>Проверка по плану</li>
    </ol>
    <div class="toolbar">
      <div class="frame-selector" role="group" aria-label="Кадры сцены">
        {#each frames as frame, index (frame.id)}
          <button
            type="button"
            class:active={frameIndex === index}
            aria-pressed={frameIndex === index}
            aria-label={`Кадр ${index + 1}: ${frame.name}`}
            onclick={() => showFrame(index)}
          >
            <img src={frame.src} alt="" loading="lazy" />
            <span>{index + 1}</span>
            {#if frame.prediction}<i aria-label="Распознан" title="Распознан"></i>{/if}
          </button>
        {/each}
      </div>
      <div class="run-controls">
        <div class="mode-switch" role="group" aria-label="Режим распознавания">
          <button type="button" class:active={recognitionMode === '640'} aria-pressed={recognitionMode === '640'} disabled={busy} onclick={() => chooseMode('640')} title="YOLO 640 — быстрее">Стандартный</button>
          <button type="button" class:active={recognitionMode === '960'} aria-pressed={recognitionMode === '960'} disabled={busy} onclick={() => chooseMode('960')} title="YOLO 960 — лучше для мелких и дальних машин">Детальный</button>
        </div>
        <button
          class="button primary run"
          disabled={!frames.length || loadingScene || frames.some((frame) => !frame.file) || busy || status !== 'ready'}
          onclick={analyze}
        >
          {!frames.length
            ? 'Выберите кадры'
            : busy
            ? `Распознаём ${Math.min(progress + 1, frames.length)} из ${frames.length}…`
            : progress > 0 && progress < frames.length
              ? `Продолжить · осталось ${frameCount(frames.length - progress)}`
              : progress === frames.length && frames.length > 0
                ? 'Распознать заново'
                : `Распознать ${frameCount(frames.length)}`}
          <ArrowRightIcon size={17} />
        </button>
        {#if busy}<button type="button" class="stop-run" onclick={stopAnalysis}>Стоп</button>{/if}
      </div>
    </div>
    {#if busy}<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax={frames.length} aria-valuenow={progress}><i style:width={`${(progress / Math.max(1, frames.length)) * 100}%`}></i></div>{/if}
    {#if status === 'disabled'}
      <p class="message">Распознавание отключено в этой сборке (<code>INFERENCE_DEMO_ENABLED</code>).</p>
    {:else if status === 'unavailable'}
      <p class="message">Сервис распознавания ещё запускается или не отвечает. <button class="retry" onclick={refreshStatus}>Проверить снова</button></p>
    {/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}

    <div class="stage">
      <div class="viewer">
        {#if preview}
          <div class="image-shell">
            <div class="image-plane">
              {#key preview}<img src={preview} alt="Кадр для распознавания" in:fade={{ duration: ms(220) }} />{/key}
              {#if busy && !prediction}<div class="scan" aria-hidden="true"></div>{/if}
              {#if prediction}
                {#each prediction.detections as detection, index}
                  <button
                    class="box"
                    class:other={detection.mapping_status !== 'mapped'}
                    class:selected={selected === index}
                    class:edge-top={detection.bounding_box.y_min < 0.07}
                    class:edge-right={detection.bounding_box.x_min > 0.6}
                    style:left={`${detection.bounding_box.x_min * 100}%`}
                    style:top={`${detection.bounding_box.y_min * 100}%`}
                    style:width={`${(detection.bounding_box.x_max - detection.bounding_box.x_min) * 100}%`}
                    style:height={`${(detection.bounding_box.y_max - detection.bounding_box.y_min) * 100}%`}
                    aria-label={`${detectionLabel(detection)}, уверенность классификатора ${score(detection.classifier_score)}`}
                    aria-pressed={selected === index}
                    onclick={() => (selected = selected === index ? null : index)}
                    in:scale={{ duration: ms(260), delay: ms(Math.min(index, 12) * 45), start: 0.92, easing: cubicOut }}
                    ><span class:quiet={index > 7 && selected !== index}>{detectionLabel(detection)}</span></button
                  >
                {/each}
              {/if}
            </div>
          </div>
        {:else}
          <div class="empty-frame">
            <p>{loadingScene ? 'Открываем сцену…' : 'Выберите сцену или загрузите свои кадры.'}</p>
          </div>
        {/if}
        <div class="viewer-meta">
          <span
            >{frames.length ? `Кадр ${frameIndex + 1} из ${frames.length}` : 'Нет кадров'}{#if currentScene && sceneId !== 'own'}
              · {currentScene.title}{/if}</span
          >
          <span
            >{#if progress > 0}Распознано {progress} из {frames.length} · {recognitionMode === '640' ? 'стандартный' : 'детальный'} режим{/if}</span
          >
        </div>
        {#if archiveMessage}<p class="archive-note" role="status">{archiveMessage} {#if archivedRunId}<a href="/app/site/history">Открыть архив</a>{/if}</p>{/if}
      </div>

      <aside class="insights" aria-label="Результат по кадру">
        <VisualInterpretation {file} {prediction} available={vlmStatus === 'ready'} frameId={frames[frameIndex]?.id ?? ''} {sceneId} planSuggestion={currentScene?.planSuggestion ?? ''} onReport={onVisualReport} />
        {#if prediction}
          <div class="card" in:fly={{ y: 12, duration: ms(260), easing: cubicOut }}>
            <h3>Техника на кадре</h3>
            {#if frameInventory.length}
              <ul class="chips">{#each frameInventory as item (item.label)}<li><b>{item.label}</b>{#if item.count > 1}<span>×{item.count}</span>{/if}</li>{/each}</ul>
            {:else}
              <p class="muted">Техника на кадре не найдена. Это не значит, что её нет на площадке.</p>
            {/if}
            {#if prediction.detections.length - mappedCount > 0}<p class="muted small">Ещё {objectCount(prediction.detections.length - mappedCount)}: люди, неопознанные или вне перечня правил.</p>{/if}
            {#if prediction.detections.length}
              <details class="all-objects">
                <summary>Все объекты и уверенность</summary>
                <div class="detection-list">
                  {#each prediction.detections as detection, index}
                    <button class:active={selected === index} onclick={() => (selected = selected === index ? null : index)}>
                      <span class="name"><strong>{detectionLabel(detection)}</strong><small>{mappingLabel[detection.mapping_status] ?? detection.mapping_status}</small></span>
                      <span class="scores"><b>{score(detection.classifier_score)}</b><small>детектор {score(detection.detector_score)}</small></span>
                    </button>
                  {/each}
                </div>
              </details>
            {/if}
          </div>
        {/if}
        {#if sceneInventory.length}
          <div class="card" in:fly={{ y: 12, duration: ms(260), delay: ms(60), easing: cubicOut }}>
            <h3>По всей сцене <small>максимум на одном кадре</small></h3>
            <ul class="chips">{#each sceneInventory.slice(0, 8) as item (item.label)}<li><b>{item.label}</b><span>до {item.maxOnFrame} · {frameCount(item.frames)}</span></li>{/each}</ul>
          </div>
          <button type="button" class="button primary to-plan" class:pulse={recognised && !showPlan} onclick={openPlan}>Проверить по плану <ArrowRightIcon size={16} /></button>
        {/if}
      </aside>
    </div>
  </section>

  <section id="plan-review" class="plan-entry" aria-label="Проверка по плану">
    {#if showPlan}
      <LiveEvaluation
        {prediction}
        {file}
        {rulesStatus}
        scenario={sceneId === 'own' ? null : (currentScene?.check ?? null)}
        sceneFrames={frames}
      />
    {:else}
      <div>
        <h2>Проверка по плану</h2>
        <p>Этап, правило по технике и несколько кадров одной камеры — и сервис правил покажет, чего не хватает.</p>
      </div>
      <button type="button" class="button secondary" onclick={openPlan}>Открыть <ArrowRightIcon size={16} /></button>
    {/if}
  </section>

  <footer class="fineprint">
    <p>
      Это подсказки моделей, а не заключение о стройке: отклонение фиксируется по этапу, правилу и нескольким кадрам во
      времени. Кадры не хранятся на сервере; описание работ делает мультимодальная модель; результаты — в архиве
      этого браузера.
    </p>
    {#if frames.some((frame) => frame.prediction)}<button type="button" class="export-scene" onclick={downloadSceneReport}>Скачать результаты сцены (JSON)</button>{/if}
  </footer>
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
    max-width: 1480px;
    margin: 0 auto;
    padding: 28px clamp(16px, 2.3vw, 40px) 64px;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
  }
  .intro h1 {
    font-size: clamp(30px, 2.8vw, 42px);
    letter-spacing: -0.055em;
    line-height: 1;
    font-weight: 700;
  }
  .intro p {
    color: var(--muted);
    margin-top: 8px;
    font-size: 14px;
    line-height: 1.5;
  }
  h2 {
    font-size: clamp(20px, 1.7vw, 24px);
    letter-spacing: -0.045em;
    line-height: 1.15;
  }

  /* scenes */
  .scene-selector {
    display: flex;
    gap: 10px;
    overflow-x: auto;
    padding: 2px 2px 8px;
    scrollbar-width: thin;
  }
  .scene-card,
  .own-card {
    flex: 0 0 236px;
    display: flex;
    align-items: center;
    gap: 11px;
    min-height: 72px;
    padding: 9px 12px 9px 9px;
    text-align: left;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--surface);
    transition: border-color 0.15s, background 0.15s;
  }
  .scene-card:hover { border-color: var(--accent); }
  .scene-card.active,
  .own-card.active {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .scene-card img {
    width: 54px;
    height: 54px;
    flex: 0 0 54px;
    object-fit: cover;
    border-radius: 7px;
  }
  .scene-card span,
  .own-card > span:not(.own-actions) {
    min-width: 0;
    display: grid;
    gap: 4px;
  }
  .scene-card strong,
  .own-card strong {
    font-size: 12.5px;
    line-height: 1.2;
    font-weight: 700;
  }
  .scene-card small,
  .own-card small {
    color: var(--muted);
    font-size: 11px;
  }
  .own-card {
    flex-basis: 250px;
    border-style: dashed;
    background: transparent;
  }
  .own-card :global(svg) { flex: none; color: var(--muted); }
  .own-actions {
    margin-left: auto;
    display: grid;
    gap: 5px;
  }
  .own-pick {
    position: relative;
    display: block;
    padding: 4px 10px;
    border: 1px solid var(--line);
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    text-align: center;
    cursor: pointer;
    background: var(--surface);
  }
  .own-pick:hover { border-color: var(--accent); }
  .own-pick input {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }
  .own-pick:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  .folder-input { display: none; }

  /* workbench */
  .workbench {
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surface);
    padding: clamp(14px, 1.6vw, 22px);
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }
  .frame-selector {
    display: flex;
    gap: 7px;
    overflow-x: auto;
    min-width: 0;
    flex: 1 1 320px;
    padding: 2px;
    scrollbar-width: thin;
  }
  .frame-selector button {
    position: relative;
    flex: 0 0 66px;
    height: 46px;
    padding: 0;
    border-radius: 7px;
    overflow: hidden;
    outline: 2px solid transparent;
    outline-offset: 1px;
    background: var(--bg);
  }
  .frame-selector button.active { outline-color: var(--accent); }
  .frame-selector img { width: 100%; height: 100%; object-fit: cover; }
  .frame-selector button span {
    position: absolute;
    right: 3px;
    bottom: 3px;
    min-width: 16px;
    padding: 1px 4px;
    border-radius: 4px;
    background: #101810cc;
    color: #fff;
    font: 10px ui-monospace, monospace;
  }
  .frame-selector button i {
    position: absolute;
    left: 5px;
    top: 5px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 2px #101810aa;
  }
  .run-controls {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .mode-switch {
    display: inline-flex;
    padding: 3px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: var(--bg);
  }
  .mode-switch button {
    padding: 8px 14px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    color: var(--muted);
  }
  .mode-switch button.active {
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 1px 3px #0003;
  }
  .run { gap: 12px; border-radius: 999px; }
  .stop-run {
    color: var(--muted);
    font-size: 12px;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .stop-run:hover { color: var(--text); }
  .progress {
    height: 3px;
    border-radius: 3px;
    background: var(--line);
    overflow: hidden;
  }
  .progress i {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width 0.3s;
  }
  .message,
  .error {
    font-size: 13px;
    line-height: 1.5;
    color: var(--warning);
  }
  .error { color: var(--danger); }
  .retry {
    color: var(--accent);
    font-size: 13px;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  code { font-size: 11px; }

  .stage {
    display: grid;
    grid-template-columns: minmax(0, 1.75fr) minmax(300px, 1fr);
    gap: 18px;
    align-items: start;
  }
  .viewer { min-width: 0; display: grid; gap: 8px; }
  .image-shell {
    overflow: hidden;
    border-radius: 10px;
    background: #10120f;
    min-height: 360px;
    display: grid;
    place-items: center;
    padding: 6px;
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
    max-height: min(64vh, 700px);
    width: auto;
    height: auto;
    border-radius: 6px;
  }
  .box {
    position: absolute;
    border: 2px solid var(--accent);
    border-radius: 3px;
    padding: 0;
  }
  .box.other { border-color: var(--warning); border-style: dashed; }
  .box.selected { outline: 2px solid white; outline-offset: 3px; }
  .box span {
    position: absolute;
    left: -2px;
    bottom: calc(100% + 2px);
    border-radius: 4px;
    background: var(--accent);
    color: var(--accent-ink);
    font-size: 10.5px;
    font-weight: 800;
    white-space: nowrap;
    padding: 3px 7px;
  }
  .box span.quiet { display: none; }
  /* labels stay inside the frame: under the top edge and against the right edge */
  .box.edge-top span { top: 2px; bottom: auto; left: 2px; }
  .box.edge-right span { left: auto; right: -2px; }
  .box.edge-top.edge-right span { right: 2px; }
  .box.other span { background: var(--warning); color: var(--bg); }
  .empty-frame {
    aspect-ratio: 16 / 9;
    border: 1px dashed var(--line);
    border-radius: 10px;
    display: grid;
    place-content: center;
    text-align: center;
  }
  .empty-frame p { color: var(--muted); font-size: 14px; }
  .viewer-meta {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    color: var(--muted);
    font-size: 12px;
  }
  .archive-note { color: var(--muted); font-size: 12px; }
  .archive-note a { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }

  .insights {
    position: sticky;
    top: 16px;
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  .card {
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--bg);
    padding: 14px 16px;
  }
  .card h3 {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
    font-size: 14px;
    letter-spacing: -0.02em;
  }
  .card h3 small { color: var(--muted); font-size: 11px; font-weight: 500; letter-spacing: 0; }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    list-style: none;
    padding: 0;
    margin: 11px 0 0;
  }
  .chips li {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 6px 10px;
    border-radius: 999px;
    background: var(--accent-soft);
    font-size: 12px;
  }
  .chips li span { color: var(--muted); font-size: 11px; }
  .muted { color: var(--muted); font-size: 13px; line-height: 1.5; margin-top: 10px; }
  .muted.small { font-size: 11.5px; }
  .all-objects { margin-top: 12px; }
  .all-objects summary {
    width: fit-content;
    cursor: pointer;
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
  }
  .all-objects summary:hover { color: var(--text); }
  .detection-list {
    margin-top: 8px;
    max-height: 260px;
    overflow-y: auto;
    border-top: 1px solid var(--line);
  }
  .detection-list button {
    width: 100%;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    padding: 9px 4px;
    text-align: left;
    border-bottom: 1px solid var(--line);
  }
  .detection-list button:hover,
  .detection-list button.active { background: var(--raised); }
  .name, .scores { display: grid; gap: 2px; }
  .name strong { font-size: 12.5px; }
  .name small, .scores small { color: var(--muted); font-size: 10.5px; }
  .scores { text-align: right; }
  .scores b { font: 12px ui-monospace, monospace; }
  .to-plan { width: 100%; justify-content: space-between; border-radius: 999px; }

  .plan-entry:not(:has(.live-evaluation)) {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 22px;
    padding: 20px 22px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surface);
  }
  .plan-entry p { margin-top: 6px; color: var(--muted); font-size: 13px; line-height: 1.5; }
  #plan-review { scroll-margin-top: 20px; }

  .fineprint {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 20px;
    color: var(--muted);
    font-size: 11.5px;
    line-height: 1.55;
  }
  .fineprint p { max-width: 90ch; }
  .export-scene { flex: none; color: var(--accent); font-size: 12px; font-weight: 700; }
  .export-scene:hover { color: var(--text); }

  @media (max-width: 1024px) {
    .stage { grid-template-columns: 1fr; }
    .insights { position: static; }
  }
  @media (max-width: 640px) {
    .scene-card, .own-card { flex-basis: 200px; }
    .run-controls, .run { width: 100%; }
    .run { justify-content: space-between; }
    .mode-switch { width: 100%; }
    .mode-switch button { flex: 1; }
    .image-shell { min-height: 220px; }
    .plan-entry:not(:has(.live-evaluation)), .fineprint { flex-direction: column; align-items: stretch; }
  }

  /* steps */
  .steps { display: flex; gap: 8px; list-style: none; padding: 0; margin: 0; flex-wrap: wrap; }
  .steps li { display: inline-flex; align-items: center; gap: 9px; padding: 7px 14px 7px 8px; border-radius: 999px; background: var(--bg); color: var(--muted); font-size: 12.5px; font-weight: 700; transition: background .25s, color .25s; }
  .steps li i { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-style: normal; font-size: 11px; background: var(--raised); color: var(--muted); transition: background .25s, color .25s; }
  .steps li.current { background: var(--accent-soft); color: var(--text); }
  .steps li.current i { background: var(--accent); color: var(--accent-ink); animation: breathe 1.8s ease-in-out infinite; }
  .steps li.done { color: var(--text); }
  .steps li.done i { background: var(--text); color: var(--bg); }
  @keyframes breathe { 50% { box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 35%, transparent); } }
  /* scan line over the frame being recognised */
  .scan { position: absolute; inset: 0; pointer-events: none; overflow: hidden; border-radius: 6px; }
  .scan::after { content: ''; position: absolute; left: 0; right: 0; height: 30%; background: linear-gradient(180deg, transparent, color-mix(in srgb, var(--accent) 40%, transparent), transparent); animation: scan 1.4s ease-in-out infinite; }
  @keyframes scan { from { top: -30%; } to { top: 100%; } }
  /* tactile controls */
  .scene-card, .own-card, .frame-selector button, .mode-switch button, .run, .to-plan { transition: transform .16s ease, box-shadow .2s ease, background .2s ease, border-color .2s ease, outline-color .2s ease; }
  .scene-card:hover { transform: translateY(-2px); box-shadow: 0 10px 24px -14px rgba(0, 0, 0, .35); }
  .scene-card:active, .run:active, .to-plan:active, .mode-switch button:active { transform: scale(.98); }
  .frame-selector button:hover { transform: translateY(-1px); }
  .to-plan.pulse { animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 50% { box-shadow: 0 0 0 7px color-mix(in srgb, var(--accent) 30%, transparent); } }
  @media (prefers-reduced-motion: reduce) {
    .steps li.current i, .scan::after, .to-plan.pulse { animation: none; }
    .scene-card:hover, .frame-selector button:hover { transform: none; }
  }
</style>
