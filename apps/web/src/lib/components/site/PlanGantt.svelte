<script lang="ts">
  import { DAY, days, numericDate, time } from '$lib/site/format';
  import { useSite } from '$lib/site/store.svelte';

  let { onpick }: { onpick?: (id: string) => void } = $props();
  const site = useSite();

  const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
  const monthStart = (at: number, shift = 0) => {
    const date = new Date(at);
    return new Date(date.getFullYear(), date.getMonth() + shift, 1).getTime();
  };
  const dayMonth = (at: number) => numericDate(at).slice(0, 5);

  const comparison = $derived(site.planComparison);
  const factAt = $derived(
    comparison ? time(`${comparison.observation.at.slice(0, 10)}T00:00:00`) : null,
  );
  const planStart = $derived(site.windows[0]?.start ?? 0);
  const planEnd = $derived(site.windows.at(-1)?.end ?? 0);
  // Markers far from the plan would squeeze the bars; they are listed in the legend instead.
  const near = (at: number | null) =>
    at !== null && at > 0 && at >= planStart - 120 * DAY && at <= planEnd + 120 * DAY;
  const shot = $derived.by(() => {
    const stamps = (site.project?.frames ?? []).map((frame) => time(frame.timestamp));
    return stamps.length ? { start: Math.min(...stamps), end: Math.max(...stamps) } : null;
  });

  // While a bar is dragged the scale stays put, so the edge follows the pointer.
  let frozen = $state<{ start: number; end: number } | null>(null);
  const span = $derived.by(() => {
    if (frozen) return frozen;
    const points = [planStart, planEnd];
    if (near(factAt)) points.push(factAt!);
    if (near(site.at)) points.push(site.at);
    return { start: monthStart(Math.min(...points)), end: monthStart(Math.max(...points) - 1, 1) };
  });
  const x = (at: number) => ((at - span.start) / (span.end - span.start)) * 100;
  const clamp = (value: number) => Math.min(100, Math.max(0, value));

  let trackWidth = $state(0);
  const months = $derived.by(() => {
    const out: { at: number; next: number; label: string; year: number | null }[] = [];
    for (let at = span.start; at < span.end; at = monthStart(at, 1)) {
      const date = new Date(at);
      const first = at === span.start || date.getMonth() === 0;
      out.push({ at, next: monthStart(at, 1), label: MONTHS[date.getMonth()], year: first ? date.getFullYear() : null });
    }
    return out;
  });
  const every = $derived(Math.max(1, Math.ceil((months.length * 58) / Math.max(trackWidth, 1))));

  const labelInside = (start: number, end: number) =>
    ((100 - x(end)) / 100) * trackWidth < 72 && ((x(end) - x(start)) / 100) * trackWidth > 80;

  const elapsed = (start: number, end: number) =>
    !site.at ? 0 : Math.min(1, Math.max(0, (site.at - start) / (end - start)));

  /* ---------- duration by dragging the right edge ---------- */
  let dragIndex = $state<number | null>(null);
  let origin = { x: 0, days: 0 };
  function grab(event: PointerEvent, index: number) {
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    frozen = { ...span };
    origin = { x: event.clientX, days: site.plan.stages[index].days };
    dragIndex = index;
  }
  function pull(event: PointerEvent) {
    if (dragIndex === null || !frozen || !trackWidth) return;
    const shift = Math.round(((event.clientX - origin.x) / trackWidth) * ((frozen.end - frozen.start) / DAY));
    const next = Math.max(1, origin.days + shift);
    if (site.plan.stages[dragIndex].days !== next) site.plan.stages[dragIndex].days = next;
  }
  function release() {
    dragIndex = null;
    frozen = null;
  }
  function nudge(event: KeyboardEvent, index: number) {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const stage = site.plan.stages[index];
    stage.days = Math.max(1, stage.days + step * (event.shiftKey ? 7 : 1));
  }
</script>

<figure class="gantt" class:dragging={dragIndex !== null} aria-label="Диаграмма Ганта календарного плана">
  <div class="scroller">
  <div class="grid">
    <div class="corner">
      <span class="eyebrow">Этап</span>
    </div>
    <div class="axis" bind:clientWidth={trackWidth}>
      {#each months as month, i (month.at)}
        <span class="month" style="left:{x(month.at)}%; width:{x(month.next) - x(month.at)}%">
          {#if i % every === 0}{month.label}{#if month.year}<small>{month.year}</small>{/if}{/if}
        </span>
      {/each}
      {#if near(site.at)}
        <span class="chip now-chip" style="left:{x(site.at)}%">кадр {dayMonth(site.at)}</span>
      {/if}
    </div>

    <div class="rows">
      <div class="layer" aria-hidden="true">
        {#each months as month (month.at)}<i class="gridline" style="left:{x(month.at)}%"></i>{/each}
        {#if shot && near(shot.start)}
          <i
            class="shot"
            style="left:{clamp(x(shot.start))}%; width:{Math.max(0.4, clamp(x(shot.end)) - clamp(x(shot.start)))}%"
          ></i>
        {/if}
        {#if near(site.at)}<i class="now" style="left:{x(site.at)}%"></i>{/if}
      </div>

      {#each site.windows as w, i (w.id)}
        {@const progress = elapsed(w.start, w.end)}
        {@const fact = comparison && comparison.stage.id === w.id && near(factAt) ? comparison : null}
        <div class="row" class:current={site.plannedWindow?.id === w.id} style="--i:{i}">
          <button class="label" type="button" onclick={() => onpick?.(w.id)} title={w.name}>
            <b class="num">{i + 1}</b>
            <span>{w.name}</span>
          </button>
          <div class="track">
            <div
              class="bar"
              class:done={progress === 1}
              class:future={progress === 0}
              style="left:{x(w.start)}%; width:{Math.max(0.35, x(w.end) - x(w.start))}%"
            >
              <button
                class="body"
                type="button"
                onclick={() => onpick?.(w.id)}
                aria-label="{w.name}: {numericDate(w.start)} — {numericDate(w.end)}, {days(w.days)}"
              >
                <span class="fill" style="width:{progress * 100}%"></span>
              </button>
              <span
                class="grip"
                role="slider"
                tabindex="0"
                aria-label="Длительность этапа «{w.name}»"
                aria-valuemin={1}
                aria-valuenow={w.days}
                aria-valuetext={days(w.days)}
                onpointerdown={(event) => grab(event, i)}
                onpointermove={pull}
                onpointerup={release}
                onpointercancel={release}
                onkeydown={(event) => nudge(event, i)}
              ></span>
              <span class="tip" role="tooltip">
                <strong>{w.name}</strong>
                {numericDate(w.start)} — {numericDate(w.end)} · {days(w.days)}
                <em>Потяните правый край, чтобы изменить длительность</em>
              </span>
            </div>
            <span class="duration" class:inside={labelInside(w.start, w.end)} style="left:{x(w.end)}%">
              {days(w.days)}
            </span>
            {#if fact && factAt !== null}
              {@const from = Math.min(x(w.start), x(factAt))}
              {@const to = Math.max(x(w.start), x(factAt))}
              <span
                class="shift"
                class:late={fact.status === 'late'}
                style="left:{from}%; width:{Math.max(0.2, to - from)}%"
                aria-hidden="true"
              ></span>
              <a
                class="fact"
                class:late={fact.status === 'late'}
                href="/app/site/history"
                style="left:{x(factAt)}%"
                onclick={() => site.selectFrame(fact.observation.frameId)}
                aria-label="Факт по сценарию: {numericDate(factAt)}. Открыть кадр"
              >
                <i></i>
                <span
                  >{fact.status === 'late' ? '+' : fact.status === 'ahead' ? '−' : ''}{days(
                    Math.abs(fact.days),
                  )}</span
                >
              </a>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
  </div>

  <figcaption class="legend">
    <span><i class="key bar-key"></i>План этапа</span>
    <span><i class="key fill-key"></i>Прошло по графику к дате кадра</span>
    {#if comparison && near(factAt)}
      <span
        ><i class="key fact-key" class:late={comparison.status === 'late'}></i>Факт начала по сценарию:
        {numericDate(factAt!)}</span
      >
    {/if}
    {#if shot && near(shot.start)}<span><i class="key shot-key"></i>Период съёмки камер</span>{/if}
    {#if site.at && !near(site.at)}<span>Кадр {numericDate(site.at)} — вне периода плана</span>{/if}
  </figcaption>
</figure>

<style>
  .gantt {
    --label: 240px;
    --row: 44px;
    margin: 0 0 16px;
    padding: 14px 16px 12px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--surface);
  }
  .grid {
    display: grid;
    grid-template-columns: var(--label) minmax(0, 1fr);
  }
  @media (min-width: 1280px) {
    .gantt {
      --label: 300px;
    }
  }
  .corner {
    display: flex;
    align-items: end;
    padding-bottom: 8px;
  }
  .axis {
    position: relative;
    height: 44px;
    border-bottom: 1px solid var(--line);
  }
  .month {
    position: absolute;
    bottom: 6px;
    padding-left: 6px;
    overflow: hidden;
    white-space: nowrap;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--muted);
    transition: left 0.35s cubic-bezier(0.2, 0.8, 0.2, 1), width 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .month small {
    margin-left: 4px;
    font-weight: 500;
    opacity: 0.75;
  }
  .chip {
    position: absolute;
    top: 0;
    transform: translateX(-50%);
    padding: 2px 7px;
    border-radius: 999px;
    white-space: nowrap;
    font-size: 11px;
    font-weight: 700;
    background: var(--text);
    color: var(--bg);
    transition: left 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .rows {
    grid-column: 1 / -1;
    position: relative;
  }
  .layer {
    position: absolute;
    inset: 0 0 0 var(--label);
    pointer-events: none;
  }
  .gridline,
  .now,
  .shot {
    position: absolute;
    top: 0;
    bottom: 0;
    transition: left 0.35s cubic-bezier(0.2, 0.8, 0.2, 1), width 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .gridline {
    width: 1px;
    background: var(--line);
    opacity: 0.55;
  }
  .shot {
    background: repeating-linear-gradient(135deg, transparent 0 6px, var(--raised) 6px 8px);
    opacity: 0.7;
  }
  .now {
    width: 2px;
    margin-left: -1px;
    background: var(--text);
    opacity: 0.85;
  }
  .row {
    display: grid;
    grid-template-columns: var(--label) minmax(0, 1fr);
    height: var(--row);
    border-bottom: 1px solid color-mix(in srgb, var(--line) 55%, transparent);
  }
  .row:last-child {
    border-bottom: 0;
  }
  .label {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    padding: 0 12px 0 0;
    text-align: left;
    font-size: 13px;
    color: var(--text);
  }
  .label span {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .label:hover span {
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .num {
    flex: none;
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--raised);
    font-size: 11px;
  }
  .row.current .num {
    background: var(--accent);
    color: var(--accent-ink);
  }
  .track {
    position: relative;
  }
  .bar {
    position: absolute;
    top: 11px;
    height: 22px;
    transition: left 0.35s cubic-bezier(0.2, 0.8, 0.2, 1), width 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
    animation: grow 0.55s cubic-bezier(0.2, 0.8, 0.2, 1) both;
    animation-delay: calc(var(--i) * 70ms);
    transform-origin: left center;
  }
  .body {
    position: absolute;
    inset: 0;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
    border-radius: 6px;
    background: var(--accent-soft);
    cursor: pointer;
  }
  .fill {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--accent);
    transition: width 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .bar.done .fill {
    opacity: 0.55;
  }
  .row.current .body {
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent);
  }
  .grip {
    position: absolute;
    top: -3px;
    right: -6px;
    width: 12px;
    height: 28px;
    cursor: ew-resize;
    touch-action: none;
    border-radius: 4px;
  }
  .grip::after {
    content: '';
    position: absolute;
    top: 7px;
    left: 5px;
    width: 2px;
    height: 14px;
    border-radius: 1px;
    background: var(--text);
    opacity: 0;
    transition: opacity 0.15s;
  }
  .bar:hover .grip::after,
  .grip:focus-visible::after,
  .dragging .grip::after {
    opacity: 0.8;
  }
  .grip:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
  .tip {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 0;
    z-index: 3;
    display: grid;
    gap: 3px;
    min-width: 220px;
    padding: 8px 10px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--raised);
    font-size: 12px;
    color: var(--text);
    opacity: 0;
    transform: translateY(4px);
    pointer-events: none;
    transition: opacity 0.15s, transform 0.15s;
  }
  .tip em {
    font-style: normal;
    color: var(--muted);
    font-size: 11px;
  }
  .bar:hover .tip,
  .bar:focus-within .tip {
    opacity: 1;
    transform: none;
  }
  .dragging .tip {
    opacity: 1;
    transform: none;
  }
  .duration {
    position: absolute;
    top: 13px;
    margin-left: 8px;
    white-space: nowrap;
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    pointer-events: none;
    transition: left 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .duration.inside {
    margin-left: 0;
    transform: translateX(calc(-100% - 10px));
    color: var(--accent-ink);
    font-weight: 700;
  }
  .shift {
    position: absolute;
    top: 21px;
    height: 0;
    border-top: 2px dashed var(--accent);
    transition: left 0.35s cubic-bezier(0.2, 0.8, 0.2, 1), width 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
    pointer-events: none;
  }
  .shift.late {
    border-top-color: var(--danger);
  }
  .fact {
    position: absolute;
    top: 0;
    bottom: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    transform: translateX(-7px);
    transition: left 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .fact i {
    width: 14px;
    height: 14px;
    transform: rotate(45deg);
    border: 2px solid var(--bg);
    border-radius: 2px;
    background: var(--accent);
  }
  .fact.late i {
    background: var(--danger);
  }
  .fact span {
    margin-left: 6px;
    padding: 1px 6px;
    border-radius: 999px;
    white-space: nowrap;
    font-size: 11px;
    font-weight: 700;
    background: var(--accent);
    color: var(--accent-ink);
    transform: translateY(-15px);
  }
  .fact.late span {
    background: var(--danger);
    color: #2a0d0b;
  }
  .fact:hover i {
    outline: 2px solid var(--text);
    outline-offset: 1px;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
    margin-top: 12px;
    font-size: 12px;
    color: var(--muted);
  }
  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }
  .key {
    display: inline-block;
    width: 18px;
    height: 10px;
    border-radius: 3px;
  }
  .bar-key {
    border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
    background: var(--accent-soft);
  }
  .fill-key {
    background: var(--accent);
  }
  .fact-key {
    width: 10px;
    transform: rotate(45deg);
    background: var(--accent);
  }
  .fact-key.late {
    background: var(--danger);
  }
  .shot-key {
    background: repeating-linear-gradient(135deg, transparent 0 3px, var(--muted) 3px 4px);
  }
  .dragging .bar,
  .dragging .fill,
  .dragging .duration,
  .dragging .shift,
  .dragging .fact {
    transition: none;
  }
  @keyframes grow {
    from {
      transform: scaleX(0);
      opacity: 0;
    }
  }
  @media (max-width: 760px) {
    .gantt {
      --label: 128px;
      padding: 12px 10px 10px;
    }
    /* Phones scroll the timeline sideways; stage names stay pinned on the left. */
    .scroller {
      overflow-x: auto;
      overscroll-behavior-x: contain;
    }
    .grid {
      min-width: 620px;
    }
    .corner,
    .label {
      position: sticky;
      left: 0;
      z-index: 2;
      background: var(--surface);
    }
    .label {
      font-size: 12px;
      gap: 6px;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .bar,
    .fill,
    .month,
    .chip,
    .gridline,
    .now,
    .shot,
    .duration,
    .shift,
    .fact {
      transition: none;
      animation: none;
    }
  }
</style>
