<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import ArrowLeftIcon from 'phosphor-svelte/lib/ArrowLeftIcon';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import PolygonIcon from 'phosphor-svelte/lib/PolygonIcon';
  import FrameView from '$lib/components/site/FrameView.svelte';
  import ZoneCanvas from '$lib/components/site/ZoneCanvas.svelte';
  import { EQUIPMENT, equipmentName } from '$lib/site/catalog';
  import { equipmentIcon } from '$lib/site/icons';
  import { clock, numericDate, objects, plural } from '$lib/site/format';
  import { zoneFor, zoneVisibility } from '$lib/site/zones';
  import { useSite } from '$lib/site/store.svelte';
  import type { Point, Zone } from '$lib/site/types';

  const site = useSite();
  const frame = $derived(site.frame);
  const zones = $derived(site.zones[site.cameraId] ?? []);

  let editing = $state(false);
  let drawing = $state(false);
  let draft = $state<Point[]>([]);
  let wizard = $state(false);
  let draftName = $state('Запретная зона');
  let draftClasses = $state<string[]>(['excavator']);

  onMount(() => {
    if (page.url.searchParams.has('new')) openWizard();
  });

  const setZones = (next: Zone[]) => (site.zones = { ...site.zones, [site.cameraId]: next });
  const updateZone = (id: string, patch: Partial<Zone>) =>
    setZones(zones.map((z) => (z.id === id ? { ...z, ...patch } : z)));

  function openWizard() {
    draftName = 'Запретная зона';
    draftClasses = ['excavator'];
    wizard = true;
  }
  function startDrawing() {
    wizard = false;
    editing = true;
    drawing = true;
    draft = [];
  }
  function finishDrawing() {
    if (draft.length >= 3)
      setZones([
        ...zones,
        {
          id: `zone-${Date.now()}`,
          name: draftName.trim() || 'Запретная зона',
          equipment: [...draftClasses],
          points: draft,
        },
      ]);
    draft = [];
    drawing = false;
  }
  function toggleClass(zone: Zone, slug: string, on: boolean) {
    const next = on
      ? [...new Set([...zone.equipment, slug])]
      : zone.equipment.filter((s) => s !== slug);
    if (next.length) updateZone(zone.id, { equipment: next });
  }

  // Readable share of each polygon on the frame on screen, cached by frame and geometry.
  // Waits for the geometry to settle so a drag does not trigger a computation per move.
  const visKey = (zone: Zone) => `${frame?.id}|${zone.id}|${zone.points.flat().join(',')}`;
  $effect(() => {
    const current = frame;
    if (!current) return;
    const pending = zones.filter((zone) => !(visKey(zone) in site.visibility));
    if (!pending.length) return;
    const timer = setTimeout(() => {
      for (const zone of pending) {
        const key = visKey(zone);
        site.visibility[key] = -1;
        zoneVisibility(current.image, zone)
          .then((value) => (site.visibility[key] = value))
          .catch(() => delete site.visibility[key]);
      }
    }, 250);
    return () => clearTimeout(timer);
  });

  const violations = (zone: Zone) =>
    frame ? frame.boxes.filter((box) => zoneFor(box, [zone])).length : 0;
  const geometry = $derived(site.project?.geometry ?? null);
  const cameraName = (id?: string) =>
    site.project?.cameras.find((c) => c.id === id)?.name ?? id ?? '';
</script>

{#if frame}
  <div class="page-heading">
    <div>
      <h1>Запретные зоны</h1>
      <p>{site.camera?.name} · {numericDate(frame.timestamp)} · {clock(frame.timestamp)}</p>
    </div>
    <div class="heading-actions">
      <label>
        Камера
        <select
          aria-label="Камера"
          value={site.cameraId}
          onchange={(e) => {
            site.selectCamera(e.currentTarget.value);
            drawing = false;
            draft = [];
          }}
        >
          {#each site.project?.cameras ?? [] as camera (camera.id)}<option value={camera.id}
              >{camera.name}</option
            >{/each}
        </select>
      </label>
      {#if zones.length}
        <button
          class="button {editing ? 'primary' : 'secondary'}"
          onclick={() => ((editing = !editing), (drawing = false), (draft = []))}
        >
          {editing ? 'Готово' : 'Редактировать'}
        </button>
      {/if}
    </div>
  </div>

  {#if editing}
    <div class="toolbar" role="status">
      <span>
        {drawing
          ? `Ставьте точки по границе области: ${draft.length} ${plural(draft.length, ['точка', 'точки', 'точек'])}`
          : 'Тяните вершину или весь многоугольник; «+» на ребре добавляет вершину'}
      </span>
      {#if drawing}
        <button class="button primary" onclick={finishDrawing} disabled={draft.length < 3}
          >Завершить зону</button
        >
        <button class="button quiet" onclick={() => ((drawing = false), (draft = []))}
          >Отмена</button
        >
      {:else}
        <button class="button secondary" onclick={openWizard}>+ Запретная зона</button>
      {/if}
    </div>
  {/if}

  <div class="zones-layout">
    <section class="panel" aria-label="Кадр камеры с зонами">
      <div class="panel-body">
        <FrameView
          {frame}
          tones={site.analysis?.boxTones}
          alt="Запретные зоны, {site.camera?.name}"
        >
          {#snippet overlay()}
            <ZoneCanvas {zones} {editing} {drawing} bind:draft onchange={setZones} />
          {/snippet}
        </FrameView>
        <div class="frame-nav">
          <div class="stamp">
            <b>{clock(frame.timestamp)}</b><span>{numericDate(frame.timestamp)}</span>
          </div>
          <div class="arrows">
            <button
              onclick={() => site.step(-1)}
              disabled={site.frameIndex <= 0}
              aria-label="Предыдущий кадр"><ArrowLeftIcon size={18} /></button
            >
            <span>{site.frameIndex + 1} / {site.frames.length}</span>
            <button
              onclick={() => site.step(1)}
              disabled={site.frameIndex >= site.frames.length - 1}
              aria-label="Следующий кадр"><ArrowRightIcon size={18} /></button
            >
          </div>
          <div class="position">
            <b>{site.camera?.name}</b><span>кадр {site.frameIndex + 1} из {site.frames.length}</span
            >
          </div>
        </div>
      </div>
    </section>

    <aside class="panel" aria-label="Зоны камеры">
      <div class="panel-head">
        <div>
          <span class="eyebrow">Запретные зоны камеры</span>
          <h2>
            {zones.length
              ? `${zones.length} ${plural(zones.length, ['зона', 'зоны', 'зон'])}`
              : 'Зон пока нет'}
          </h2>
        </div>
      </div>
      <div class="panel-body">
        {#each zones as zone (zone.id)}
          {@const hits = violations(zone)}
          {@const vis = site.visibility[visKey(zone)]}
          <div class="zone-row" class:issue={hits > 0}>
            <div class="zone-main">
              {#if editing}
                <input
                  type="text"
                  value={zone.name}
                  oninput={(e) => updateZone(zone.id, { name: e.currentTarget.value })}
                  aria-label="Название зоны"
                />
              {:else}
                <b>{zone.name}{zone.example ? ' · пример правила' : ''}</b>
              {/if}
              <span class="metrics">
                <span>Видимость {vis === undefined || vis < 0 ? 'считается…' : `${vis}%`}</span>
                <span class="tone {hits ? 'yellow' : 'green'}"
                  >{hits ? `${objects(hits)} в зоне` : 'объекты в зоне не найдены'}</span
                >
              </span>
              {#if editing}
                <fieldset>
                  <legend>Запрещена техника</legend>
                  {#each EQUIPMENT as slug (slug)}
                    {@const Icon = equipmentIcon(slug)}
                    <label class="chip">
                      <input
                        type="checkbox"
                        checked={zone.equipment.includes(slug)}
                        onchange={(e) => toggleClass(zone, slug, e.currentTarget.checked)}
                      />
                      <Icon size={14} />{equipmentName(slug)}
                    </label>
                  {/each}
                </fieldset>
              {:else}
                <small>Въезд запрещён: {zone.equipment.map(equipmentName).join(', ')}</small>
              {/if}
            </div>
            {#if editing}
              <button
                class="icon-button"
                onclick={() => setZones(zones.filter((z) => z.id !== zone.id))}
                aria-label="Удалить зону «{zone.name}»"><XIcon size={16} /></button
              >
            {/if}
          </div>
        {:else}
          <div class="onboarding">
            <PolygonIcon size={28} />
            <b>Разметьте запретные зоны</b>
            <span
              >Выберите один или несколько типов техники и обведите область, куда им нельзя
              заезжать.</span
            >
            <button class="button primary" onclick={openWizard}>Начать разметку</button>
          </div>
        {/each}
        {#if zones.length && !editing}
          <button class="button quiet" onclick={() => ((editing = true), openWizard())}
            >+ Добавить запретную зону</button
          >
        {/if}
        <p class="hint">
          Техника считается в зоне, если середина нижнего края рамки (точка касания с землёй)
          внутри контура. Видимость — доля зоны без пересвета и провалов в чёрное; для метров и
          генплана камеры нужно привязать к опорным точкам.
        </p>
      </div>
    </aside>
  </div>

  {#if geometry}
    <div class="section">
      <div class="section-head">
        <div>
          <h2>Геометрия камер</h2>
          <p>
            {geometry.note} По гомографии общей плоскости рамки двух камер можно свести в одни координаты,
            чтобы не считать одну машину дважды.
          </p>
        </div>
      </div>
      <div class="geometry">
        {#each geometry.cameras as g (g.cameraId)}
          <article class="panel">
            <span class="eyebrow">{cameraName(g.cameraId)} · стабильность ракурса</span>
            <b>{g.inliers} из {g.matches} совпадений · {Math.round(g.inlierRatio * 100)}%</b>
            <small
              >RMSE {g.rmse ?? '—'} px · серия {g.spanSec} с · ключевых точек {g.keypoints.join(
                ' / ',
              )}</small
            >
          </article>
        {/each}
        {#each geometry.pairs as g (g.kind)}
          <article class="panel">
            <span class="eyebrow"
              >{cameraName(g.from)} ↔ {cameraName(g.to)} · {g.kind === 'homography'
                ? 'гомография плоскости'
                : 'эпиполярная геометрия'}</span
            >
            <b>{g.inliers} из {g.matches} совпадений · {Math.round(g.inlierRatio * 100)}%</b>
            <small
              >{g.rmse !== null ? `RMSE ${g.rmse} px` : 'RMSE не применим'} · SIFT + RANSAC</small
            >
          </article>
        {/each}
      </div>
    </div>
  {/if}

  {#if wizard}
    <div
      class="backdrop"
      role="presentation"
      onclick={(e) => e.target === e.currentTarget && (wizard = false)}
    >
      <div class="dialog narrow" role="dialog" aria-modal="true" aria-label="Новая запретная зона">
        <header>
          <div>
            <span class="eyebrow">Новая запретная зона</span>
            <h2>{site.camera?.name}</h2>
          </div>
          <button class="icon-button" onclick={() => (wizard = false)} aria-label="Закрыть"
            ><XIcon size={20} /></button
          >
        </header>
        <div class="dialog-body">
          <label class="field">
            <span class="eyebrow">Название зоны</span>
            <input type="text" bind:value={draftName} placeholder="Например: склад материалов" />
          </label>
          <fieldset>
            <legend>Какой технике въезд запрещён</legend>
            {#each EQUIPMENT as slug (slug)}
              {@const Icon = equipmentIcon(slug)}
              <label class="chip">
                <input
                  type="checkbox"
                  checked={draftClasses.includes(slug)}
                  onchange={(e) =>
                    (draftClasses = e.currentTarget.checked
                      ? [...draftClasses, slug]
                      : draftClasses.filter((s) => s !== slug))}
                />
                <Icon size={14} />{equipmentName(slug)}
              </label>
            {/each}
          </fieldset>
          <p class="hint">
            Можно выбрать несколько типов. Затем поставьте точки по границе области на кадре и
            нажмите «Завершить зону».
          </p>
          <button class="button primary" onclick={startDrawing} disabled={!draftClasses.length}
            >Перейти к обводу</button
          >
        </div>
      </div>
    </div>
  {/if}
{/if}

<style>
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    padding: 10px 14px;
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    background: var(--accent-soft);
    font-size: 13px;
  }
  .toolbar span {
    margin-right: auto;
  }
  .toolbar .button,
  .heading-actions .button {
    min-height: 36px;
    padding: 6px 14px;
  }
  .zones-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.55fr) minmax(300px, 1fr);
    gap: 16px;
    align-items: start;
  }
  @media (max-width: 1100px) {
    .zones-layout {
      grid-template-columns: 1fr;
    }
  }
  .zone-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
    padding: 12px;
    border: 1px solid var(--line);
    border-left: 3px solid var(--danger);
    border-radius: var(--radius);
  }
  .zone-row.issue {
    background: var(--warning-soft);
  }
  .zone-main {
    display: grid;
    gap: 6px;
    min-width: 0;
  }
  .zone-main small {
    color: var(--muted);
    font-size: 12px;
  }
  .metrics {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    font-size: 12px;
  }
  fieldset {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 0;
    padding: 0;
    border: 0;
  }
  legend {
    margin-bottom: 6px;
    font-size: 12px;
    color: var(--muted);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 8px;
    border: 1px solid var(--line);
    border-radius: 999px;
    font-size: 11px;
    cursor: pointer;
  }
  .chip:has(input:checked) {
    border-color: var(--danger);
    color: var(--text);
  }
  .chip input {
    margin: 0;
  }
  .onboarding {
    display: grid;
    justify-items: start;
    gap: 8px;
    padding: 14px;
    border: 1px dashed var(--line);
    border-radius: var(--radius);
    font-size: 13px;
  }
  .onboarding span {
    color: var(--muted);
  }
  .field {
    display: grid;
    gap: 4px;
  }
  .geometry {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 10px;
  }
  .geometry article {
    display: grid;
    gap: 6px;
    padding: 14px 16px;
  }
  .geometry b {
    font-size: 15px;
  }
  .geometry small {
    color: var(--muted);
    font-size: 12px;
  }
</style>
