<script lang="ts">
  import { days, numericDate } from '$lib/site/format';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();
  const comparison = $derived(site.planComparison);
  const title = $derived(comparison?.status === 'late'
    ? `Задержка ${days(Math.abs(comparison.days))}`
    : comparison?.status === 'ahead'
      ? `Опережение ${days(Math.abs(comparison.days))}`
      : 'По плану');
</script>

{#if comparison}
  <section class="schedule-evidence" class:late={comparison.status === 'late'} class:ahead={comparison.status === 'ahead'} aria-label="Сравнение рубежа с планом">
    <div class="summary">
      <div>
        <span class="eyebrow">Демосценарий · сравнение с планом</span>
        <h2>{title}</h2>
        <p>Начало этапа «{comparison.stage.name}»</p>
      </div>
      <a href="/app/site/history" onclick={() => site.selectFrame(comparison.observation.frameId)}>Смотреть кадр ↗</a>
    </div>
    <div class="dates">
      <div><small>По плану</small><b>{numericDate(comparison.stage.start)}</b></div>
      <div class="connector" aria-hidden="true"></div>
      <div><small>Рубеж сценария</small><b>{numericDate(comparison.observation.at)}</b></div>
    </div>
    <p class="source">{comparison.observation.note} Даты и длительность плана можно изменить во вкладке «План работ» — расчёт обновится.</p>
  </section>
{/if}

<style>
  .schedule-evidence { margin: 18px 0; padding: 24px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
  .schedule-evidence.late { border-left: 4px solid var(--warning); }
  .schedule-evidence.ahead { border-left: 4px solid var(--accent); }
  .summary { display: flex; align-items: start; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
  h2 { margin: 8px 0 4px; font-size: clamp(23px, 2.5vw, 32px); letter-spacing: -.04em; }
  .summary p, .source { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
  .summary a { color: var(--text); font-size: 13px; font-weight: 700; border-bottom: 1px solid currentColor; padding-bottom: 3px; }
  .dates { display: grid; grid-template-columns: minmax(0, 1fr) minmax(24px, .25fr) minmax(0, 1fr); align-items: center; gap: 12px; margin: 24px 0 16px; }
  .dates div:not(.connector) { display: grid; gap: 6px; padding: 15px 17px; border: 1px solid var(--line); border-radius: var(--radius); }
  .dates small { color: var(--muted); font-size: 11px; }
  .dates b { font-size: 17px; font-variant-numeric: tabular-nums; }
  .connector { height: 1px; background: var(--line); }
  @media (max-width: 550px) { .schedule-evidence { padding: 16px; } .dates { gap: 5px; } .dates div:not(.connector) { padding: 12px 8px; } .dates b { font-size: 13px; } }
</style>
