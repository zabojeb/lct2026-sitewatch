<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import BellIcon from 'phosphor-svelte/lib/BellIcon';
  import ListChecksIcon from 'phosphor-svelte/lib/ListChecksIcon';
  import InfoIcon from 'phosphor-svelte/lib/InfoIcon';
  import Brand from '$lib/components/Brand.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import TasksPanel from '$lib/components/site/TasksPanel.svelte';
  import JournalDrawer from '$lib/components/site/JournalDrawer.svelte';
  import EvidenceModal from '$lib/components/site/EvidenceModal.svelte';
  import DesignViewDialog from '$lib/components/site/DesignViewDialog.svelte';
  import { SOURCE_LABELS } from '$lib/site/catalog';
  import { SiteConsole, provideSite } from '$lib/site/store.svelte';
  import '$lib/site/site.css';

  let { children } = $props();
  const site = provideSite(new SiteConsole());

  const tabs = [
    { href: '/app/site', label: 'Контроль' },
    { href: '/app/site/plan', label: 'План работ' },
    { href: '/app/site/zones', label: 'Запретные зоны' },
    { href: '/app/site/history', label: 'Ход строительства' },
  ];

  onMount(() => {
    void site.load(fetch);
  });

  // Every edit of the plan, profiles, zones or stage choice is kept for this project.
  $effect(() => {
    if (site.status !== 'ready') return;
    void [
      site.plan,
      site.profileOverrides,
      site.zones,
      site.stageMode,
      site.acceptedProfileId,
      site.cameraId,
    ];
    site.save();
  });

  const redAlerts = $derived(site.journal.filter((e) => e.alert.tone === 'red').length);
</script>

<svelte:head>
  <title>Площадка · SiteWatch</title>
  <meta name="robots" content="noindex" />
</svelte:head>

<header class="app-header">
  <Brand compact />
  <nav aria-label="Навигация пульта">
    <a href="/app">Пульт</a>
    <a href="/app/site" aria-current="page">Площадка</a>
    <a href="/app/model">Проверка кадра</a>
  </nav>
  <ThemeToggle />
</header>

<div class="site-console">
  {#if site.status === 'loading'}
    <p class="site-state" role="status">Загружаем проект…</p>
  {:else if site.status === 'error'}
    <div class="site-state" role="alert">
      <b>Не удалось открыть проект</b>
      <span>{site.error}</span>
      <button class="button secondary" onclick={() => site.load(fetch)}>Повторить</button>
    </div>
  {:else if site.project}
    <div class="site-bar">
      <label class="project-pick">
        <span>Проект</span>
        <select
          value={site.project.id}
          onchange={(event) => site.load(fetch, event.currentTarget.value)}
          aria-label="Проект"
        >
          {#each site.projects as project (project.id)}
            <option value={project.id}>{project.name} · {project.subtitle}</option>
          {/each}
        </select>
      </label>
      <nav class="site-tabs" aria-label="Разделы площадки">
        {#each tabs as tab (tab.href)}
          <a href={tab.href} aria-current={page.url.pathname === tab.href ? 'page' : undefined}
            >{tab.label}</a
          >
        {/each}
      </nav>
      <div class="site-actions">
        <button
          class="icon-button counter"
          class:attention={site.tasks.length > 0}
          onclick={() => (site.panel = site.panel === 'tasks' ? null : 'tasks')}
          aria-label={`Задачи настройки: ${site.tasks.length}`}
          aria-expanded={site.panel === 'tasks'}
        >
          <BellIcon size={20} />
          {#if site.tasks.length}<b>{site.tasks.length}</b>{/if}
        </button>
        <button
          class="icon-button counter"
          class:danger={redAlerts > 0}
          onclick={() => (site.panel = site.panel === 'journal' ? null : 'journal')}
          aria-label={`Журнал отклонений: ${site.journal.length}`}
          aria-expanded={site.panel === 'journal'}
        >
          <ListChecksIcon size={20} />
          {#if site.journal.length}<b>{site.journal.length}</b>{/if}
        </button>
      </div>
    </div>

    <p class="provenance" class:synthetic={site.project.kind === 'synthetic'}>
      <InfoIcon size={16} />
      <span>
        <b>Рамки: {SOURCE_LABELS[site.project.provenance.boxes]}.</b>
        {site.project.provenance.text}
        {#each site.project.provenance.sources as source (source.url)}
          <a href={source.url} target="_blank" rel="noreferrer">{source.name} ↗</a>
        {/each}
        {#if site.plan.example}<em>График — пример для проверки, его можно менять.</em>{/if}
      </span>
    </p>
    {#if site.storageFailed}
      <p class="storage-warning" role="status">
        Браузер не сохранил изменения — они действуют до перезагрузки, отчёт можно скачать.
      </p>
    {/if}

    <main id="main">
      {@render children()}
    </main>

    {#if site.panel === 'tasks'}<TasksPanel />{/if}
    {#if site.panel === 'journal'}<JournalDrawer />{/if}
    {#if site.evidenceFrameId}<EvidenceModal />{/if}
    {#if site.designDialog}<DesignViewDialog />{/if}
  {/if}
</div>

<style>
  .app-header {
    min-height: 76px;
    padding-inline: clamp(20px, 4vw, 64px);
    display: flex;
    align-items: center;
    gap: clamp(24px, 4vw, 64px);
    border-bottom: 1px solid var(--line);
  }
  .app-header nav {
    display: flex;
    gap: clamp(16px, 3vw, 38px);
    margin-right: auto;
    font-size: 12px;
    color: var(--muted);
  }
  .app-header nav a {
    min-height: 76px;
    display: inline-flex;
    align-items: center;
    border-bottom: 2px solid transparent;
  }
  .app-header nav a:hover,
  .app-header nav a[aria-current='page'] {
    color: var(--text);
  }
  .app-header nav a[aria-current='page'] {
    border-bottom-color: var(--accent);
  }
  @media (max-width: 560px) {
    .app-header {
      gap: 14px;
    }
    .app-header nav {
      gap: 12px;
      font-size: 11px;
    }
  }
</style>
