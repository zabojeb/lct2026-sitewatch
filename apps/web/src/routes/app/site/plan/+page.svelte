<script lang="ts">
  import DotsSixVerticalIcon from 'phosphor-svelte/lib/DotsSixVerticalIcon';
  import ArrowUpIcon from 'phosphor-svelte/lib/ArrowUpIcon';
  import ArrowDownIcon from 'phosphor-svelte/lib/ArrowDownIcon';
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import PlusIcon from 'phosphor-svelte/lib/PlusIcon';
  import PlanGantt from '$lib/components/site/PlanGantt.svelte';
  import ScheduleEvidence from '$lib/components/site/ScheduleEvidence.svelte';
  import { isControllable } from '$lib/site/analysis';
  import { EQUIPMENT, equipmentName } from '$lib/site/catalog';
  import { equipmentIcon } from '$lib/site/icons';
  import { days, numericDate, plural } from '$lib/site/format';
  import { useSite } from '$lib/site/store.svelte';
  import type { PlanStage, StageProfile } from '$lib/site/types';

  const site = useSite();

  /* ---------- plan editing ---------- */
  let dragging = $state<string | null>(null);
  let flashId = $state<string | null>(null);
  function pick(id: string) {
    document.getElementById(`stage-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    flashId = id;
    setTimeout(() => flashId === id && (flashId = null), 1400);
  }
  let query = $state('');
  const matches = $derived(
    query.trim().length < 2
      ? []
      : (site.methodology?.stages ?? [])
          .filter((row) => row.name.toLowerCase().includes(query.trim().toLowerCase()))
          .slice(0, 8),
  );
  const profileName = (id: string) => site.profile(id)?.name ?? id;

  function move(from: number, to: number) {
    if (to < 0 || to >= site.plan.stages.length || from === to) return;
    const stages = [...site.plan.stages];
    const [item] = stages.splice(from, 1);
    stages.splice(to, 0, item);
    site.plan.stages = stages;
  }
  function addStage(stage: Omit<PlanStage, 'id'>) {
    site.plan.stages = [...site.plan.stages, { ...stage, id: `stage-${Date.now()}` }];
    query = '';
  }
  function removeStage(id: string) {
    if (site.plan.stages.length > 1) site.plan.stages = site.plan.stages.filter((s) => s.id !== id);
  }

  /* ---------- requirements of a profile ---------- */
  let focusId = $state('');
  const focus = $derived<StageProfile | null>(
    site.profile(focusId) ?? site.acceptedProfile ?? site.plannedProfile ?? null,
  );
  let showAll = $state(false);
  type Role = 'required' | 'any' | 'optional' | 'off';
  const roleOf = (p: StageProfile, slug: string): Role =>
    slug in p.required
      ? 'required'
      : p.anyOf.some((g) => g.includes(slug))
        ? 'any'
        : p.optional.includes(slug)
          ? 'optional'
          : 'off';
  const rows = $derived(
    focus
      ? showAll
        ? [...EQUIPMENT]
        : EQUIPMENT.filter((slug) => roleOf(focus, slug) !== 'off')
      : [],
  );
  const counts = $derived(site.analysis?.snapshot.counts ?? {});
  const edited = $derived(Boolean(focus && site.profileOverrides[focus.id]));

  function setRole(slug: string, role: Role) {
    if (!focus) return;
    const p: StageProfile = JSON.parse(JSON.stringify(focus));
    delete p.required[slug];
    p.anyOf = p.anyOf.map((g) => g.filter((s) => s !== slug)).filter((g) => g.length);
    p.optional = p.optional.filter((s) => s !== slug);
    if (role === 'required') p.required[slug] = 1;
    if (role === 'any')
      p.anyOf = p.anyOf.length ? [[...p.anyOf[0], slug], ...p.anyOf.slice(1)] : [[slug]];
    if (role === 'optional') p.optional.push(slug);
    site.profileOverrides = { ...site.profileOverrides, [p.id]: p };
  }
  function setMinimum(slug: string, value: number) {
    if (!focus || !(slug in focus.required)) return;
    const p: StageProfile = JSON.parse(JSON.stringify(focus));
    p.required[slug] = Math.max(1, Math.round(value) || 1);
    site.profileOverrides = { ...site.profileOverrides, [p.id]: p };
  }
  function resetProfile() {
    if (!focus) return;
    const { [focus.id]: _, ...rest } = site.profileOverrides;
    site.profileOverrides = rest;
  }
</script>

<div class="page-heading">
  <div>
    <h1>План работ</h1>
    <p>Плановые этапы и требования к технике. Фактический этап работ требует отдельной визуальной проверки.</p>
  </div>
  <div class="heading-actions">
    <span class="hint">Изменения сохраняются в этом браузере автоматически</span>
    <button
      class="button quiet"
      onclick={() =>
        confirm('Вернуть план, профили и зоны проекта к исходным?') && site.resetProject()}
    >
      Сбросить проект
    </button>
  </div>
</div>

<section class="status-strip" aria-label="План и наблюдения">
  <div>
    <span class="eyebrow">По графику на {site.frame ? numericDate(site.frame.timestamp) : '—'}</span>
    <b class="clamp" title={site.plannedWindow?.name}>{site.plannedWindow?.name ?? 'Вне графика'}</b>
    <small>{site.plannedWindow
      ? `${numericDate(site.plannedWindow.start)} — ${numericDate(site.plannedWindow.end)}`
      : 'На эту дату этап не запланирован'}</small>
  </div>
  <div>
    <span class="eyebrow">Техника на доступных кадрах</span>
    <b>{Object.values(counts).reduce((sum, count) => sum + count, 0)} объектов</b>
    <small>Состав техники не устанавливает фактический этап</small>
  </div>
  <div>
    <span class="eyebrow">Профиль для сравнения</span>
    <select bind:value={site.acceptedProfileId} aria-label="Профиль для сравнения">
      <option value="">По плану · {site.plannedProfile?.name ?? 'не задан'}</option>
      {#each site.profiles.filter(isControllable) as profile (profile.id)}
        <option value={profile.id}>{profile.name}</option>
      {/each}
    </select>
    <small>Ручной выбор меняет правило сравнения, не подтверждает этап</small>
  </div>
  <div>
    <span class="eyebrow">Факт выполнения</span>
    <b>{site.planComparison ? 'Дата факта задана' : 'Не установлена'}</b>
    <small>{site.planComparison ? 'Задана сценарием, не моделью' : 'Для вывода нужны видимые признаки работ и источник факта'}</small>
  </div>
</section>

{#if site.planComparison}<ScheduleEvidence />{/if}

<div class="section">
  <div class="section-head">
    <div>
      <h2>Календарный план</h2>
      <p>
        {site.plan.stages.length} {plural(site.plan.stages.length, ['этап', 'этапа', 'этапов'])} · {days(
          site.plan.stages.reduce((sum, s) => sum + s.days, 0),
        )} · порядок меняйте за ручку строки, длительность — за край полосы
      </p>
    </div>
    <label class="start">
      <span class="eyebrow">Начало</span>
      <input type="date" bind:value={site.plan.start} />
    </label>
  </div>
  <PlanGantt onpick={pick} />
  <ol class="plan-list">
    {#each site.plan.stages as stage, index (stage.id)}
      {@const w = site.windows[index]}
      <li
        id="stage-{stage.id}"
        class="plan-item"
        class:dragging={dragging === stage.id}
        class:flash={flashId === stage.id}
        class:current={site.plannedWindow?.id === stage.id}
        draggable="true"
        ondragstart={(e) => {
          dragging = stage.id;
          e.dataTransfer?.setData('text/plain', stage.id);
        }}
        ondragend={() => (dragging = null)}
        ondragover={(e) => e.preventDefault()}
        ondrop={(e) => {
          e.preventDefault();
          const from = site.plan.stages.findIndex(
            (s) => s.id === e.dataTransfer?.getData('text/plain'),
          );
          move(from, index);
        }}
      >
        <span class="handle" aria-hidden="true"><DotsSixVerticalIcon size={18} /></span>
        <b class="num">{index + 1}</b>
        <span class="name">
          <b title={stage.name}>{stage.name}</b>
          <small>{stage.row ? `строка ${stage.row} перечня` : 'свой этап'}</small>
        </span>
        <label>
          <span class="eyebrow">Профиль техники</span>
          <select bind:value={stage.profileId}>
            {#each site.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
          </select>
        </label>
        <label class="duration">
          <span class="eyebrow">Дней</span>
          <input
            type="number"
            min="1"
            bind:value={stage.days}
            onchange={() => (stage.days = Math.max(1, Math.round(stage.days) || 1))}
          />
        </label>
        <span class="dates">{numericDate(w.start)} — {numericDate(w.end)}</span>
        <span class="actions">
          <button
            class="icon-button"
            onclick={() => move(index, index - 1)}
            disabled={index === 0}
            aria-label="Поднять этап"><ArrowUpIcon size={16} /></button
          >
          <button
            class="icon-button"
            onclick={() => move(index, index + 1)}
            disabled={index === site.plan.stages.length - 1}
            aria-label="Опустить этап"><ArrowDownIcon size={16} /></button
          >
          <button
            class="icon-button"
            onclick={() => removeStage(stage.id)}
            disabled={site.plan.stages.length === 1}
            aria-label="Удалить этап"><XIcon size={16} /></button
          >
        </span>
      </li>
    {/each}
  </ol>
  <div class="add">
    <label>
      <span class="eyebrow">Добавить этап из перечня работ (377 строк)</span>
      <input type="search" bind:value={query} placeholder="Например: котлован, сваи, асфальт…" />
    </label>
    {#if matches.length}
      <ul class="matches">
        {#each matches as row (row.row)}
          <li>
            <button
              onclick={() =>
                addStage({ name: row.name, profileId: row.profileId, row: row.row, days: 14 })}
            >
              <PlusIcon size={14} />
              <span
                ><b>{row.name}</b><small
                  >строка {row.row}{row.code ? ` · ${row.code}` : ''} · {row.l2 || row.l1} · {profileName(
                    row.profileId,
                  )}</small
                ></span
              >
            </button>
          </li>
        {/each}
      </ul>
    {:else if query.trim().length >= 2}
      <p class="hint">В перечне нет такой строки — можно добавить свой этап.</p>
    {/if}
    <button
      class="button secondary"
      onclick={() =>
        addStage({ name: query.trim() || 'Новый этап', profileId: 'needs_review', days: 14 })}
    >
      <PlusIcon size={16} /> Свой этап
    </button>
  </div>
</div>

<div class="section">
  <div class="section-head">
    <div>
      <h2>Требования к технике</h2>
      <p>
        Роль каждого класса в профиле этапа. «Обязательная» — нужна с минимумом, «Одна из группы» —
        достаточно любой из группы, «Допустимая» — не вызывает предупреждений.
      </p>
    </div>
    <div class="heading-actions">
      <label>
        Профиль
        <select value={focus?.id ?? ''} onchange={(e) => (focusId = e.currentTarget.value)}>
          {#each site.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
        </select>
      </label>
      <button class="button quiet" onclick={() => (showAll = !showAll)}
        >{showAll ? 'Только используемые' : `Все ${EQUIPMENT.length} классов`}</button
      >
      {#if edited}<button class="button quiet" onclick={resetProfile}
          >Вернуть исходный профиль</button
        >{/if}
    </div>
  </div>
  {#if focus}
    <div class="requirements panel">
      <div class="table req">
        <div class="row head">
          <span>Техника</span><span>Роль</span><span>Минимум</span><span>В срезе камер</span>
        </div>
        {#each rows as slug (slug)}
          {@const Icon = equipmentIcon(slug)}
          {@const role = roleOf(focus, slug)}
          <div class="row">
            <span class="machine"><Icon size={18} /><b>{equipmentName(slug)}</b></span>
            <select
              value={role}
              onchange={(e) => setRole(slug, e.currentTarget.value as Role)}
              aria-label="Роль: {equipmentName(slug)}"
            >
              <option value="required">Обязательная</option>
              <option value="any">Одна из группы</option>
              <option value="optional">Допустимая</option>
              <option value="off">Не используется</option>
            </select>
            <input
              type="number"
              min="1"
              value={focus.required[slug] ?? 1}
              disabled={role !== 'required'}
              onchange={(e) => setMinimum(slug, Number(e.currentTarget.value))}
              aria-label="Минимум: {equipmentName(slug)}"
            />
            <b>{counts[slug] ?? 0}</b>
          </div>
        {/each}
        <p class="hint">Ноль в доступных кадрах не доказывает, что техники нет в зоне.</p>
      </div>
      <aside class="basis">
        <span class="eyebrow">Основание профиля</span>
        <b>{focus.name}</b>
        {#if focus.note}<p>{focus.note}</p>{/if}
        {#if focus.gesn.length}<p><small>Нормы:</small> {focus.gesn.join('; ')}</p>{/if}
        {#each focus.sourceRefs as ref (ref)}
          {@const source = site.methodology?.sources[ref]}
          {#if source}<a href={source.url} target="_blank" rel="noreferrer"
              >{source.authority}: {source.title} ↗</a
            >{/if}
        {/each}
        <p class="hint">
          Окно наблюдения {focus.windowMinutes} мин: требование не означает, что машина видна на каждом
          кадре. {edited ? 'Профиль изменён для этого проекта.' : ''}
        </p>
      </aside>
    </div>
  {/if}
</div>

<style>
  .start {
    display: grid;
    gap: 4px;
  }
  .plan-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 6px;
  }
  .plan-item {
    display: grid;
    grid-template-columns: 22px 28px minmax(0, 1.6fr) minmax(160px, 1fr) 88px 190px auto;
    gap: 12px;
    align-items: center;
    padding: 10px 12px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--surface);
  }
  .plan-item.current {
    border-color: var(--accent);
  }
  .plan-item.dragging {
    opacity: 0.5;
  }
  .plan-item.flash {
    animation: flash 1.4s ease-out;
  }
  @keyframes flash {
    0%,
    35% {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 35%, transparent);
    }
  }
  .handle {
    color: var(--muted);
    cursor: grab;
  }
  .num {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: var(--raised);
    font-size: 12px;
  }
  .name {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  .name b {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-size: 13px;
  }
  .name small {
    font-size: 11px;
    color: var(--muted);
  }
  .plan-item label {
    display: grid;
    gap: 4px;
    min-width: 0;
  }
  .plan-item select,
  .status-strip select,
  .req select {
    width: 100%;
    min-width: 0;
  }
  .duration input {
    width: 100%;
  }
  .dates {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }
  .actions {
    display: flex;
    gap: 2px;
  }
  .actions .icon-button {
    width: 32px;
    height: 32px;
  }
  .actions .icon-button:disabled {
    opacity: 0.3;
    cursor: default;
  }
  @media (max-width: 1100px) {
    .plan-item {
      grid-template-columns: 22px 28px minmax(0, 1fr) auto;
    }
    .plan-item label,
    .dates {
      grid-column: 3 / -1;
    }
    .actions {
      grid-column: 4;
      grid-row: 1;
    }
  }
  .add {
    display: grid;
    gap: 8px;
    margin-top: 12px;
    max-width: 760px;
  }
  .add label {
    display: grid;
    gap: 4px;
  }
  .add .button {
    width: fit-content;
    min-height: 38px;
    padding: 8px 14px;
    gap: 8px;
  }
  .matches {
    list-style: none;
    margin: 0;
    padding: 0;
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  .matches button {
    display: flex;
    gap: 10px;
    width: 100%;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
  }
  .matches button:hover {
    background: var(--raised);
  }
  .matches span {
    display: grid;
    gap: 2px;
  }
  .matches small {
    color: var(--muted);
    font-size: 11px;
  }
  .requirements {
    display: grid;
    grid-template-columns: minmax(0, 1.7fr) minmax(240px, 1fr);
    gap: 20px;
    padding: 14px 16px;
  }
  @media (max-width: 900px) {
    .requirements {
      grid-template-columns: 1fr;
    }
  }
  .req .row {
    grid-template-columns: minmax(0, 1fr) 160px 80px 120px;
  }
  .req .row input {
    width: 100%;
  }
  .req .row input:disabled {
    opacity: 0.35;
  }
  .req .row > b {
    text-align: center;
  }
  @media (max-width: 640px) {
    .req .row {
      grid-template-columns: 1fr 1fr;
    }
    .req .row.head {
      display: none;
    }
  }
  .basis {
    display: grid;
    align-content: start;
    gap: 8px;
    font-size: 13px;
  }
  .basis p {
    margin: 0;
    line-height: 1.55;
  }
  .basis small {
    color: var(--muted);
  }
  .basis a {
    font-size: 12px;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
</style>
