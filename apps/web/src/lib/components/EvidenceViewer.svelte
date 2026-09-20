<script lang="ts">
  import CornersOutIcon from 'phosphor-svelte/lib/CornersOutIcon';
  import BoundingBoxIcon from 'phosphor-svelte/lib/BoundingBoxIcon';
  import type { Detection } from '$lib/demo/data';
  let {
    src,
    alt,
    detections = [],
    compact = false,
  }: { src: string; alt: string; detections?: Detection[]; compact?: boolean } = $props();
  let boxes = $state(true);
  let selected = $state(-1);
  let expanded = $state(false);
  let failed = $state(false);
  $effect(() => {
    src;
    selected = -1;
    failed = false;
  });
</script>

<div class="evidence" class:compact>
  <div class="image-window" class:expanded>
    <div class="image-plane">
      <img
        {src}
        srcset={`${src.replace('.webp', '-768.webp')} 768w, ${src} 1536w`}
        sizes="(max-width: 767px) 100vw, 65vw"
        {alt}
        width="1536"
        height="1024"
        loading="lazy"
        onerror={() => (failed = true)}
      />
      {#if failed}<div class="image-error">
          Не удалось загрузить иллюстрацию. Обновите страницу.
        </div>{/if}
      {#if boxes && !failed}
        {#each detections as detection, i}
          <button
            class="bbox"
            class:unexpected={detection.unexpected}
            class:selected={selected === i}
            aria-label={`${detection.label} ${Math.round(detection.confidence * 100)}%: уверенность демонстрационной разметки`}
            style:left={`${detection.bbox[0] * 100}%`}
            style:top={`${detection.bbox[1] * 100}%`}
            style:width={`${detection.bbox[2] * 100}%`}
            style:height={`${detection.bbox[3] * 100}%`}
            aria-pressed={selected === i}
            onclick={() => (selected = selected === i ? -1 : i)}
          >
            <span
              >{detection.label} <b class="mono">{Math.round(detection.confidence * 100)}%</b></span
            >
          </button>
        {/each}
      {/if}
    </div>
  </div>
  <div class="viewer-toolbar">
    <span class="viewer-label"
      >{selected >= 0 && detections[selected]
        ? `${detections[selected].label} · ручная демо-разметка`
        : 'Иллюстрация · не результат ML'}</span
    >
    <div>
      <button
        class="icon-button"
        aria-label={boxes ? 'Скрыть рамки объектов' : 'Показать рамки объектов'}
        aria-pressed={boxes}
        onclick={() => (boxes = !boxes)}><BoundingBoxIcon size={20} /></button
      >
      <button
        class="icon-button"
        aria-label={expanded ? 'Уменьшить снимок' : 'Увеличить снимок'}
        aria-pressed={expanded}
        onclick={() => (expanded = !expanded)}><CornersOutIcon size={20} /></button
      >
    </div>
  </div>
</div>

<style>
  .evidence {
    min-width: 0;
    background: var(--surface);
  }
  .image-window {
    overflow: hidden;
    aspect-ratio: 3/2;
    position: relative;
  }
  .image-plane {
    position: relative;
    width: 100%;
    transition: transform 350ms;
  }
  .expanded .image-plane {
    transform: scale(1.35);
    transform-origin: 48% 50%;
  }
  img {
    width: 100%;
    height: auto;
  }
  .bbox {
    position: absolute;
    border: 1.5px solid #d1ef92;
    color: #1b2412;
    padding: 0;
    background: transparent;
    border-radius: 1px;
  }
  .bbox:hover,
  .bbox.selected {
    background: rgb(198 220 145 / 0.1);
    outline: 2px solid #d1ef92;
    outline-offset: 3px;
  }
  .bbox span {
    position: absolute;
    left: -1px;
    bottom: 100%;
    display: flex;
    align-items: center;
    gap: 14px;
    background: #d1ef92;
    padding: 5px 8px;
    font-size: 11px;
    white-space: nowrap;
  }
  .bbox:active {
    transform: none;
  }
  .bbox.unexpected {
    border-color: #ff8a82;
    color: #321411;
  }
  .bbox.unexpected span {
    background: #ff8a82;
  }
  .bbox.unexpected:hover {
    outline-color: #ff8a82;
  }
  .viewer-toolbar {
    min-height: 49px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 3px 12px 3px 18px;
    border-bottom: 1px solid var(--line);
    gap: 6px;
  }
  .viewer-toolbar > div {
    display: flex;
    flex-shrink: 0;
  }
  .viewer-label {
    font-size: 11px;
    color: var(--muted);
  }
  .image-error {
    position: absolute;
    inset: 0;
    background: var(--surface);
    display: grid;
    place-content: center;
    padding: 24px;
    color: var(--warning);
  }
  .compact .image-window {
    aspect-ratio: 1.8;
  }
  .compact .image-plane {
    margin-top: -4%;
  }
  @media (max-width: 640px) {
    .viewer-toolbar {
      padding-left: 10px;
    }
    .bbox span {
      font-size: 10px;
    }
  }
</style>
