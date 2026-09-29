<script lang="ts">
  import FrameView from '$lib/components/site/FrameView.svelte';
  import ScheduleEvidence from '$lib/components/site/ScheduleEvidence.svelte';
  import ModelRunArchive from '$lib/components/site/ModelRunArchive.svelte';
  import { classCounts, cameraFrames } from '$lib/site/analysis';
  import { isMachine } from '$lib/site/catalog';
  import { cameras, clock, frames as framesWord, numericDate, time } from '$lib/site/format';
  import { windowAt } from '$lib/site/plan';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();
  const project = $derived(site.project!);
  const frame = $derived(site.frame);
  const all = $derived([...project.frames].sort((a, b) => time(a.timestamp) - time(b.timestamp)));
  const index = $derived(frame ? all.indexOf(frame) : -1);
  const cameraName = (id: string) => project.cameras.find((c) => c.id === id)?.name ?? id;
  const machines = (f: (typeof all)[number]) =>
    Object.values(classCounts(f.boxes)).reduce((a, b) => a + b, 0);
  const people = (f: (typeof all)[number]) => f.boxes.filter((b) => !isMachine(b.slug)).length;

  const days = $derived.by(() => {
    const byDay = new Map<string, typeof all>();
    for (const f of all) {
      const day = f.timestamp.slice(0, 10);
      if (!byDay.has(day)) byDay.set(day, []);
      byDay.get(day)!.push(f);
    }
    return [...byDay.values()].map((items) => ({
      date: items[0].timestamp,
      items,
      cameras: new Set(items.map((f) => f.cameraId)).size,
      machines: Math.max(...items.map(machines)),
      people: Math.max(...items.map(people)),
      stage: windowAt(site.windows, time(items[0].timestamp))?.name ?? 'Вне графика',
    }));
  });
</script>

<ModelRunArchive />

{#if frame && site.analysis}
  {@const planned = windowAt(site.windows, time(frame.timestamp))}
  <div class="page-heading">
    <div>
      <h1>Демонстрационные кадры</h1>
      <p>
        {numericDate(all[0].timestamp)} — {numericDate(all.at(-1)!.timestamp)} · {framesWord(
          all.length,
        )} ·
        {project.cameras.length === 1 ? 'один ракурс' : cameras(project.cameras.length)}
      </p>
    </div>
  </div>

  {#if site.planComparison}<ScheduleEvidence />{/if}

  <div class="history-layout">
    <section class="panel" aria-label="Кадр">
      <div class="panel-head">
        <div>
          <span class="eyebrow"
            >{cameraName(frame.cameraId)} · кадр {index + 1} из {all.length}</span
          >
          <h2>{numericDate(frame.timestamp)} · {clock(frame.timestamp)}</h2>
        </div>
      </div>
      <div class="panel-body">
        <FrameView
          {frame}
          tones={frame.boxes.map(() => ({ tone: 'neutral' as const, messages: [] }))}
          alt="Ход строительства, {numericDate(frame.timestamp)}"
        />
      </div>
    </section>

    <aside class="panel facts" aria-label="Состояние на дату">
      <div class="panel-head">
        <div>
          <span class="eyebrow">Состояние на дату</span>
          <h2>{numericDate(frame.timestamp)}</h2>
        </div>
      </div>
      <div class="panel-body">
        <dl>
          <div>
            <dt>Фактический этап</dt>
            <dd>{site.planComparison?.observation.frameId === frame.id ? 'Дата факта задана вручную' : 'Не установлена'}</dd>
          </div>
          <div>
            <dt>По графику</dt>
            <dd title={planned?.name}>{planned?.name ?? 'вне графика'}</dd>
          </div>
          <div>
            <dt>Техника на кадре</dt>
            <dd>{machines(frame)}</dd>
          </div>
          <div>
            <dt>Люди на кадре</dt>
            <dd>{people(frame)}</dd>
          </div>
          <div>
            <dt>Проверка по плану</dt>
            <dd>{site.planComparison?.observation.frameId === frame.id ? 'См. сравнение выше' : 'Нет данных о факте'}</dd>
          </div>
        </dl>
        <button class="design-reference" onclick={() => (site.designDialog = true)}>
          <span class="eyebrow">Проектный вид</span>
          <b>{site.designView ? 'Открыть' : 'Загрузить'}</b>
          <small>Визуальное сопоставление без автоматической оценки готовности</small>
        </button>
        <p class="hint">
          Состав техники не доказывает этап. Сравнивать динамику стоит только по кадрам одного ракурса: {cameraFrames(
            project,
            frame.cameraId,
          ).length} кадров у «{cameraName(frame.cameraId)}».
        </p>
      </div>
    </aside>
  </div>

  <ul class="thumbs" aria-label="Все кадры по времени">
    {#each all as item (item.id)}
      <li>
        <button
          class="thumb"
          class:active={item.id === frame.id}
          onclick={() => site.selectFrame(item.id)}
          aria-label="{cameraName(item.cameraId)}, {numericDate(item.timestamp)} {clock(
            item.timestamp,
          )}"
        >
          <img src={item.preview ?? item.image} alt="" loading="lazy" />
          <span
            ><b>{numericDate(item.timestamp)}</b><small
              >{clock(item.timestamp)} · {cameraName(item.cameraId)}</small
            ></span
          >
        </button>
      </li>
    {/each}
  </ul>

  <div class="section">
    <div class="section-head">
      <div>
        <h2>Контрольные даты</h2>
        <p>Сводка снимков и плановых этапов; фактическое выполнение по технике не определяется</p>
      </div>
    </div>
    <div class="panel">
      <div class="table dates">
        <div class="row head">
          <span>Дата</span><span>Кадров</span><span>Камер</span><span>Техники</span><span
          >Людей</span
          ><span>По графику</span>
        </div>
        {#each days as day (day.date)}
          <button class="row" onclick={() => site.selectFrame(day.items.at(-1)!.id)}>
            <b>{numericDate(day.date)}</b>
            <span>{day.items.length}</span>
            <span>{day.cameras}</span>
            <span>{day.machines}</span>
            <span>{day.people}</span>
            <span class="stage">{day.stage}</span>
          </button>
        {/each}
      </div>
    </div>
  </div>
{/if}

<style>
  .history-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr);
    gap: 16px;
    align-items: start;
  }
  @media (max-width: 1000px) {
    .history-layout {
      grid-template-columns: 1fr;
    }
  }
  dl {
    margin: 0;
    display: grid;
    gap: 0;
  }
  dl div {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 12px;
    padding: 9px 0;
    border-bottom: 1px solid var(--line);
    font-size: 13px;
  }
  dt {
    color: var(--muted);
  }
  dd {
    margin: 0;
    max-width: 220px;
    text-align: right;
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .design-reference {
    display: grid;
    gap: 4px;
    padding: 12px;
    border: 1px dashed var(--line);
    border-radius: var(--radius);
    text-align: left;
  }
  .design-reference:hover {
    background: var(--raised);
  }
  .design-reference small {
    color: var(--muted);
    font-size: 11px;
  }
  .thumbs {
    list-style: none;
    margin: 16px 0 0;
    padding: 0 0 6px;
    display: flex;
    gap: 10px;
    overflow-x: auto;
  }
  .thumbs li {
    flex: 0 0 150px;
  }
  .thumb {
    width: 100%;
    display: grid;
    gap: 6px;
    padding: 6px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    text-align: left;
    background: var(--surface);
  }
  .thumb.active {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .thumb img {
    width: 100%;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    border-radius: 2px;
    background: var(--raised);
  }
  .thumb span {
    display: grid;
    gap: 2px;
    font-size: 12px;
  }
  .thumb small {
    color: var(--muted);
    font-size: 11px;
  }
  .dates {
    padding: 12px 16px;
  }
  .dates .row {
    grid-template-columns: 110px 70px 60px 70px 60px minmax(0, 1fr);
    width: 100%;
    text-align: left;
  }
  .dates button.row:hover {
    background: var(--raised);
  }
  .stage {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  @media (max-width: 760px) {
    .dates .row {
      grid-template-columns: 1fr 1fr 1fr;
    }
    .dates .row.head {
      display: none;
    }
  }
</style>
