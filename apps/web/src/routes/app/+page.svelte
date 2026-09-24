<script lang="ts">
  import { onMount, tick } from 'svelte';
  import ArrowUpRightIcon from 'phosphor-svelte/lib/ArrowUpRightIcon';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import DownloadSimpleIcon from 'phosphor-svelte/lib/DownloadSimpleIcon';
  import UploadSimpleIcon from 'phosphor-svelte/lib/UploadSimpleIcon';
  import MagnifyingGlassIcon from 'phosphor-svelte/lib/MagnifyingGlassIcon';
  import CameraIcon from 'phosphor-svelte/lib/CameraIcon';
  import WarningCircleIcon from 'phosphor-svelte/lib/WarningCircleIcon';
  import CheckCircleIcon from 'phosphor-svelte/lib/CheckCircleIcon';
  import ClockCounterClockwiseIcon from 'phosphor-svelte/lib/ClockCounterClockwiseIcon';
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import Brand from '$lib/components/Brand.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import EvidenceViewer from '$lib/components/EvidenceViewer.svelte';
  import Schedule from '$lib/components/Schedule.svelte';
  import ReviewDialog from '$lib/components/ReviewDialog.svelte';
  import UploadDialog from '$lib/components/UploadDialog.svelte';
  import PlanEditor from '$lib/components/PlanEditor.svelte';
  import ZoneEditor from '$lib/components/ZoneEditor.svelte';
  import ControlAnalysis from '$lib/components/ControlAnalysis.svelte';
  import ScenarioLab from '$lib/components/ScenarioLab.svelte';
  import '$lib/workspace.css';
  import {
    defaults,
    parseWorkspace,
    workspaceKey,
    projectObservation,
    analyze,
    markedDetections,
    summary,
    type Workspace,
    type Scenario,
  } from '$lib/demo/workspace';
  import {
    observations,
    sites,
    assessmentLabels,
    decisionLabels,
    filterObservations,
    formatTime,
    parseReviews,
    reviewStorageKey,
    type Observation,
    type Review,
  } from '$lib/demo/data';

  type View =
    'overview' | 'observations' | 'schedule' | 'zones' | 'analysis' | 'scenarios' | 'journal';
  const navigation: { id: View; label: string }[] = [
    { id: 'overview', label: 'Обзор' },
    { id: 'observations', label: 'Наблюдения' },
    { id: 'schedule', label: 'План работ' },
    { id: 'zones', label: 'Зоны' },
    { id: 'analysis', label: 'Аналитика' },
    { id: 'scenarios', label: 'Сценарии' },
    { id: 'journal', label: 'Журнал' },
  ];
  let view = $state<View>('overview');
  let siteId = $state('north');
  let query = $state('');
  let filter = $state('all');
  let selectedId = $state('OBS-1042');
  let reviews = $state<Review[]>([]);
  let currentReview = $state<Observation | null>(null);
  let toast = $state('');
  let storageWarning = $state('');
  let ready = $state(false);
  let workspaces = $state<Record<string, Workspace>>({
    north: defaults('north'),
    river: defaults('river'),
  });
  let scenario = $state<Scenario>('original');
  const workspace = $derived(workspaces[siteId]);
  const context = $derived(JSON.stringify(workspace));
  const activeReviews = $derived(
    reviews.filter(
      (r) => r.context === context || (!r.context && context === JSON.stringify(defaults(siteId))),
    ),
  );
  let reviewDialog: ReviewDialog;
  let uploadDialog: UploadDialog;
  let searchInput = $state<HTMLInputElement>();
  let resetDialog: HTMLDialogElement;
  let infoDialog: HTMLDialogElement;
  let toastTimer: ReturnType<typeof setTimeout>;
  const site = $derived(sites.find((s) => s.id === siteId)!);
  const siteObservations = $derived(
    observations.filter((o) => o.siteId === siteId).map((o) => projectObservation(o, workspace)),
  );
  const selected = $derived(
    siteObservations.find((o) => o.id === selectedId) || siteObservations[0],
  );
  const filtered = $derived(filterObservations(siteObservations, query, filter, activeReviews));
  const attention = $derived(
    siteObservations.filter(
      (o) =>
        o.assessment === 'needs_attention' && !activeReviews.some((r) => r.observationId === o.id),
    ),
  );
  const insufficient = $derived(
    siteObservations.filter((o) => o.assessment === 'insufficient_evidence'),
  );
  const journal = $derived(
    reviews
      .filter((r) => siteObservations.some((o) => o.id === r.observationId))
      .toSorted((a, b) => b.createdAt.localeCompare(a.createdAt)),
  );

  function notify(message: string) {
    toast = message;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = ''), 4500);
  }
  function persist(next: Review[]) {
    reviews = next;
    try {
      localStorage.setItem(reviewStorageKey, JSON.stringify(next));
      storageWarning = '';
    } catch {
      storageWarning = 'Браузер запретил сохранение. Решения доступны только до перезагрузки.';
    }
  }
  function saveReview(review: Review) {
    persist([
      { ...review, context },
      ...reviews.filter((r) => r.observationId !== review.observationId),
    ]);
    notify(
      storageWarning ? 'Решение сохранено в памяти страницы' : 'Решение сохранено в этом браузере',
    );
  }
  async function inspect(observation: Observation) {
    currentReview = observation;
    await tick();
    reviewDialog.open();
  }
  async function focusSearch() {
    view = 'observations';
    await tick();
    searchInput?.focus();
  }
  function switchSite() {
    selectedId = observations.find((o) => o.siteId === siteId)!.id;
    query = '';
    filter = 'all';
    scenario = 'original';
  }
  function saveWorkspace(next: Workspace) {
    workspaces = { ...workspaces, [siteId]: next };
    try {
      localStorage.setItem(`${workspaceKey}.${siteId}`, JSON.stringify(next));
      storageWarning = '';
      notify('Настройки площадки сохранены. Наблюдения пересчитаны.');
    } catch {
      storageWarning = 'Настройки применены в памяти, но браузер запретил сохранение.';
    }
  }
  function downloadReport() {
    const report = {
      schema: 'sitewatch.demo.report.v1',
      mode: 'synthetic_demo',
      site,
      exportedAt: new Date().toISOString(),
      note: 'Иллюстрации и разметка синтетические. Не является отчётом о реальной стройке.',
      observations: siteObservations,
      reviews: journal,
      workspace,
      analyses: siteObservations.map((o) => ({ observationId: o.id, ...analyze(o, workspace) })),
      summary: summary(selected, analyze(selected, workspace), 'original'),
      modelStatus: {
        detector: 'not_connected',
        vlm: 'not_connected',
        llm: 'not_connected',
        notifications: 'draft_only',
      },
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `sitewatch-demo-${site.id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify('Демонстрационный отчёт экспортирован в JSON');
  }
  onMount(() => {
    try {
      reviews = parseReviews(localStorage.getItem(reviewStorageKey));
      workspaces = Object.fromEntries(
        sites.map((s) => [
          s.id,
          parseWorkspace(localStorage.getItem(`${workspaceKey}.${s.id}`), s.id),
        ]),
      );
    } catch {
      storageWarning = 'Локальное хранилище недоступно. Решения не переживут перезагрузку.';
    }
    ready = true;
    const requested = new URLSearchParams(location.search).get('observation');
    const target = observations.find((o) => o.id === requested);
    if (target) {
      siteId = target.siteId;
      selectedId = target.id;
      inspect(projectObservation(target, workspaces[target.siteId]));
    }
    const requestedView = new URLSearchParams(location.search).get('view');
    if (navigation.some((n) => n.id === requestedView)) view = requestedView as View;
    return () => clearTimeout(toastTimer);
  });
</script>

<svelte:head
  ><title>{site.name} · SiteWatch</title><meta name="robots" content="noindex" /></svelte:head
>
<svelte:window
  onkeydown={(event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      focusSearch();
    }
  }}
/>

<header class="app-header">
  <Brand compact />
  <nav aria-label="Разделы пульта">
    {#each navigation as item}<button
        class:active={view === item.id}
        aria-current={view === item.id ? 'page' : undefined}
        onclick={() => (view = item.id)}
        >{item.label}{#if item.id === 'journal' && reviews.length}<span class="nav-count"
            >{reviews.length}</span
          >{/if}</button
      >{/each}
  </nav>
  <div class="app-actions">
    <button class="icon-button" aria-label="Поиск наблюдений" onclick={focusSearch}
      ><MagnifyingGlassIcon size={20} /></button
    ><ThemeToggle /><span class="operator" title="Локальный демонстрационный оператор">ДМ</span>
  </div>
</header>
<div class="demo-banner">
  <div>
    <strong>ДЕМО</strong><span>Синтетические площадки и снимки. ML и бизнес-API не подключены.</span
    >
  </div>
  <button onclick={() => infoDialog.showModal()}>Что работает <ArrowUpRightIcon size={13} /></button
  >
</div>

<main id="main" class="workspace">
  <div class="page-heading">
    <div>
      <p class="breadcrumb">Рабочее пространство <span>/ {site.code}</span></p>
      <h1>{view === 'overview' ? site.name : navigation.find((n) => n.id === view)?.label}</h1>
      <p class="page-subtitle">
        {view === 'overview'
          ? `${site.address} · демонстрационная смена 19 сентября`
          : `${site.name} · 19 сентября 2026`}
      </p>
    </div>
    <div class="heading-actions">
      <label class="sr-only" for="site-select">Площадка</label><select
        id="site-select"
        class="control"
        bind:value={siteId}
        onchange={switchSite}
        >{#each sites as s}<option value={s.id}>{s.name}</option>{/each}</select
      ><button class="button secondary export" onclick={downloadReport}
        ><DownloadSimpleIcon size={17} />Экспорт отчёта</button
      >
    </div>
  </div>
  {#if storageWarning}<p class="storage-warning" role="alert">{storageWarning}</p>{/if}
  {#if view === 'analysis' || view === 'scenarios'}<label class="field analysis-select"
      >Наблюдение для анализа<select class="control" bind:value={selectedId}
        >{#each siteObservations as o}<option value={o.id}
            >{formatTime(o.time)} · {o.camera} · {o.zone}</option
          >{/each}</select
      ></label
    >{/if}

  {#if view === 'overview'}
    <div class="stats" aria-label="Сводка демонстрационной площадки">
      <div class="stat">
        <span>Источники наблюдений</span>
        <div>
          <strong>{site.cameras.toString().padStart(2, '0')}</strong><CameraIcon size={24} />
        </div>
        <small>Камеры в демо-сценарии</small>
      </div>
      <button
        class="stat"
        onclick={() => {
          view = 'observations';
          filter = 'all';
        }}
        ><span>Наблюдения за смену</span>
        <div>
          <strong>{siteObservations.length.toString().padStart(2, '0')}</strong><ArrowUpRightIcon
            size={23}
          />
        </div>
        <small>Снимки и контекст</small></button
      >
      <button
        class="stat attention"
        onclick={() => {
          view = 'observations';
          filter = 'needs_attention';
        }}
        ><span>Требуют внимания</span>
        <div>
          <strong>{attention.length.toString().padStart(2, '0')}</strong><WarningCircleIcon
            size={25}
          />
        </div>
        <small>{attention.length ? 'Ожидают решения ревьюера' : 'Все сигналы рассмотрены'}</small
        ></button
      >
      <button
        class="stat"
        onclick={() => {
          view = 'observations';
          filter = 'insufficient_evidence';
        }}
        ><span>Недостаточно данных</span>
        <div>
          <strong>{insufficient.length.toString().padStart(2, '0')}</strong><span
            class="unknown-mark">?</span
          >
        </div>
        <small>Не оцениваются как нарушения</small></button
      >
    </div>

    <div class="overview-grid">
      <section class="observation-view" aria-labelledby="camera-title">
        <div class="panel-heading">
          <div><h2 id="camera-title">{selected.camera}<span>{selected.zone}</span></h2></div>
          <span class="mono">{formatTime(selected.time)} МСК</span>
        </div>
        <EvidenceViewer
          src={selected.image}
          alt={`Синтетическое наблюдение: ${selected.zone}`}
          detections={markedDetections(selected, analyze(selected, workspace))}
          compact
        />
        <div class="frame-selector" aria-label="Выбор наблюдения">
          {#each siteObservations as observation}<button
              class:active={selected.id === observation.id}
              aria-pressed={selected.id === observation.id}
              onclick={() => (selectedId = observation.id)}
              ><span class="mono">{formatTime(observation.time)}</span><span
                >{observation.camera}</span
              ></button
            >{/each}
        </div>
        <div class="selected-caption">
          <span class={`status ${selected.assessment}`}
            >{assessmentLabels[selected.assessment]}</span
          ><button onclick={() => inspect(selected)}
            >Разобрать кадр <ArrowUpRightIcon size={16} /></button
          >
        </div>
      </section>
      <aside class="attention-panel" aria-labelledby="attention-title">
        <div class="panel-heading">
          <h2 id="attention-title">В фокусе внимания</h2>
          <span class="mono">{attention.length + insufficient.length}</span>
        </div>
        <div class="attention-list">
          {#each [...attention, ...insufficient] as observation}<button
              class="attention-row"
              onclick={() => inspect(observation)}
              ><div class="row-meta">
                <span class={`status ${observation.assessment}`}
                  >{assessmentLabels[observation.assessment]}</span
                ><span class="mono">{formatTime(observation.time)}</span>
              </div>
              <h3>{observation.title}</h3>
              <p>{observation.zone}</p>
              <span class="row-bottom">{observation.stage}<ArrowUpRightIcon size={17} /></span
              ></button
            >{/each}
          {#if !attention.length && !insufficient.length}<div class="empty-state">
              <CheckCircleIcon size={30} />
              <h3>Все сигналы рассмотрены</h3>
              <p>Решения доступны в журнале.</p>
            </div>{/if}
        </div>
        <button
          class="all-observations"
          onclick={() => {
            view = 'observations';
            filter = 'all';
          }}>Все наблюдения <ArrowRightIcon size={18} /></button
        >
      </aside>
    </div>
    <div class="overview-next">
      <span>Снимки каждые {workspace.interval} минут · архивная демо-смена, не live</span><button
        class="button secondary"
        onclick={() => (view = 'analysis')}
        >Правила, готовность и сводка <ArrowUpRightIcon size={16} /></button
      >
    </div>
    <Schedule plan={workspace.stages} />
  {:else if view === 'observations'}
    <div class="observation-tools">
      <div class="search-field">
        <MagnifyingGlassIcon size={19} /><input
          bind:this={searchInput}
          bind:value={query}
          aria-label="Поиск по наблюдениям"
          placeholder="Найти по зоне, технике или номеру…"
        /><kbd>⌘ K</kbd>
      </div>
      <button class="button primary" onclick={() => uploadDialog.open()}
        ><UploadSimpleIcon size={18} />Свой снимок</button
      >
    </div>
    <div class="filter-bar" aria-label="Фильтры наблюдений">
      {#each [{ id: 'all', label: 'Все' }, { id: 'needs_attention', label: 'Нужна проверка' }, { id: 'insufficient_evidence', label: 'Недостаточно данных' }, { id: 'consistent', label: 'По плану' }, { id: 'reviewed', label: 'Рассмотрены' }] as item}<button
          class:active={filter === item.id}
          aria-pressed={filter === item.id}
          onclick={() => (filter = item.id)}>{item.label}</button
        >{/each}<span>{filtered.length} из {siteObservations.length}</span>
    </div>
    <div class="observations-grid">
      {#each filtered as observation}<button
          class="observation-card"
          onclick={() => inspect(observation)}
          ><div class="card-image">
            <img
              src={observation.image}
              alt={`Иллюстрация: ${observation.zone}`}
              width="1536"
              height="1024"
              loading="lazy"
            /><span class="image-arrow"><ArrowUpRightIcon size={23} /></span>
          </div>
          <div class="card-content">
            <div class="row-meta">
              <span class={`status ${observation.assessment}`}
                >{assessmentLabels[observation.assessment]}</span
              ><span class="mono">{formatTime(observation.time)}</span>
            </div>
            <h2>{observation.title}</h2>
            <p>{observation.camera} / {observation.zone}</p>
            <div class="card-bottom">
              <span class="mono">{observation.id}</span><span
                >{activeReviews.find((r) => r.observationId === observation.id)
                  ? 'Решение сохранено'
                  : 'Открыть разбор'}</span
              >
            </div>
          </div></button
        >{/each}
    </div>
    {#if !filtered.length}<div class="empty-state">
        <MagnifyingGlassIcon size={36} />
        <h3>Наблюдений не найдено</h3>
        <p>Попробуйте другую зону или сбросьте фильтры.</p>
        <button
          class="button secondary"
          onclick={() => {
            query = '';
            filter = 'all';
          }}>Сбросить фильтры</button
        >
      </div>{/if}
  {:else if view === 'schedule'}
    <div class="plan-intro">{@render StackExplanation()}</div>
    <Schedule detailed plan={workspace.stages} />
    {#key siteId}<PlanEditor {workspace} onchange={saveWorkspace} />{/key}
  {:else if view === 'zones'}
    {#key siteId}<ZoneEditor {workspace} onchange={saveWorkspace} />{/key}
  {:else if view === 'analysis'}
    <ControlAnalysis
      observation={selected}
      {workspace}
      onplan={() => (view = 'schedule')}
      onzones={() => (view = 'zones')}
      onchange={saveWorkspace}
    />
  {:else if view === 'scenarios'}
    <ScenarioLab selected={scenario} onchange={(s) => (scenario = s)} />
    <ControlAnalysis
      observation={selected}
      {workspace}
      {scenario}
      onplan={() => (view = 'schedule')}
      onzones={() => (view = 'zones')}
      onchange={saveWorkspace}
    />
  {:else if view === 'journal'}
    <div class="journal-header">
      <p>Решения сохраняются локально. Исходные наблюдения остаются неизменными.</p>
      <button
        class="button secondary"
        disabled={!reviews.length}
        onclick={() => resetDialog.showModal()}>Сбросить демо</button
      >
    </div>
    {#if !ready}<div class="empty-state" role="status">
        Читаем локальный журнал…
      </div>{:else if !journal.length}<div class="empty-state">
        <ClockCounterClockwiseIcon size={36} />
        <h3>Здесь появятся ваши решения</h3>
        <p>Откройте наблюдение, добавьте комментарий и сохраните решение.</p>
        <button class="button primary" onclick={() => (view = 'observations')}
          >К наблюдениям <ArrowRightIcon size={18} /></button
        >
      </div>{:else}<div class="journal-list">
        {#each journal as review}{@const observation = observations.find(
            (o) => o.id === review.observationId,
          )!}
          <article>
            <div class="journal-icon"><CheckCircleIcon size={22} /></div>
            <div>
              <span class="journal-time"
                >{new Date(review.createdAt).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })} МСК</span
              >
              <h2>{decisionLabels[review.decision]}</h2>
              <p>{review.note}</p>
              {#if review.context && review.context !== context}<p class="muted">
                  Правила изменились после этого решения. Нужна повторная проверка.
                </p>{/if}
              <button onclick={() => inspect(projectObservation(observation, workspace))}
                >{observation.id} / {observation.title}<ArrowUpRightIcon size={15} /></button
              >
            </div>
          </article>{/each}
      </div>{/if}
  {/if}

  <footer class="app-footer">
    <span>SiteWatch / демо-пространство</span><button onclick={() => infoDialog.showModal()}
      >Границы демонстрации <ArrowUpRightIcon size={13} /></button
    ><span>Часовой пояс: МСК (UTC+3)</span>
  </footer>
</main>

{#snippet StackExplanation()}<h2>План даёт снимку контекст.</h2>
  <p>
    Обязательная и возможная техника, источник правил и сроки. Изменения применяются к этой
    площадке. Готовность вводится отдельно по замерам и не выводится из наличия техники.
  </p>{/snippet}

<ReviewDialog
  bind:this={reviewDialog}
  observation={currentReview}
  review={reviews.find((r) => r.observationId === currentReview?.id)}
  onsave={saveReview}
/>
<UploadDialog bind:this={uploadDialog} />
<dialog bind:this={resetDialog} aria-labelledby="reset-title">
  <div class="dialog-heading">
    <h2 id="reset-title">Сбросить решения демо?</h2>
    <button
      class="icon-button"
      aria-label="Закрыть подтверждение"
      onclick={() => resetDialog.close()}><XIcon size={20} /></button
    >
  </div>
  <div class="dialog-body info-body">
    <p>
      Будут удалены локальные решения по всем площадкам в этом браузере. Сначала экспортируйте
      отчёт, если хотите сохранить их.
    </p>
    <div class="reset-actions">
      <button class="button secondary" onclick={() => resetDialog.close()}>Отмена</button><button
        class="button primary"
        onclick={() => {
          persist([]);
          resetDialog.close();
          notify(
            storageWarning
              ? 'Решения сброшены в памяти. Хранилище недоступно.'
              : 'Локальные решения демо сброшены',
          );
        }}>Сбросить решения</button
      >
    </div>
  </div>
</dialog>
<dialog bind:this={infoDialog} aria-labelledby="info-title">
  <div class="dialog-heading">
    <h2 id="info-title">Честная демонстрация</h2>
    <button class="icon-button" aria-label="Закрыть описание" onclick={() => infoDialog.close()}
      ><XIcon size={20} /></button
    >
  </div>
  <div class="dialog-body info-body">
    <p>
      Работают поиск, фильтры, выбор площадки и наблюдений, рамки объектов, разбор правил, локальный
      журнал и экспорт JSON. Редактор правил и сроков, ручная разметка зон, соседние этапы, анализ
      обзора, сценарии ошибок, замеры готовности и объяснимая сводка также работают локально.
    </p>
    <p>
      Площадки, события, уверенность и разметка заданы вручную. Три сгенерированные иллюстрации
      переиспользуются в сценариях. Это не поток камер и не результаты модели.
    </p>
    <p>
      Решения остаются в localStorage этого браузера. Загруженные снимки хранятся только в памяти
      вкладки. Нет отправки файлов, аналитических трекеров или реальных уведомлений.
    </p>
    <p>
      Архитектура подключения: Rust-микросервисы, отдельные БД PostgreSQL, события NATS и
      Kubernetes. Бизнес-API и инференс ещё не подключены к этому пульту.
    </p>
  </div>
</dialog>
<div class="toast-region" role="status" aria-live="polite">
  {#if toast}<div class="toast">
      <CheckCircleIcon size={19} />{toast}<button
        class="icon-button"
        aria-label="Скрыть уведомление"
        onclick={() => (toast = '')}><XIcon size={16} /></button
      >
    </div>{/if}
</div>

<style>
  .analysis-select {
    max-width: 510px;
    margin-top: 20px;
  }
  .overview-next {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    flex-wrap: wrap;
    padding-top: 24px;
    font-size: 11px;
    color: var(--muted);
  }
  .app-header {
    height: 72px;
    padding: 0 32px;
    display: flex;
    align-items: center;
    gap: 28px;
    border-bottom: 1px solid var(--line);
    background: var(--bg);
    position: sticky;
    top: 0;
    z-index: 10;
  }
  nav {
    display: flex;
    gap: 22px;
    height: 100%;
  }
  nav button {
    font-size: 12px;
    color: var(--muted);
    border-bottom: 2px solid transparent;
    padding: 0;
    display: flex;
    align-items: center;
    gap: 7px;
    white-space: nowrap;
  }
  nav button.active {
    color: var(--text);
    border-color: var(--accent);
  }
  .nav-count {
    background: var(--raised);
    padding: 2px 5px;
    font-size: 10px;
    border-radius: 2px;
  }
  .app-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
  }
  .operator {
    width: 32px;
    height: 32px;
    display: grid;
    place-items: center;
    background: var(--raised);
    border-radius: 4px;
    font-size: 10px;
    margin-left: 10px;
  }
  .demo-banner {
    background: var(--accent-soft);
    color: var(--text);
    padding: 10px 32px;
    font-size: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
  }
  .demo-banner > div {
    display: flex;
    gap: 18px;
    align-items: center;
  }
  .demo-banner strong {
    font-size: 9px;
    letter-spacing: 0.08em;
    border-right: 1px solid var(--muted);
    padding-right: 18px;
  }
  .demo-banner button {
    font-size: 10px;
    white-space: nowrap;
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .workspace {
    max-width: 1600px;
    margin: auto;
    padding: 24px 32px;
  }
  .page-heading {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 24px;
    margin-bottom: 22px;
  }
  .breadcrumb {
    color: var(--muted);
    font-size: 10px;
    margin-bottom: 12px;
  }
  .breadcrumb span {
    margin-left: 10px;
  }
  h1 {
    font-size: clamp(29px, 3vw, 42px);
    letter-spacing: -0.065em;
    line-height: 1.2;
    font-weight: 600;
  }
  .page-subtitle {
    font-size: 11px;
    color: var(--muted);
    margin-top: 10px;
  }
  .heading-actions {
    display: flex;
    gap: 10px;
  }
  .heading-actions select,
  .heading-actions .button {
    font-size: 11px;
    min-height: 42px;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
    margin-bottom: 22px;
  }
  .stat {
    padding: 15px 26px 15px 0;
    margin: 0 26px 0 0;
    text-align: left;
    border-right: 1px solid var(--line);
  }
  .stat:last-child {
    border: 0;
    margin: 0;
    padding-right: 0;
  }
  .stat > span {
    color: var(--muted);
    font-size: 11px;
  }
  .stat > div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 8px;
  }
  .stat strong {
    font-size: 39px;
    font-weight: 500;
    letter-spacing: -0.06em;
  }
  .stat small {
    font-size: 9px;
    color: var(--muted);
  }
  .stat :global(svg) {
    color: var(--muted);
  }
  .stat.attention strong,
  .stat.attention :global(svg) {
    color: var(--warning);
  }
  button.stat:hover {
    background: var(--surface);
  }
  .unknown-mark {
    font-size: 25px;
    color: var(--muted);
  }
  .overview-grid {
    display: grid;
    grid-template-columns: 1.9fr 1fr;
    gap: 30px;
  }
  .panel-heading {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    min-height: 43px;
    margin-bottom: 14px;
  }
  .panel-heading h2 {
    font-size: 16px;
    font-weight: 650;
    letter-spacing: -0.03em;
  }
  .panel-heading h2 span {
    font-weight: 450;
    font-size: 10px;
    color: var(--muted);
    margin-left: 15px;
  }
  .panel-heading > .mono {
    font-size: 10px;
    color: var(--muted);
  }
  .frame-selector {
    display: flex;
    border-bottom: 1px solid var(--line);
  }
  .frame-selector button {
    text-align: left;
    padding: 12px 16px;
    display: grid;
    gap: 5px;
    border-bottom: 2px solid transparent;
    flex: 1;
  }
  .frame-selector button.active {
    background: var(--accent-soft);
    border-color: var(--accent);
  }
  .frame-selector .mono {
    font-size: 11px;
  }
  .frame-selector button > span:last-child {
    color: var(--muted);
    font-size: 9px;
  }
  .selected-caption {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding-top: 15px;
  }
  .selected-caption button {
    display: flex;
    gap: 18px;
    align-items: center;
    font-size: 11px;
  }
  .attention-panel {
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .attention-list {
    border-top: 1px solid var(--line);
  }
  .attention-row {
    display: block;
    width: 100%;
    text-align: left;
    padding: 19px 0;
    border-bottom: 1px solid var(--line);
  }
  .attention-row:hover {
    background: var(--surface);
    padding-inline: 10px;
  }
  .row-meta {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: center;
  }
  .row-meta .mono {
    font-size: 10px;
    color: var(--muted);
  }
  .attention-row h3 {
    font-size: 15px;
    margin-top: 14px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .attention-row p {
    font-size: 11px;
    color: var(--muted);
    margin-top: 7px;
  }
  .row-bottom {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 18px;
    font-size: 10px;
    color: var(--muted);
  }
  .row-bottom :global(svg) {
    color: var(--text);
  }
  .all-observations {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 18px 0 0;
    font-size: 11px;
    margin-top: auto;
  }
  .observation-tools {
    display: flex;
    gap: 20px;
    align-items: center;
    justify-content: space-between;
  }
  .search-field {
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--surface);
    border: 1px solid var(--line);
    padding: 0 15px;
    min-height: 48px;
    flex: 1;
    max-width: 540px;
    border-radius: 4px;
    color: var(--muted);
  }
  .search-field input {
    width: 100%;
    background: none;
    border: none;
    padding: 14px 0;
    font-size: 12px;
    outline: none;
    min-width: 0;
    color: var(--text);
  }
  .search-field:focus-within {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  kbd {
    white-space: nowrap;
    font-size: 10px;
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 3px 5px;
  }
  .filter-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 23px 0;
    flex-wrap: wrap;
  }
  .filter-bar button {
    padding: 8px 12px;
    font-size: 11px;
    color: var(--muted);
    border: 1px solid transparent;
    border-radius: 4px;
  }
  .filter-bar button.active {
    background: var(--raised);
    border-color: var(--line);
    color: var(--text);
  }
  .filter-bar > span {
    margin-left: auto;
    font-size: 10px;
    color: var(--muted);
  }
  .observations-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
  }
  .observation-card {
    padding: 0;
    text-align: left;
    background: var(--surface);
    overflow: hidden;
    border-radius: 4px;
  }
  .card-image {
    position: relative;
    overflow: hidden;
  }
  .card-image img {
    width: 100%;
    aspect-ratio: 1.7;
    object-fit: cover;
    transition: transform 400ms;
  }
  .observation-card:hover img {
    transform: scale(1.035);
  }
  .image-arrow {
    position: absolute;
    bottom: 12px;
    right: 12px;
    width: 35px;
    height: 35px;
    display: grid;
    place-items: center;
    background: var(--accent);
    color: var(--accent-ink);
  }
  .card-content {
    padding: 20px;
  }
  .card-content h2 {
    font-size: 19px;
    font-weight: 600;
    letter-spacing: -0.04em;
    margin-top: 20px;
  }
  .card-content > p {
    color: var(--muted);
    font-size: 11px;
    margin-top: 10px;
  }
  .card-bottom {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    border-top: 1px solid var(--line);
    padding-top: 17px;
    margin-top: 24px;
    color: var(--muted);
    font-size: 9px;
  }
  .plan-intro {
    padding: 30px;
    background: var(--surface);
  }
  .plan-intro :global(h2) {
    font-size: 28px;
    font-weight: 550;
    letter-spacing: -0.04em;
  }
  .plan-intro :global(p) {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.8;
    margin-top: 15px;
    max-width: 600px;
  }
  .journal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 25px;
    border-bottom: 1px solid var(--line);
    padding-bottom: 22px;
  }
  .journal-header p {
    color: var(--muted);
    font-size: 12px;
  }
  .journal-list {
    max-width: 900px;
  }
  .journal-list article {
    display: grid;
    grid-template-columns: 40px 1fr;
    gap: 18px;
    padding: 28px 0;
    border-bottom: 1px solid var(--line);
  }
  .journal-icon {
    color: var(--muted);
    padding-top: 3px;
  }
  .journal-time {
    font-size: 10px;
    color: var(--muted);
  }
  .journal-list h2 {
    font-size: 20px;
    margin: 8px 0;
    letter-spacing: -0.03em;
  }
  .journal-list p {
    font-size: 13px;
    line-height: 1.8;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }
  .journal-list button {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 18px 0 0;
    color: var(--muted);
    font-size: 11px;
    text-align: left;
  }
  .app-footer {
    border-top: 1px solid var(--line);
    margin-top: 45px;
    padding-top: 22px;
    display: flex;
    justify-content: space-between;
    gap: 20px;
    font-size: 9px;
    color: var(--muted);
  }
  .app-footer button {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 0;
    font-size: 9px;
  }
  .storage-warning {
    padding: 15px;
    margin-bottom: 20px;
    background: var(--warning-soft);
    color: var(--warning);
    font-size: 12px;
  }
  dialog {
    width: 600px;
  }
  .info-body {
    display: grid;
    gap: 20px;
    font-size: 13px;
    line-height: 1.8;
    color: var(--muted);
  }
  .reset-actions {
    display: flex;
    justify-content: end;
    gap: 15px;
  }
  .toast-region {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 30;
    max-width: calc(100vw - 48px);
  }
  .toast {
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--accent);
    color: var(--accent-ink);
    padding: 8px 8px 8px 20px;
    font-size: 12px;
    border-radius: 5px;
    box-shadow: 0 8px 35px rgb(10 18 7 / 0.18);
  }
  @media (max-width: 1100px) {
    .app-header {
      gap: 12px;
      height: auto;
      flex-wrap: wrap;
    }
    .app-header :global(.brand) {
      margin-block: 15px;
    }
    .app-actions {
      order: 2;
    }
    nav {
      gap: 20px;
      order: 3;
      width: 100%;
      height: 44px;
      overflow-x: auto;
    }
    .heading-actions {
      flex-direction: column;
    }
    .overview-grid {
      grid-template-columns: 1.6fr 1fr;
      gap: 22px;
    }
    .panel-heading h2 span {
      display: block;
      margin: 5px 0 0;
    }
    .observations-grid {
      grid-template-columns: repeat(2, 1fr);
    }
    .stat {
      margin-right: 18px;
      padding-right: 18px;
    }
  }
  @media (max-width: 767px) {
    .app-header {
      padding: 0 20px;
      gap: 15px;
      height: auto;
      flex-wrap: wrap;
    }
    .app-header :global(.brand) {
      margin-block: 15px;
    }
    .app-actions {
      order: 2;
    }
    nav {
      order: 3;
      width: 100%;
      height: 44px;
      gap: 28px;
      overflow-x: auto;
    }
    nav button {
      font-size: 11px;
    }
    .demo-banner {
      padding: 12px 20px;
      align-items: start;
    }
    .demo-banner > div {
      gap: 12px;
      align-items: start;
    }
    .demo-banner span {
      font-size: 9px;
      line-height: 1.7;
    }
    .demo-banner button {
      display: none;
    }
    .demo-banner strong {
      padding-right: 12px;
      margin-top: 2px;
    }
    .workspace {
      padding: 24px 20px;
    }
    .page-heading {
      flex-direction: column;
      align-items: stretch;
      gap: 20px;
    }
    .heading-actions {
      flex-direction: row;
      justify-content: space-between;
    }
    .heading-actions select {
      max-width: 55%;
    }
    .heading-actions .button {
      padding-inline: 12px;
      gap: 8px;
      font-size: 10px;
    }
    .stats {
      grid-template-columns: 1fr 1fr;
      margin-bottom: 20px;
    }
    .stat {
      padding: 18px 16px 18px 0;
      margin-right: 16px;
    }
    .stat:nth-child(2) {
      border-right: 0;
      margin: 0;
    }
    .stat:nth-child(n + 3) {
      border-top: 1px solid var(--line);
    }
    .stat strong {
      font-size: 34px;
    }
    .stat small {
      font-size: 8px;
    }
    .stat > span {
      font-size: 10px;
    }
    .overview-grid {
      grid-template-columns: 1fr;
      gap: 30px;
    }
    .panel-heading h2 span {
      display: inline;
      margin-left: 12px;
    }
    .frame-selector button {
      padding: 12px 10px;
    }
    .attention-row {
      padding: 20px 0;
    }
    .attention-row h3 {
      font-size: 17px;
    }
    .observation-tools {
      gap: 12px;
      flex-wrap: wrap;
    }
    .search-field {
      flex-basis: 100%;
      max-width: none;
    }
    .observation-tools .button {
      font-size: 12px;
      min-height: 42px;
    }
    .filter-bar {
      gap: 3px;
    }
    .filter-bar button {
      font-size: 10px;
      padding: 8px;
    }
    .observations-grid {
      grid-template-columns: 1fr;
    }
    .card-content h2 {
      font-size: 22px;
    }
    .journal-header {
      flex-wrap: wrap;
    }
    .plan-intro {
      padding: 25px;
    }
    .plan-intro :global(h2) {
      font-size: 24px;
    }
    .app-footer {
      flex-wrap: wrap;
    }
    .app-footer > span:last-child {
      width: 100%;
    }
    .operator {
      display: none;
    }
    .reset-actions {
      flex-wrap: wrap;
    }
  }
</style>
