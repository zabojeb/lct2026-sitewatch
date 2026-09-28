<script lang="ts">
  import type { Snippet } from 'svelte';
  import { equipmentName, isMachine, SOURCE_LABELS } from '$lib/site/catalog';
  import type { Tone } from '$lib/site/analysis';
  import type { SiteFrame, Zone } from '$lib/site/types';

  let {
    frame,
    tones = [],
    zones = [],
    alt,
    overlay,
  }: {
    frame: SiteFrame;
    tones?: { tone: Tone; messages: string[] }[];
    /** Forbidden zones drawn under the boxes (read-only). */
    zones?: Zone[];
    alt: string;
    /** Extra layer above the image, e.g. the zone editor. */
    overlay?: Snippet;
  } = $props();

  let loaded = $state(false);
  let current = $state('');
  $effect(() => {
    if (frame.image !== current) {
      current = frame.image;
      loaded = false;
    }
  });

  const place = ([cx, cy, w, h]: number[]) =>
    `left:${(cx - w / 2) * 100}%;top:${(cy - h / 2) * 100}%;width:${w * 100}%;height:${h * 100}%`;
</script>

<div
  class="frame"
  style={frame.preview ? `background-image:url('${frame.preview}')` : undefined}
  data-frame={frame.id}
>
  <img src={frame.image} {alt} class:loaded decoding="async" onload={() => (loaded = true)} />
  {#if zones.length}
    <svg class="zones-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      {#each zones as zone (zone.id)}
        <polygon points={zone.points.map((p) => p.join(',')).join(' ')} />
      {/each}
    </svg>
  {/if}
  {#each frame.boxes as box, index (index)}
    {@const state = tones[index] ?? { tone: 'green', messages: [] }}
    {@const label = [equipmentName(box.slug), ...state.messages].join(' · ')}
    {#if isMachine(box.slug)}
      <button
        type="button"
        class="box {state.tone}"
        class:synthetic={box.source === 'synthetic'}
        style={place(box.bbox)}
        aria-label={label}
      >
        <span class="tip">
          <b>{equipmentName(box.slug)}</b> · {SOURCE_LABELS[box.source]}
          {#each state.messages as message (message)}<br />{message}{/each}
        </span>
      </button>
    {:else}
      <div class="box person" style={place(box.bbox)} aria-hidden="true"></div>
    {/if}
  {/each}
  {@render overlay?.()}
</div>

<style>
  .zones-layer {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }
  .zones-layer polygon {
    fill: rgb(255 138 130 / 0.16);
    stroke: var(--danger);
    stroke-width: 0.35;
    stroke-dasharray: 1.2 0.8;
    vector-effect: non-scaling-stroke;
  }
</style>
