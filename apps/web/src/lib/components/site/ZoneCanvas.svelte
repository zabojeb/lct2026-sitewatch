<script lang="ts">
  import { clampPoint, splitEdge } from '$lib/site/zones';
  import type { Point, Zone } from '$lib/site/types';

  let {
    zones,
    editing,
    drawing,
    draft = $bindable(),
    onchange,
  }: {
    zones: Zone[];
    editing: boolean;
    drawing: boolean;
    draft: Point[];
    /** Called with the new zone list after every edit. */
    onchange: (zones: Zone[]) => void;
  } = $props();

  let surface = $state<HTMLDivElement>();
  let drag = $state<{
    zoneId: string;
    vertex: number | null;
    start: Point;
    original: Point[];
  } | null>(null);

  const toPercent = (event: PointerEvent | MouseEvent): Point => {
    const rect = surface!.getBoundingClientRect();
    return clampPoint([
      ((event.clientX - rect.left) / rect.width) * 100,
      ((event.clientY - rect.top) / rect.height) * 100,
    ]);
  };
  const points = (zone: Zone) => zone.points.map((p) => p.join(',')).join(' ');
  const update = (zoneId: string, next: Point[]) =>
    onchange(zones.map((z) => (z.id === zoneId ? { ...z, points: next } : z)));

  function start(event: PointerEvent, zone: Zone, vertex: number | null) {
    if (!editing || drawing) return;
    event.preventDefault();
    event.stopPropagation();
    surface!.setPointerCapture(event.pointerId);
    drag = {
      zoneId: zone.id,
      vertex,
      start: toPercent(event),
      original: zone.points.map((p) => [...p] as Point),
    };
  }
  function move(event: PointerEvent) {
    if (!drag) return;
    const p = toPercent(event);
    if (drag.vertex !== null) {
      const next = drag.original.map((q) => [...q] as Point);
      next[drag.vertex] = p;
      update(drag.zoneId, next);
    } else {
      const dx = p[0] - drag.start[0];
      const dy = p[1] - drag.start[1];
      update(
        drag.zoneId,
        drag.original.map(([x, y]) => clampPoint([x + dx, y + dy])),
      );
    }
  }
  function click(event: MouseEvent) {
    if (drawing) draft = [...draft, toPercent(event)];
  }
  const midpoint = (zone: Zone, i: number): Point => {
    const a = zone.points[i];
    const b = zone.points[(i + 1) % zone.points.length];
    return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  };
</script>

<!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
<div
  bind:this={surface}
  class="zone-canvas"
  class:editing
  class:drawing
  onpointermove={move}
  onpointerup={() => (drag = null)}
  onpointercancel={() => (drag = null)}
  onclick={click}
>
  <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
    {#each zones as zone (zone.id)}
      <polygon class="zone" points={points(zone)} onpointerdown={(e) => start(e, zone, null)} />
    {/each}
    {#if draft.length}
      <polyline class="draft" points={draft.map((p) => p.join(',')).join(' ')} />
    {/if}
  </svg>
  {#each zones as zone (zone.id)}
    <span
      class="label"
      style="left:{Math.min(...zone.points.map((p) => p[0])) + 1}%;top:{Math.min(
        ...zone.points.map((p) => p[1]),
      ) + 1}%"
    >
      {zone.name}{zone.example ? ' · пример' : ''}
    </span>
    {#if editing && !drawing}
      {#each zone.points as point, i (i)}
        {@const mid = midpoint(zone, i)}
        <button
          type="button"
          class="vertex"
          style="left:{point[0]}%;top:{point[1]}%"
          onpointerdown={(e) => start(e, zone, i)}
          aria-label="Вершина {i + 1} зоны «{zone.name}»"
        ></button>
        <button
          type="button"
          class="split"
          style="left:{mid[0]}%;top:{mid[1]}%"
          onclick={(e) => {
            e.stopPropagation();
            onchange(zones.map((z) => (z.id === zone.id ? splitEdge(z, i) : z)));
          }}
          aria-label="Добавить вершину на ребро {i + 1}">+</button
        >
      {/each}
    {/if}
  {/each}
  {#each draft as point, i (i)}
    <span class="draft-point" style="left:{point[0]}%;top:{point[1]}%"></span>
  {/each}
</div>

<style>
  .zone-canvas {
    position: absolute;
    inset: 0;
    z-index: 3;
    pointer-events: none;
  }
  .zone-canvas.editing,
  .zone-canvas.drawing {
    pointer-events: auto;
  }
  .zone-canvas.drawing {
    cursor: crosshair;
  }
  svg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  .zone {
    fill: rgb(255 138 130 / 0.2);
    stroke: var(--danger);
    stroke-width: 2;
    vector-effect: non-scaling-stroke;
    pointer-events: none;
  }
  .editing .zone {
    pointer-events: auto;
    cursor: move;
  }
  .draft {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2;
    stroke-dasharray: 6 4;
    vector-effect: non-scaling-stroke;
  }
  .label {
    position: absolute;
    padding: 3px 7px;
    border-radius: var(--radius);
    background: rgb(40 8 6 / 0.82);
    color: #ffd8d4;
    font-size: 11px;
    font-weight: 700;
    pointer-events: none;
    white-space: nowrap;
  }
  .vertex,
  .split,
  .draft-point {
    position: absolute;
    transform: translate(-50%, -50%);
  }
  .vertex {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    border: 2px solid var(--danger);
    cursor: grab;
    touch-action: none;
  }
  .split {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: rgb(20 24 18 / 0.85);
    color: #fff;
    font-size: 13px;
    line-height: 18px;
    text-align: center;
  }
  .draft-point {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--accent);
    pointer-events: none;
  }
</style>
