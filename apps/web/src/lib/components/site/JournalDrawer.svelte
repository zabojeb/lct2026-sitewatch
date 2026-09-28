<script lang="ts">
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import { SITE } from '$lib/site/analysis';
  import { clock, duration, frames, numericDate } from '$lib/site/format';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();
  let filter = $state<'all' | 'red' | 'yellow'>('all');
  const entries = $derived(site.journal.filter((e) => filter === 'all' || e.alert.tone === filter));
  const cameraName = (id: string) =>
    id === SITE ? 'Площадка' : (site.project?.cameras.find((c) => c.id === id)?.name ?? id);
  const when = (start: number, end: number) =>
    start === end
      ? `${numericDate(start)} ${clock(start)}`
      : numericDate(start) === numericDate(end)
        ? `${numericDate(start)} ${clock(start)}–${clock(end)} · ${duration(end - start)}`
        : `${numericDate(start)} — ${numericDate(end)}`;
</script>

<aside class="drawer" aria-label="Журнал отклонений">
  <header>
    <div>
      <span class="eyebrow">Журнал отклонений</span>
      <h2>{site.journal.length} {site.journal.length === 1 ? 'запись' : 'записей'} по проекту</h2>
    </div>
    <button class="icon-button" onclick={() => (site.panel = null)} aria-label="Закрыть"
      ><XIcon size={20} /></button
    >
  </header>
  <div class="drawer-body">
    <div class="filters" role="group" aria-label="Фильтр">
      <button class:active={filter === 'all'} onclick={() => (filter = 'all')}>Все</button>
      <button class:active={filter === 'red'} onclick={() => (filter = 'red')}>Критичные</button>
      <button class:active={filter === 'yellow'} onclick={() => (filter = 'yellow')}
        >Проверить</button
      >
    </div>
    {#each entries as entry (entry.key + entry.start)}
      <button class="alert entry" onclick={() => (site.evidenceFrameId = entry.frameIds.at(-1)!)}>
        <i class="dot {entry.alert.tone}"></i>
        <span>
          <b>{entry.alert.title}</b>
          <small>{entry.alert.message}</small>
          <small
            >{cameraName(entry.cameraId)} · {when(entry.start, entry.end)} · {frames(
              entry.frameIds.length,
            )}</small
          >
        </span>
        <span class="open">Кадр →</span>
      </button>
    {:else}
      <div class="quiet-state">
        <b>Отклонений нет</b><span>По всем кадрам проекта правила выполнены.</span>
      </div>
    {/each}
    <p class="hint">
      Журнал пересчитывается по всем кадрам проекта при каждом изменении плана, профилей и зон.
      Повторы одной находки объединяются: «Площадка» — выводы по срезу всех камер, остальное — по
      конкретной камере.
    </p>
  </div>
</aside>

<style>
  .filters {
    display: flex;
    gap: 6px;
  }
  .filters button {
    padding: 6px 12px;
    border: 1px solid var(--line);
    border-radius: 999px;
    font-size: 12px;
    color: var(--muted);
  }
  .filters button.active {
    border-color: var(--accent);
    color: var(--text);
  }
  .entry {
    width: 100%;
    text-align: left;
  }
  .entry:hover {
    outline: 1px solid var(--line);
  }
  .open {
    font-size: 12px;
    color: var(--accent);
    white-space: nowrap;
  }
</style>
