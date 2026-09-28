<script lang="ts">
  import { DAY, clock, days, frames, numericDate, percent, shortDate } from '$lib/site/format';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();

  // One axis for the plan, the observed stages and the reasons, padded by a few days.
  const span = $derived.by(() => {
    const points = [
      ...site.windows.flatMap((w) => [w.start, w.end]),
      ...site.segments.flatMap((s) => [s.start, s.end]),
    ];
    if (!points.length) return { start: 0, end: 1, length: 1 };
    const start = Math.min(...points) - 2 * DAY;
    const end = Math.max(...points) + 2 * DAY;
    return { start, end, length: end - start };
  });
  const x = (value: number) => ((value - span.start) / span.length) * 100;
  const width = (a: number, b: number) => Math.max(0.6, x(b) - x(a));
  const profileIndex = (id: string) =>
    Math.max(
      0,
      site.profiles.findIndex((p) => p.id === id),
    ) % 6;
  const now = $derived(site.at);
</script>

<section class="timeline" aria-label="План и наблюдения">
  <div class="axis">
    <span>{shortDate(span.start)}</span>
    <span>{shortDate(span.start + span.length / 2)}</span>
    <span>{shortDate(span.end)}</span>
  </div>

  <div class="lane">
    <span class="lane-label">План</span>
    <div class="track">
      {#each site.windows as w (w.id)}
        <button
          type="button"
          class="seg plan c{profileIndex(w.profileId)}"
          style="left:{x(w.start)}%;width:{width(w.start, w.end)}%"
          onclick={() =>
            document
              .getElementById(`stage-${w.id}`)
              ?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
          aria-label="{w.name}: {numericDate(w.start)} — {numericDate(w.end)}"
        >
          <b>{w.name}</b>
          <span class="tip"
            ><strong>{w.name}</strong>{numericDate(w.start)} — {numericDate(w.end)} · {days(
              w.days,
            )}{w.row ? ` · строка ${w.row}` : ''}</span
          >
        </button>
      {/each}
    </div>
  </div>

  <div class="lane">
    <span class="lane-label">По камерам</span>
    <div class="track">
      {#each site.segments as s (s.start)}
        <button
          type="button"
          class="seg observed c{profileIndex(s.profile.id)}"
          style="left:{x(s.start)}%;width:{width(s.start, s.end)}%"
          onclick={() => (site.evidenceFrameId = s.frameIds.at(-1)!)}
          aria-label="{s.profile.name}: {numericDate(s.start)} — {numericDate(s.end)}"
        >
          <b>{s.profile.name}</b>
          <span class="tip">
            <strong>{s.profile.name}</strong>{numericDate(s.start)} — {numericDate(s.end)} · совпадение
            {percent(s.score)} · {frames(s.frameIds.length)}
            <br /><em>Нажмите, чтобы открыть последний кадр</em>
          </span>
        </button>
      {/each}
    </div>
  </div>

  {#each site.reasons as band (band.label)}
    <div class="lane reason">
      <span class="lane-label">{band.label}</span>
      <div class="track thin">
        {#each band.intervals as interval (interval.start)}
          <button
            class="seg band {band.tone}"
            style="left:{x(interval.start)}%;width:{width(interval.start, interval.end)}%"
            onclick={() => (site.evidenceFrameId = interval.entries.at(-1)!.frameIds.at(-1)!)}
            aria-label="{band.label}: {numericDate(interval.start)}"
          >
            <span class="tip">
              <strong>{band.label}</strong>
              {numericDate(interval.start)}
              {clock(interval.start)} — {numericDate(interval.end)}
              {clock(interval.end)}
              {#each interval.entries.slice(0, 3) as entry (entry.key)}<br />{entry.alert
                  .message}{/each}
              <br /><em>Нажмите, чтобы открыть кадр</em>
            </span>
          </button>
        {/each}
      </div>
    </div>
  {/each}

  {#if now >= span.start && now <= span.end}
    <i class="now" style="left:calc(112px + (100% - 112px) * {x(now) / 100})" title="Выбранный кадр"
    ></i>
  {/if}
  <p class="legend">
    Сверху — плановые этапы, ниже — этап дня по составу техники всех камер и интервалы, когда
    срабатывали правила. Одинаковый цвет — один профиль техники.
  </p>
</section>

<style>
  .timeline {
    position: relative;
    display: grid;
    gap: 6px;
    padding: 16px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--surface);
  }
  .axis {
    display: flex;
    justify-content: space-between;
    margin-left: 112px;
    font: 10px var(--mono);
    color: var(--muted);
  }
  .lane {
    display: grid;
    grid-template-columns: 104px 1fr;
    gap: 8px;
    align-items: center;
  }
  .lane-label {
    font-size: 12px;
    color: var(--muted);
    line-height: 1.2;
  }
  .reason .lane-label {
    font-size: 11px;
  }
  .track {
    position: relative;
    height: 40px;
    border-radius: var(--radius);
    background: var(--raised);
  }
  .track.thin {
    height: 16px;
  }
  .seg {
    position: absolute;
    top: 3px;
    bottom: 3px;
    display: flex;
    align-items: center;
    padding: 0 8px;
    border-radius: 3px;
    font-size: 11px;
    color: #10140e;
    outline: none;
  }
  .seg b {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .seg.plan {
    opacity: 0.55;
  }
  .seg.observed {
    box-shadow: inset 0 0 0 2px rgb(0 0 0 / 0.25);
  }
  .c0 {
    background: #c6dc91;
  }
  .c1 {
    background: #9fc6e0;
  }
  .c2 {
    background: #e3c07d;
  }
  .c3 {
    background: #d9a3c4;
  }
  .c4 {
    background: #a8d8c0;
  }
  .c5 {
    background: #d6c9a8;
  }
  .seg.band {
    top: 2px;
    bottom: 2px;
    padding: 0;
    min-width: 6px;
  }
  .seg.band.red {
    background: var(--danger);
  }
  .seg.band.yellow {
    background: var(--warning);
  }
  .tip {
    position: absolute;
    left: 0;
    bottom: calc(100% + 6px);
    z-index: 5;
    display: none;
    width: max-content;
    max-width: 320px;
    padding: 8px 10px;
    border-radius: var(--radius);
    background: #0d110c;
    color: #eef0e7;
    font-size: 11px;
    line-height: 1.45;
    white-space: normal;
    text-align: left;
  }
  .tip strong {
    display: block;
    margin-bottom: 2px;
  }
  .tip em {
    color: #b8c49c;
  }
  .seg:hover .tip,
  .seg:focus-visible .tip {
    display: block;
  }
  .seg:hover,
  .seg:focus-visible {
    z-index: 4;
  }
  .now {
    position: absolute;
    top: 30px;
    bottom: 34px;
    width: 2px;
    margin-left: -1px;
    background: var(--text);
    opacity: 0.6;
    pointer-events: none;
  }
  .legend {
    margin: 6px 0 0;
    font-size: 11px;
    color: var(--muted);
  }
  @media (max-width: 560px) {
    .axis {
      margin-left: 0;
    }
    .lane {
      grid-template-columns: 1fr;
      gap: 2px;
    }
    .now {
      display: none;
    }
  }
</style>
