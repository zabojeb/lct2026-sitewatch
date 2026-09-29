<script lang="ts">
  import { onMount } from 'svelte';
  import { detectionLabel } from '$lib/model';
  import { deleteArchivedRun, listArchivedRuns, updateArchivedVisual, type ArchivedRun, type ArchivedVisual } from '$lib/model/archive';
  import { frames as frameCount, objects as objectCount } from '$lib/site/format';

  let runs = $state<ArchivedRun[]>([]);
  let selectedRunId = $state('');
  let selectedFrameId = $state('');
  let error = $state('');
  let loading = $state(true);
  let visualBusy = $state(false);
  let visualError = $state('');
  const urls = new Map<string, string>();
  const run = $derived(runs.find((item) => item.id === selectedRunId) ?? runs[0] ?? null);
  const frame = $derived(run?.frames.find((item) => item.id === selectedFrameId) ?? run?.frames[0] ?? null);
  const sourceFor = (runId: string, frameId: string) => urls.get(`${runId}:${frameId}`) ?? '';
  const alignment = {
    consistent: 'Видимое согласуется с описанием',
    possible_mismatch: 'Возможное расхождение',
    insufficient_evidence: 'Недостаточно данных по кадру',
    not_provided: 'План не указан',
  };

  function setRuns(items: ArchivedRun[]) {
    urls.forEach((url) => URL.revokeObjectURL(url));
    urls.clear();
    runs = items;
    for (const item of items) for (const picture of item.frames) {
      urls.set(`${item.id}:${picture.id}`, URL.createObjectURL(picture.preview));
    }
    if (!items.some((item) => item.id === selectedRunId)) selectedRunId = items[0]?.id ?? '';
    selectedFrameId = '';
  }

  onMount(() => {
    void listArchivedRuns().then(setRuns).catch(() => {
      error = 'Не удалось прочитать локальный архив в этом браузере.';
    }).finally(() => (loading = false));
    return () => { urls.forEach((url) => URL.revokeObjectURL(url)); };
  });

  async function remove(id: string) {
    if (!confirm('Удалить этот запуск из локального архива?')) return;
    try {
      await deleteArchivedRun(id);
      setRuns(runs.filter((item) => item.id !== id));
    } catch { error = 'Не удалось удалить запуск.'; }
  }

  async function assess() {
    if (!run || !frame || visualBusy) return;
    visualBusy = true;
    visualError = '';
    const runId = run.id;
    const frameId = frame.id;
    try {
      const body = new FormData();
      body.set('image', new File([frame.preview], 'archive-frame.jpg', { type: 'image/jpeg' }));
      body.set('prediction', JSON.stringify(frame.prediction));
      body.set('planned_work', '');
      const response = await fetch('/api/model/describe', { method: 'POST', body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Не удалось оценить кадр.');
      const visual: ArchivedVisual = { ...result, planText: '' };
      await updateArchivedVisual(runId, frameId, visual);
      runs = runs.map((item) => item.id === runId ? {
        ...item, frames: item.frames.map((picture) => picture.id === frameId ? { ...picture, visual } : picture),
      } : item);
    } catch (cause) {
      visualError = cause instanceof Error ? cause.message : 'Не удалось оценить кадр.';
    } finally { visualBusy = false; }
  }
</script>

<section id="saved-runs" class="run-archive" aria-label="Сохранённые запуски анализа">
  <div class="archive-heading">
    <div><span class="eyebrow">Локальный архив</span><h2>Ваши запуски анализа</h2><p>Результаты и уменьшенные копии кадров хранятся в этом браузере. Каждый запуск остаётся отдельной записью.</p></div>
    <a href="/app/model">Новый анализ ↗</a>
  </div>
  {#if loading}<p class="archive-empty">Открываем сохранённые запуски…</p>
  {:else if error}<p class="archive-empty" role="alert">{error}</p>
  {:else if !runs.length}<p class="archive-empty">Пока пусто. Распознайте сцену или свои кадры — результат появится здесь.</p>
  {:else}
    <div class="run-grid">
      <div class="run-list" aria-label="Запуски">
        {#each runs as item (item.id)}
          <button class:active={run?.id === item.id} onclick={() => { selectedRunId = item.id; selectedFrameId = ''; visualError = ''; }}>
            <img src={sourceFor(item.id, item.frames[0].id)} alt="" />
            <span><b>{item.title}</b><small>{new Date(item.createdAt).toLocaleString('ru-RU')} · {frameCount(item.frames.length)} · {item.recognitionMode === '640' ? 'стандартный режим' : 'детальный режим'}</small></span>
          </button>
        {/each}
      </div>
      {#if run && frame}
        <div class="run-detail">
          <div class="detail-head"><div><span class="eyebrow">{run.origin === 'upload' ? 'Ваши кадры' : 'Готовая сцена'} · {run.recognitionMode === '640' ? 'стандартный режим' : 'детальный режим'}</span><h3>{run.title}</h3></div><button class="delete" onclick={() => remove(run.id)}>Удалить запуск</button></div>
          <div class="photo"><img src={sourceFor(run.id, frame.id)} alt={frame.name} />
            {#each frame.prediction.detections as detection, index (index)}
              <div class="box" style:left={`${detection.bounding_box.x_min * 100}%`} style:top={`${detection.bounding_box.y_min * 100}%`} style:width={`${(detection.bounding_box.x_max - detection.bounding_box.x_min) * 100}%`} style:height={`${(detection.bounding_box.y_max - detection.bounding_box.y_min) * 100}%`} title={detectionLabel(detection)}></div>
            {/each}
          </div>
          <div class="frame-info"><b>{frame.name}</b><span>{objectCount(frame.prediction.detections.length)} найдено</span></div>
          {#if frame.visual}
            <div class="visual"><small>Описание работ</small><b>{frame.visual.work_stage}</b><p>{frame.visual.stage_evidence}</p>
              {#if frame.visual.planText}<div class="plan"><small>Плановая работа: {frame.visual.planText}</small><strong>{alignment[frame.visual.plan_alignment]}</strong><p>{frame.visual.plan_reason}</p></div>{/if}
            </div>
          {:else}
            <div class="visual-missing"><span>Описание работ для этого кадра не сохранено.</span><button disabled={visualBusy} onclick={assess}>{visualBusy ? 'Описываем…' : 'Получить описание'}</button>{#if visualError}<small role="alert">{visualError}</small>{/if}</div>
          {/if}
          <div class="frame-pick" aria-label="Кадры запуска">
            {#each run.frames as item (item.id)}
              <button class:active={frame.id === item.id} onclick={() => { selectedFrameId = item.id; visualError = ''; }} aria-label={`Открыть кадр ${item.name}`}><img src={sourceFor(run.id, item.id)} alt="" /></button>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}
</section>

<style>
  .run-archive { scroll-margin-top: 24px; padding: 26px 0 34px; border-bottom: 1px solid var(--line); }
  .archive-heading { display: flex; justify-content: space-between; align-items: end; flex-wrap: wrap; gap: 15px; margin-bottom: 20px; }
  h2 { margin: 6px 0; font-size: clamp(24px, 2.7vw, 34px); letter-spacing: -.04em; }
  .archive-heading p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.55; }
  .archive-heading a { font-size: 13px; font-weight: 700; border-bottom: 1px solid currentColor; padding-bottom: 4px; }
  .archive-empty { padding: 24px; border: 1px dashed var(--line); color: var(--muted); font-size: 13px; }
  .run-grid { display: grid; grid-template-columns: minmax(220px, .7fr) minmax(0, 1.7fr); gap: 18px; align-items: start; }
  .run-list { display: grid; gap: 8px; max-height: 680px; overflow: auto; }
  .run-list button { display: flex; gap: 12px; align-items: center; width: 100%; min-width: 0; padding: 8px; text-align: left; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); color: var(--text); }
  .run-list button.active, .run-list button:hover { border-color: var(--accent); }
  .run-list img { width: 78px; height: 58px; flex: none; object-fit: cover; }
  .run-list span { min-width: 0; display: grid; gap: 4px; }
  .run-list b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .run-list small { color: var(--muted); font-size: 10px; line-height: 1.45; }
  .run-detail { min-width: 0; padding: 16px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
  .detail-head { display: flex; align-items: start; justify-content: space-between; gap: 10px; margin-bottom: 14px; }
  h3 { margin: 6px 0 0; font-size: 18px; }
  .delete { font-size: 11px; color: var(--muted); text-decoration: underline; }
  .photo { position: relative; width: fit-content; max-width: 100%; line-height: 0; }
  .photo > img { max-width: 100%; max-height: 62vh; object-fit: contain; }
  .box { position: absolute; border: 1.5px solid var(--accent); pointer-events: none; }
  .frame-info { display: flex; justify-content: space-between; gap: 10px; margin-top: 10px; font-size: 12px; }
  .frame-info span { color: var(--muted); }
  .visual { display: grid; gap: 6px; margin-top: 16px; padding: 14px; background: var(--raised); border-left: 3px solid var(--accent); }
  .visual small { color: var(--muted); font-size: 10px; }
  .visual b { font-size: 17px; }
  .visual p { margin: 0; font-size: 12px; line-height: 1.55; }
  .plan { display: grid; gap: 6px; border-top: 1px solid var(--line); padding-top: 10px; margin-top: 5px; }
  .plan strong { font-size: 12px; }
  .visual-missing { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 16px; margin-top: 15px; padding: 13px; border: 1px dashed var(--line); color: var(--muted); font-size: 11px; }
  .visual-missing button { color: var(--text); font-weight: 700; text-decoration: underline; }
  .visual-missing small { color: var(--danger); }
  .frame-pick { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; }
  .frame-pick button { padding: 2px; border: 2px solid transparent; }
  .frame-pick button.active { border-color: var(--accent); }
  .frame-pick img { width: 70px; height: 52px; object-fit: cover; }
  @media (max-width: 800px) { .run-grid { grid-template-columns: 1fr; } .run-list { display: flex; overflow-x: auto; } .run-list button { min-width: 230px; width: 230px; } }
</style>
