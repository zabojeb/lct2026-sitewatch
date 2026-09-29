<script lang="ts">
  import { untrack } from 'svelte';
  import type { ModelPrediction } from '$lib/model';
  import type { ArchivedVisual } from '$lib/model/archive';

  type Interpretation = {
    schema: 'sitewatch.visual-interpretation.v1';
    model?: string;
    work_stage: string;
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
  let currentAbort: AbortController | null = null;
  const cache = new Map<string, Interpretation>();

  $effect(() => {
    sceneId;
    untrack(() => { plannedWork = planSuggestion; });
  });

  function cancelRequest() {
    currentAbort?.abort();
    currentAbort = null;
    requestId += 1;
    pending = false;
  }

  function keyFor(source: File, detected: ModelPrediction, plan: string) {
    return `${frameId}:${source.name}:${source.size}:${detected.recognition_mode}:${detected.model_version}:${JSON.stringify(detected.detections)}:${plan}`;
  }

  $effect(() => {
    const source = file;
    const detected = prediction;
    const enabled = available;
    frameId;
    untrack(() => {
      cancelRequest();
      report = null;
      reportPlan = '';
      error = '';
      if (source && detected && enabled) void describe(source, detected, '');
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
      throw new Error('Кадр слишком большой для визуальной оценки.');
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
    cancelRequest();
    const current = ++requestId;
    const controller = new AbortController();
    currentAbort = controller;
    pending = true;
    error = '';
    try {
      const body = new FormData();
      body.set('image', await fitImage(source));
      body.set('prediction', JSON.stringify(detected));
      body.set('planned_work', plan);
      const response = await fetch('/api/model/describe', { method: 'POST', body, signal: controller.signal });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Не удалось получить визуальную оценку.');
      if (result.schema !== 'sitewatch.visual-interpretation.v1') throw new Error('Несовместимый ответ VLM.');
      if (current === requestId) {
        const visual = plan ? (cache.get(keyFor(source, detected, '')) ?? (reportPlan === '' ? report : null)) : null;
        report = visual ? { ...(result as Interpretation), work_stage: visual.work_stage, stage_evidence: visual.stage_evidence, scene_summary: visual.scene_summary } : result as Interpretation;
        reportPlan = plan;
        cache.set(key, report);
        onReport?.(frameId, { ...report, planText: plan });
      }
    } catch (cause) {
      if (current === requestId && !controller.signal.aborted) error = cause instanceof Error ? cause.message : 'Не удалось получить визуальную оценку.';
    } finally {
      if (current === requestId) {
        pending = false;
        currentAbort = null;
      }
    }
  }

  function compareWithPlan() {
    if (file && prediction && !pending) void describe(file, prediction, plannedWork.trim());
  }

  const alignmentLabel = {
    consistent: 'Видимое согласуется с описанием',
    possible_mismatch: 'Нужно проверить возможное расхождение',
    insufficient_evidence: 'По этому кадру данных мало',
    not_provided: 'План не указан',
  };
</script>

{#if prediction}
  <section class="visual-review" aria-labelledby="visual-title">
    <div class="heading">
      <span class="eyebrow">ВИЗУАЛЬНАЯ ОЦЕНКА · DEEPSEEK</span>
      <span class="scope">Выбранный кадр</span>
    </div>
    <h3 id="visual-title">Предполагаемый этап работ</h3>
    {#if report}
      <strong class="stage" aria-live="polite">{report.work_stage}</strong>
      {#if report.stage_evidence}<p class="evidence"><b>По каким признакам:</b> {report.stage_evidence}</p>{/if}
      {#if report.scene_summary && report.scene_summary !== report.stage_evidence}<p class="summary">{report.scene_summary}</p>{/if}
    {:else if pending}
      <p class="working" role="status">Смотрим кадр и видимые работы…</p>
    {:else if !available}
      <p class="notice">Визуальная оценка сейчас недоступна.</p>
    {/if}
    {#if error}
      <p class="error" role="alert">{error}</p>
      <button type="button" class="retry" disabled={pending} onclick={compareWithPlan}>Повторить визуальную оценку</button>
    {/if}
    <p class="caution">Гипотеза по одному снимку; состав техники сам по себе этап не подтверждает.</p>
    <details class="plan-compare">
      <summary>Сопоставить с плановой работой</summary>
      <div class="plan-fields">
        {#if planSuggestion}<p class="plan-source">Подставлен пример работы из перечня для этой сцены. Это ориентир, не утверждённый календарный график. Можешь изменить текст перед сравнением.</p>{/if}
        <label for="planned-work">Какая работа запланирована</label>
        <textarea id="planned-work" bind:value={plannedWork} maxlength="2000" rows="2" placeholder="Например: монтаж опалубки фундаментной плиты"></textarea>
        <button type="button" class="button secondary" disabled={!file || !prediction || !available || pending || !plannedWork.trim()} onclick={compareWithPlan}>
          {pending ? 'Сравниваем…' : 'Сравнить с планом'}
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
  .visual-review { margin: 0 0 17px; padding: 17px 18px; border: 1px solid var(--line); border-left: 3px solid var(--accent); background: var(--raised); }
  .heading { display: flex; justify-content: space-between; gap: 12px; }
  .eyebrow, .scope { color: var(--muted); font: 10px ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .08em; }
  .scope { white-space: nowrap; }
  h3 { margin: 12px 0 7px; color: var(--muted); font-size: 12px; font-weight: 650; }
  .stage { display: block; font-size: clamp(20px, 2vw, 27px); line-height: 1.16; letter-spacing: -.04em; }
  .evidence, .summary { margin-top: 10px; font-size: 12px; line-height: 1.55; }
  .evidence b { font-weight: 700; }
  .summary { color: var(--muted); }
  .working, .notice, .error { font-size: 13px; line-height: 1.5; }
  .working { color: var(--accent); }
  .notice { color: var(--muted); }
  .error { margin-top: 11px; color: var(--danger); }
  .retry { margin-top: 8px; color: var(--accent); font-size: 12px; text-decoration: underline; }
  .caution { margin-top: 11px; color: var(--muted); font-size: 10px; line-height: 1.5; }
  .plan-compare { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 10px; }
  summary { width: fit-content; cursor: pointer; color: var(--text); font-size: 12px; font-weight: 700; }
  summary:hover { color: var(--accent); }
  .plan-fields { padding-top: 13px; }
  .plan-source { margin: 0 0 12px; color: var(--muted); font-size: 11px; line-height: 1.5; }
  label { display: block; margin-bottom: 7px; font-size: 11px; font-weight: 700; }
  textarea { display: block; width: 100%; min-height: 70px; padding: 10px 12px; resize: vertical; border: 1px solid var(--line); background: var(--bg); color: var(--text); font: inherit; font-size: 12px; line-height: 1.5; }
  textarea:focus { outline: 2px solid var(--accent); outline-offset: 2px; }
  .plan-fields button { margin-top: 10px; }
  .comparison { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 12px; }
  .comparison strong { font-size: 13px; }
  .comparison p { margin-top: 6px; color: var(--muted); font-size: 12px; line-height: 1.5; }
  @media (max-width: 620px) { .heading { display: block; } .scope { display: block; margin-top: 5px; } }
</style>
