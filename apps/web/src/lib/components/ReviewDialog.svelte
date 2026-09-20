<script lang="ts">
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import EvidenceViewer from './EvidenceViewer.svelte';
  import {
    assessmentLabels,
    decisionLabels,
    formatTime,
    type Observation,
    type Review,
    type Decision,
  } from '$lib/demo/data';
  let {
    observation,
    review,
    onsave,
  }: { observation: Observation | null; review?: Review; onsave: (value: Review) => void } =
    $props();
  let dialog: HTMLDialogElement;
  let note = $state('');
  let decision = $state<Decision>('acknowledged');
  let error = $state('');
  export function open() {
    note = review?.note || '';
    decision = review?.decision || 'acknowledged';
    error = '';
    dialog.showModal();
  }
  function save(event: SubmitEvent) {
    event.preventDefault();
    if (!observation) return;
    if (note.trim().length < 3) {
      error = 'Добавьте комментарий: минимум 3 символа.';
      return;
    }
    onsave({
      observationId: observation.id,
      decision,
      note: note.trim(),
      createdAt: new Date().toISOString(),
    });
    dialog.close();
  }
</script>

<dialog bind:this={dialog} aria-labelledby="review-title">
  {#if observation}
    <div class="dialog-heading">
      <div>
        <span class="muted mono">{observation.id} / демо</span>
        <h2 id="review-title">{observation.title}</h2>
      </div>
      <button class="icon-button" aria-label="Закрыть разбор" onclick={() => dialog.close()}
        ><XIcon size={23} /></button
      >
    </div>
    <div class="review-grid">
      <div class="visual">
        <EvidenceViewer
          src={observation.image}
          alt={`Демонстрация: ${observation.zone}`}
          detections={observation.detections}
        />
        <div class="evidence-meta">
          <span>{observation.camera} / {observation.zone}</span><span
            >{formatTime(observation.time)} МСК</span
          >
        </div>
        <p class="limitation">{observation.limitation}</p>
      </div>
      <div class="reasoning">
        <span class={`status ${observation.assessment}`}
          >{assessmentLabels[observation.assessment]}</span
        >
        <dl>
          <dt>Правило</dt>
          <dd class="mono">{observation.rule}</dd>
          <dt>Ожидаемое состояние</dt>
          <dd>{observation.expected}</dd>
          <dt>Наблюдаемое состояние</dt>
          <dd>{observation.observed}</dd>
        </dl>
        <p class="explanation">{observation.explanation}</p>
        <form onsubmit={save}>
          <h3>{review ? 'Изменить решение' : 'Решение ревьюера'}</h3>
          <label class="field"
            >Статус<select bind:value={decision}
              ><option value="acknowledged">Взять в работу</option><option value="dismissed"
                >Отклонить сигнал</option
              ></select
            ></label
          >
          <label class="field"
            >Комментарий<textarea
              bind:value={note}
              maxlength="1000"
              placeholder="Что проверили и какое действие нужно дальше?"
              aria-invalid={!!error}
              aria-describedby="review-error"></textarea></label
          >
          <span id="review-error" class="error-message" aria-live="polite">{error}</span>
          <button class="button primary" type="submit"
            >Сохранить решение <ArrowRightIcon size={18} /></button
          >
          <p class="local-note">
            {review ? `Сейчас: ${decisionLabels[review.decision]}. ` : ''}Только в этом браузере.
            Исходное наблюдение не изменится.
          </p>
        </form>
      </div>
    </div>
  {/if}
</dialog>

<style>
  dialog {
    width: 1120px;
  }
  .dialog-heading .mono {
    font-size: 10px;
  }
  .dialog-heading h2 {
    margin-top: 8px;
  }
  .review-grid {
    display: grid;
    grid-template-columns: 1.2fr 1fr;
  }
  .visual {
    padding: 24px;
    border-right: 1px solid var(--line);
  }
  .evidence-meta {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 10px;
    color: var(--muted);
    padding-block: 16px;
  }
  .limitation {
    font-size: 12px;
    line-height: 1.8;
    padding: 20px 0;
    border-top: 1px solid var(--line);
    color: var(--muted);
  }
  .reasoning {
    padding: 26px;
  }
  dl {
    margin: 24px 0;
  }
  dt {
    font-size: 10px;
    color: var(--muted);
    margin-top: 18px;
  }
  dd {
    margin: 7px 0 0;
    font-size: 13px;
    line-height: 1.7;
  }
  dd.mono {
    font-size: 11px;
  }
  .explanation {
    font-size: 12px;
    line-height: 1.8;
    color: var(--muted);
  }
  form {
    display: grid;
    gap: 15px;
    margin-top: 24px;
    border-top: 1px solid var(--line);
    padding-top: 24px;
  }
  form h3 {
    font-size: 16px;
    font-weight: 600;
  }
  .local-note {
    color: var(--muted);
    font-size: 10px;
    line-height: 1.7;
  }
  @media (max-width: 800px) {
    .review-grid {
      grid-template-columns: 1fr;
    }
    .visual {
      border-right: 0;
      border-bottom: 1px solid var(--line);
    }
    .dialog-heading {
      padding: 18px;
    }
    .dialog-heading h2 {
      font-size: 20px;
    }
  }
</style>
