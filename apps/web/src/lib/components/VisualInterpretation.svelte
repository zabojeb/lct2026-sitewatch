<script lang="ts">
  import { untrack } from 'svelte';
  import { fade } from 'svelte/transition';
  import type { ModelPrediction } from '$lib/model';
  import type { ArchivedVisual } from '$lib/model/archive';

  type Interpretation = {
    schema: 'sitewatch.visual-interpretation.v1';
    model?: string;
    work_stage: string;
    /** «высокая» / «средняя» / «низкая»; empty for older answers. */
    confidence?: string;
    stage_evidence: string;
    scene_summary: string;
    plan_alignment: 'consistent' | 'possible_mismatch' | 'insufficient_evidence' | 'not_provided';
    plan_reason: string;
  };

  let { file, prediction, available, frameId, sceneId, planSuggestion, onReport }: {
    file: File | null;
    prediction: ModelPrediction | null;
    available: boolean;
    frameId: string;
    sceneId: string;
    planSuggestion: string;
    onReport?: (frameId: string, visual: ArchivedVisual) => void;
  } = $props();
  let plannedWork = $state('');
  let report = $state<Interpretation | null>(null);
  let reportPlan = $state('');
  let pending = $state(false);
  let error = $state('');
  let requestId = 0;
  let lastPlan = '';
  let timer: ReturnType<typeof setTimeout> | undefined;
  const cache = new Map<string, Interpretation>();
  /** Requests already sent: flipping back to a frame reuses the answer instead of paying twice. */
  const inFlight = new Map<string, Promise<Interpretation>>();

  $effect(() => {
    sceneId;
    untrack(() => { plannedWork = planSuggestion; });
  });

  function keyFor(source: File, detected: ModelPrediction, plan: string) {
    return `${frameId}:${source.name}:${source.size}:${detected.recognition_mode}:${detected.model_version}:${JSON.stringify(detected.detections)}:${plan}`;
  }

  $effect(() => {
    const source = file;
    const detected = prediction;
    const enabled = available;
    frameId;
    untrack(() => {
      // Clicking through frames must not fire one paid request per click: wait until the frame stays.
      clearTimeout(timer);
      requestId += 1;
      pending = false;
      report = null;
      reportPlan = '';
      error = '';
      if (!(source && detected && enabled)) return;
      const cached = cache.get(keyFor(source, detected, ''));
      if (cached) {
        report = cached;
        return;
      }
      pending = true;
      timer = setTimeout(() => void describe(source, detected, ''), 700);
    });
  });

  async function fitImage(source: File): Promise<File> {
    if (source.size <= 5 * 1024 * 1024) return source;
    const bitmap = await createImageBitmap(source);
    try {
      const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Не удалось подготовить изображение.');
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      for (const quality of [0.86, 0.72, 0.56]) {
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
        if (blob && blob.size <= 5 * 1024 * 1024) {
          return new File([blob], 'sitewatch-frame.jpg', { type: 'image/jpeg' });
        }
      }
      throw new Error('Кадр слишком большой для описания.');
    } finally {
      bitmap.close();
    }
  }

  async function describe(source: File, detected: ModelPrediction, plan: string) {
    if (!available) return;
    const key = keyFor(source, detected, plan);
    const cached = cache.get(key);
    if (cached) {
      report = cached;
      reportPlan = plan;
      error = '';
      onReport?.(frameId, { ...cached, planText: plan });
      return;
    }
    lastPlan = plan;
    const current = ++requestId;
    const forFrame = frameId;
    pending = true;
    error = '';
    try {
      let request = inFlight.get(key);
      if (!request) {
        request = requestDescription(source, detected, plan).finally(() => inFlight.delete(key));
        inFlight.set(key, request);
      }
      const result = await request;
      const visual = plan ? cache.get(keyFor(source, detected, '')) : null;
      const merged = visual
        ? { ...result, work_stage: visual.work_stage, confidence: visual.confidence, stage_evidence: visual.stage_evidence, scene_summary: visual.scene_summary }
        : result;
      cache.set(key, merged);
      onReport?.(forFrame, { ...merged, planText: plan });
      if (current === requestId) {
        report = merged;
        reportPlan = plan;
      }
    } catch (cause) {
      if (current === requestId) error = cause instanceof Error ? cause.message : 'Не удалось получить описание работ.';
    } finally {
      if (current === requestId) pending = false;
    }
  }

  async function requestDescription(source: File, detected: ModelPrediction, plan: string) {
    const body = new FormData();
    body.set('image', await fitImage(source));
    body.set('prediction', JSON.stringify(detected));
    body.set('planned_work', plan);
    const response = await fetch('/api/model/describe', { method: 'POST', body });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error ?? 'Не удалось получить описание работ.');
    if (result.schema !== 'sitewatch.visual-interpretation.v1') throw new Error('Сервис описания вернул несовместимый ответ.');
    return result as Interpretation;
  }

  function compareWithPlan() {
    if (file && prediction && !pending) void describe(file, prediction, plannedWork.trim());
  }

  function retry() {
    if (file && prediction && !pending) void describe(file, prediction, lastPlan);
  }

  const alignmentLabel = {
    consistent: 'Видимое согласуется с планом',
    possible_mismatch: 'Возможное расхождение — нужна проверка',
    insufficient_evidence: 'По кадру недостаточно данных',
    not_provided: 'План не указан',
  };
</script>

{#if prediction}
  <section class="visual-review" aria-labelledby="visual-title">
    <h3 id="visual-title">Описание работ <small>по кадру</small></h3>
    {#if report}
      <strong class="stage" aria-live="polite" in:fade={{ duration: 240 }}>{report.work_stage}</strong>
      {#if report.confidence}<span class="confidence">уверенность: {report.confidence}</span>{/if}
      {#if report.stage_evidence}<p class="evidence"><b>По каким признакам:</b> {report.stage_evidence}</p>{/if}
      {#if report.scene_summary && report.scene_summary !== report.stage_evidence}<p class="summary">{report.scene_summary}</p>{/if}
    {:else if pending}
      <div class="skeleton" role="status" aria-label="Описываем видимые работы"><i></i><i></i><i></i></div>
    {:else if !available}
      <p class="notice">Описание работ недоступно: сервис не подключён.</p>
    {/if}
    {#if error}
      <p class="error" role="alert">{error}</p>
      <button type="button" class="retry" disabled={pending} onclick={retry}>Повторить описание</button>
    {/if}
    <p class="caution">Гипотеза по одному кадру: этап подтверждают план и правила.</p>
    <details class="plan-compare">
      <summary>Сопоставить с плановой работой</summary>
      <div class="plan-fields">
        {#if planSuggestion}<p class="plan-source">Подставлен пример работы для этой сцены — ориентир, а не утверждённый график. Текст можно изменить.</p>{/if}
        <label for="planned-work">Какая работа запланирована</label>
        <textarea id="planned-work" bind:value={plannedWork} maxlength="2000" rows="2" placeholder="Например: монтаж опалубки фундаментной плиты"></textarea>
        <button type="button" class="button secondary" disabled={!file || !prediction || !available || pending || !plannedWork.trim()} onclick={compareWithPlan}>
          {pending ? 'Сравниваем…' : 'Сравнить с плановой работой'}
        </button>
        {#if report && reportPlan && reportPlan === plannedWork.trim()}
          <div class="comparison" aria-live="polite">
            <strong>{alignmentLabel[report.plan_alignment]}</strong>
            {#if report.plan_reason}<p>{report.plan_reason}</p>{/if}
          </div>
        {/if}
      </div>
    </details>
  </section>
{/if}

<style>
  .visual-review { padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--bg); }
  h3 { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; font-size: 14px; letter-spacing: -0.02em; }
  h3 small { color: var(--muted); font: 10px ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.08em; text-transform: uppercase; }
  .stage { display: block; margin-top: 10px; font-size: clamp(19px, 1.7vw, 24px); line-height: 1.18; letter-spacing: -0.035em; }
  .confidence { display: inline-block; margin-top: 8px; padding: 3px 9px; border-radius: 999px; background: var(--accent-soft); font-size: 11px; font-weight: 700; }
  .evidence, .summary { margin-top: 10px; font-size: 12.5px; line-height: 1.55; }
  .evidence b { font-weight: 700; }
  .summary { color: var(--muted); }
  .notice, .error { margin-top: 10px; font-size: 13px; line-height: 1.5; }
  .notice { color: var(--muted); }
  .error { color: var(--danger); }
  .retry { margin-top: 8px; color: var(--accent); font-size: 12px; text-decoration: underline; }
  .caution { margin-top: 10px; color: var(--muted); font-size: 11px; line-height: 1.5; }
  .plan-compare { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }
  summary { width: fit-content; cursor: pointer; color: var(--muted); font-size: 12px; font-weight: 700; }
  summary:hover { color: var(--text); }
  .plan-fields { padding-top: 12px; }
  .plan-source { margin: 0 0 10px; color: var(--muted); font-size: 11px; line-height: 1.5; }
  label { display: block; margin-bottom: 6px; font-size: 11px; font-weight: 700; }
  textarea { display: block; width: 100%; min-height: 64px; padding: 9px 11px; resize: vertical; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--text); font: inherit; font-size: 12px; line-height: 1.5; }
  textarea:focus { outline: 2px solid var(--accent); outline-offset: 2px; }
  .plan-fields button { margin-top: 10px; }
  .comparison { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }
  .comparison strong { font-size: 13px; }
  .comparison p { margin-top: 6px; color: var(--muted); font-size: 12px; line-height: 1.5; }
  .skeleton { display: grid; gap: 9px; margin-top: 12px; }
  .skeleton i { height: 14px; border-radius: 7px; background: linear-gradient(90deg, var(--raised) 0%, color-mix(in srgb, var(--raised) 40%, var(--surface)) 50%, var(--raised) 100%); background-size: 200% 100%; animation: shimmer 1.2s linear infinite; }
  .skeleton i:first-child { height: 24px; width: 70%; }
  .skeleton i:last-child { width: 55%; }
  @keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
  @media (prefers-reduced-motion: reduce) { .skeleton i { animation: none; } }
</style>
