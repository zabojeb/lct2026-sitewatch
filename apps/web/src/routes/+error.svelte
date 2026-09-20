<script lang="ts">
  import { page } from '$app/state';
  import Brand from '$lib/components/Brand.svelte';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
</script>

<svelte:head><title>{page.status} · SiteWatch</title></svelte:head>
<main id="main">
  <Brand />
  <div>
    <span class="mono">{page.status}</span>
    <h1>{page.status === 404 ? 'Этот участок ещё не найден.' : 'Не удалось открыть страницу.'}</h1>
    <p>
      {page.status === 404
        ? 'Проверьте адрес или вернитесь в рабочее пространство.'
        : 'Попробуйте обновить страницу. Сохранённые локальные решения останутся в браузере.'}
    </p>
    <a href="/app" class="button primary">Открыть пульт <ArrowRightIcon size={20} /></a><a
      href="/"
      class="button quiet">На главную</a
    >
  </div>
</main>

<style>
  main {
    max-width: 1100px;
    margin: auto;
    padding: 32px;
    min-height: 100dvh;
  }
  main > div {
    padding-top: 15vh;
    max-width: 650px;
  }
  .mono {
    color: var(--muted);
    font-size: 16px;
  }
  h1 {
    font-size: clamp(38px, 6vw, 68px);
    font-weight: 550;
    letter-spacing: -0.06em;
    line-height: 1.1;
    margin: 25px 0;
  }
  p {
    color: var(--muted);
    line-height: 1.8;
    font-size: 15px;
    margin-bottom: 30px;
  }
  .quiet {
    margin-left: 24px;
  }
</style>
