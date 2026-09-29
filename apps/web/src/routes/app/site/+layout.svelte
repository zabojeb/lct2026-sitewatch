<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import Brand from '$lib/components/Brand.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import EvidenceModal from '$lib/components/site/EvidenceModal.svelte';
  import DesignViewDialog from '$lib/components/site/DesignViewDialog.svelte';
  import { SiteConsole, provideSite } from '$lib/site/store.svelte';
  import '$lib/site/site.css';

  let { children } = $props();
  const site = provideSite(new SiteConsole());

  const tabs = [
    { href: '/app/site', label: 'Обзор' },
    { href: '/app/site/plan', label: 'План работ' },
    { href: '/app/site/zones', label: 'Зоны' },
    { href: '/app/site/history', label: 'Кадры' },
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

</script>

<svelte:head>
  <title>Архив проекта · SiteWatch</title>
  <meta name="robots" content="noindex" />
</svelte:head>

<header class="app-header">
  <Brand compact />
  <nav aria-label="Разделы SiteWatch">
    <a href="/">Главная</a>
    <a href="/app/model">Анализ сцен</a>
    <a href="/app/site" aria-current="page">Архив <span>ДЕМО</span></a>
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
        <span>Архивный проект</span>
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
        <a href="/app/model" class="new-scene">Анализировать сцену ↗</a>
      </div>
    </div>

    {#if site.storageFailed}
      <p class="storage-warning" role="status">
        Браузер не сохранил изменения — они действуют до перезагрузки, отчёт можно скачать.
      </p>
    {/if}

    <main id="main">
      {@render children()}
    </main>

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
    gap: 6px;
    border-bottom: 2px solid transparent;
  }
  .app-header nav a:hover,
  .app-header nav a[aria-current='page'] {
    color: var(--text);
  }
  .app-header nav a[aria-current='page'] {
    border-bottom-color: var(--accent);
  }
  .app-header nav span { font-size: 9px; letter-spacing: .06em; color: var(--muted); }
  .new-scene {
    display: inline-flex;
    align-items: center;
    min-height: 38px;
    padding: 0 13px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    font-size: 12px;
    font-weight: 700;
    white-space: nowrap;
  }
  .new-scene:hover { border-color: var(--accent); }
  @media (max-width: 560px) {
    .app-header {
      gap: 14px;
    }
    .app-header nav {
      gap: 12px;
      font-size: 11px;
    }
    .app-header nav span { display: none; }
  }
</style>
