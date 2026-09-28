<script lang="ts">
  import { useSite } from '$lib/site/store.svelte';
  import { clock, numericDate, shortDate, time } from '$lib/site/format';

  const site = useSite();
  const project = $derived(site.project!);

  const span = $derived.by(() => {
    const times = project.frames.map((f) => time(f.timestamp));
    const start = Math.min(...times);
    const end = Math.max(...times);
    return { start, end, length: Math.max(1, end - start) };
  });
  const oneDay = $derived(numericDate(span.start) === numericDate(span.end));
  const label = (value: number) => (oneDay ? clock(value) : shortDate(value));
  const left = (value: number) => 2 + ((value - span.start) / span.length) * 96;
  const alertFrames = $derived(new Set(site.journal.flatMap((e) => e.frameIds)));
</script>

<section class="shift" aria-label="Кадры всех камер по времени">
  <div class="axis">
    <span>{label(span.start)}</span>
    <span>{label(span.start + span.length / 2)}</span>
    <span>{label(span.end)}</span>
  </div>
  {#each project.cameras as camera (camera.id)}
    <div class="lane" class:active={camera.id === site.cameraId}>
      <button class="lane-name" onclick={() => site.selectCamera(camera.id)}>{camera.name}</button>
      <div class="track">
        {#each project.frames.filter((f) => f.cameraId === camera.id) as frame (frame.id)}
          <button
            class="tick"
            class:current={frame.id === site.frame?.id}
            class:flagged={alertFrames.has(frame.id)}
            style="left:{left(time(frame.timestamp))}%"
            onclick={() => site.selectFrame(frame.id)}
            aria-label="{camera.name}, {numericDate(frame.timestamp)} {clock(frame.timestamp)}"
            title="{camera.name} · {numericDate(frame.timestamp)} {clock(frame.timestamp)}"
          ></button>
        {/each}
      </div>
    </div>
  {/each}
  <p class="legend">
    <span><i class="tick-key"></i> кадр</span>
    <span><i class="tick-key flagged"></i> есть отклонение</span>
    <span
      >Срез площадки на момент кадра — последний кадр каждой камеры за {project.shiftHours >= 48
        ? `${Math.round(project.shiftHours / 24)} дн.`
        : `${project.shiftHours} ч`}</span
    >
  </p>
</section>

<style>
  .shift {
    display: grid;
    gap: 6px;
    padding: 14px 16px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--surface);
  }
  .axis {
    display: flex;
    justify-content: space-between;
    margin-left: 108px;
    font: 10px var(--mono);
    color: var(--muted);
  }
  .lane {
    display: grid;
    grid-template-columns: 100px 1fr;
    align-items: center;
    gap: 8px;
  }
  .lane-name {
    text-align: left;
    font-size: 12px;
    color: var(--muted);
    padding: 4px 0;
  }
  .lane.active .lane-name {
    color: var(--text);
    font-weight: 700;
  }
  .track {
    position: relative;
    height: 26px;
    border-radius: var(--radius);
    background: var(--raised);
  }
  .lane.active .track {
    outline: 1px solid var(--accent);
  }
  .tick {
    position: absolute;
    top: 5px;
    width: 8px;
    height: 16px;
    margin-left: -4px;
    border-radius: 2px;
    background: var(--muted);
  }
  .tick.flagged {
    background: var(--warning);
  }
  .tick.current {
    top: 2px;
    height: 22px;
    background: var(--accent);
    box-shadow: 0 0 0 2px var(--surface);
  }
  .tick:hover {
    transform: scaleY(1.2);
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
    margin: 4px 0 0;
    font-size: 11px;
    color: var(--muted);
  }
  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .tick-key {
    display: inline-block;
    width: 6px;
    height: 12px;
    border-radius: 2px;
    background: var(--muted);
  }
  .tick-key.flagged {
    background: var(--warning);
  }
  @media (max-width: 560px) {
    .axis {
      margin-left: 0;
    }
    .lane {
      grid-template-columns: 1fr;
      gap: 2px;
    }
  }
</style>
