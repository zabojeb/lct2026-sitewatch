<script lang="ts">
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import FrameView from './FrameView.svelte';
  import { analyzeFrame } from '$lib/site/analysis';
  import { fullDateTime, time } from '$lib/site/format';
  import { windowAt } from '$lib/site/plan';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();
  const frame = $derived(site.project?.frames.find((f) => f.id === site.evidenceFrameId) ?? null);
  const camera = $derived(site.project?.cameras.find((c) => c.id === frame?.cameraId));
  const analysis = $derived(
    site.project && frame
      ? analyzeFrame(
          site.project,
          frame,
          site.profile(windowAt(site.windows, time(frame.timestamp))?.profileId),
          site.profiles,
          site.zones[frame.cameraId] ?? [],
        )
      : null,
  );
  const close = () => (site.evidenceFrameId = null);
  function openInConsole() {
    if (frame) site.selectFrame(frame.id);
    site.panel = null;
    close();
  }
</script>

<svelte:window onkeydown={(event) => event.key === 'Escape' && close()} />

{#if frame && analysis}
  <div
    class="backdrop"
    role="presentation"
    onclick={(event) => event.target === event.currentTarget && close()}
  >
    <div class="dialog" role="dialog" aria-modal="true" aria-label="Кадр-доказательство">
      <header>
        <div>
          <span class="eyebrow">Кадр-доказательство</span>
          <h2>{camera?.name} · {fullDateTime(frame.timestamp)}</h2>
        </div>
        <button class="icon-button" onclick={close} aria-label="Закрыть"><XIcon size={20} /></button
        >
      </header>
      <div class="dialog-body evidence">
        <FrameView
          {frame}
          tones={analysis.boxTones}
          zones={site.zones[frame.cameraId] ?? []}
          alt="Кадр {camera?.name} {fullDateTime(frame.timestamp)}"
        />
        <div class="alerts">
          {#each analysis.alerts as alert, index (`${alert.code}:${alert.message}:${index}`)}
            <div class="alert">
              <i class="dot {alert.tone}"></i>
              <span><b>{alert.title}</b><small>{alert.message}</small></span>
              <span></span>
            </div>
          {:else}
            <div class="quiet-state"><b>На этом кадре отклонений нет</b></div>
          {/each}
          <button class="button secondary" onclick={openInConsole}>Открыть в контроле</button>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .evidence {
    grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr);
    align-items: start;
  }
  @media (max-width: 760px) {
    .evidence {
      grid-template-columns: 1fr;
    }
  }
</style>
