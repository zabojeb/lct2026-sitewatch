<script lang="ts">
  import ArrowUpRightIcon from 'phosphor-svelte/lib/ArrowUpRightIcon';
  import { equipment, type Stage } from '$lib/demo/workspace';
  let { detailed = false, plan }: { detailed?: boolean; plan: Stage[] } = $props();
  let selected = $state(0);
  const first = $derived(Math.min(...plan.map((s) => Date.parse(s.start))));
  const last = $derived(Math.max(...plan.map((s) => Date.parse(s.end))));
  const days = $derived(Math.round((last - first) / 86400000) + 1);
  const stages = $derived(
    plan.map((s) => ({
      ...s,
      dates: `${s.start} — ${s.end}`,
      start: Math.round((Date.parse(s.start) - first) / 86400000),
      span: Math.round((Date.parse(s.end) - Date.parse(s.start)) / 86400000) + 1,
      equipment: s.observable
        ? `Обязательная: ${s.required.map((e) => equipment[e]).join(', ') || 'не задана'}`
        : 'Не оценивается по внешней камере',
    })),
  );
</script>

<section class="schedule" aria-labelledby="schedule-title">
  <div class="section-title">
    <h2 id="schedule-title">План работ</h2>
    <span>Сроки из локального плана <span class="muted">/ демо</span></span>
  </div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex (The scroll region must be keyboard-scrollable.) -->
  <div
    class="schedule-scroll"
    tabindex="0"
    role="region"
    aria-label="Календарный план, прокручивается горизонтально"
  >
    <div class="schedule-table">
      <div
        class="schedule-head"
        style:grid-template-columns={`230px repeat(${Math.min(days, 17)}, 1fr)`}
      >
        <span>Этап строительства</span
        >{#each Array.from({ length: Math.min(days, 17) }, (_, i) => new Date(first + Math.floor((i * days) / Math.min(days, 17)) * 86400000)) as day}<span
            >{day.getUTCDate()}</span
          >{/each}
      </div>
      {#each stages as stage, i}
        <div class="schedule-row">
          <button class:selected={selected === i} onclick={() => (selected = i)}
            >{stage.name}<ArrowUpRightIcon size={14} /></button
          >
          <div class="track">
            <button
              aria-label={`${stage.name}: ${stage.dates}. Показать требования`}
              class="stage-bar"
              class:unobservable={!stage.observable}
              style:margin-left={`${(stage.start / days) * 100}%`}
              style:width={`${(stage.span / days) * 100}%`}
              onclick={() => (selected = i)}>{stage.dates}</button
            >
          </div>
        </div>
      {/each}
    </div>
  </div>
  <div class="schedule-detail" aria-live="polite">
    <strong>{stages[selected].name}</strong><span>{stages[selected].equipment}</span><span
      class="status"
      >{stages[selected].observable
        ? 'Сопоставление по технике'
        : 'Нужен другой источник данных'}</span
    >
  </div>
  {#if detailed}<p class="schedule-note">
      План содержит демонстрационные сроки. Наличие техники не подтверждает процент готовности
      этапа. Для внутренних работ внешний ракурс не используется как доказательство.
    </p>{/if}
</section>

<style>
  .schedule {
    margin-top: 32px;
  }
  .section-title {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: center;
    margin-bottom: 22px;
  }
  h2 {
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.04em;
  }
  .section-title > span {
    font-size: 11px;
    color: var(--muted);
  }
  .schedule-scroll {
    overflow-x: auto;
  }
  .schedule-table {
    min-width: 760px;
  }
  .schedule-head {
    display: grid;
    grid-template-columns: 230px repeat(17, 1fr);
    padding-bottom: 13px;
    font-size: 10px;
    color: var(--muted);
  }
  .schedule-head > span:not(:first-child) {
    text-align: center;
  }
  .schedule-row {
    display: grid;
    grid-template-columns: 230px 1fr;
    border-top: 1px solid var(--line);
    min-height: 57px;
    align-items: center;
  }
  .schedule-row > button {
    display: flex;
    align-items: center;
    gap: 14px;
    font-size: 12px;
    text-align: left;
    padding: 10px 0;
  }
  .schedule-row > button.selected {
    font-weight: 750;
  }
  .track {
    display: block;
    padding-right: 0;
  }
  .stage-bar {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
    font-size: 10px;
    padding: 9px 13px;
    background: var(--accent-soft);
    color: var(--text);
    border-left: 2px solid var(--accent);
    border-radius: 2px;
  }
  .stage-bar:hover {
    background: var(--raised);
  }
  .stage-bar.unobservable {
    background: var(--raised);
    border-color: var(--muted);
    color: var(--muted);
  }
  .schedule-detail {
    display: flex;
    gap: 20px;
    align-items: center;
    margin-top: 12px;
    border-top: 1px solid var(--line);
    padding-top: 20px;
    font-size: 11px;
    flex-wrap: wrap;
  }
  .schedule-detail > span:not(.status) {
    color: var(--muted);
  }
  .schedule-detail .status {
    margin-left: auto;
  }
  .schedule-note {
    font-size: 13px;
    line-height: 1.8;
    color: var(--muted);
    max-width: 730px;
    margin-top: 26px;
  }
  @media (max-width: 640px) {
    .section-title {
      align-items: start;
      flex-direction: column;
      gap: 8px;
    }
    .schedule-detail {
      gap: 10px;
    }
    .schedule-detail .status {
      margin-left: 0;
    }
  }
</style>
