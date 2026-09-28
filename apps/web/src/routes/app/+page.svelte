<script lang="ts">
  import { onMount } from 'svelte';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import ArrowUpRightIcon from 'phosphor-svelte/lib/ArrowUpRightIcon';
  import CameraIcon from 'phosphor-svelte/lib/CameraIcon';
  import CheckCircleIcon from 'phosphor-svelte/lib/CheckCircleIcon';
  import ClockCounterClockwiseIcon from 'phosphor-svelte/lib/ClockCounterClockwiseIcon';
  import InfoIcon from 'phosphor-svelte/lib/InfoIcon';
  import StackIcon from 'phosphor-svelte/lib/StackIcon';
  import Brand from '$lib/components/Brand.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';

  type ServiceState = 'checking' | 'ready' | 'unavailable' | 'disabled';
  let model = $state<ServiceState>('checking');
  let rules = $state<ServiceState>('checking');
  let version = $state('');
  let checkedAt = $state('');

  const label = (state: ServiceState) =>
    ({
      checking: 'Проверяем',
      ready: 'Работает',
      unavailable: 'Нет соединения',
      disabled: 'Не включён',
    })[state];

  async function refresh() {
    try {
      const response = await fetch('/api/model/status', { cache: 'no-store' });
      if (!response.ok) throw new Error('Status request failed');
      const result = (await response.json()) as {
        status?: ServiceState;
        rules_status?: ServiceState;
        model_version?: string;
      };
      model = result.status ?? 'unavailable';
      rules = result.rules_status ?? 'unavailable';
      version = result.model_version ?? '';
    } catch {
      model = 'unavailable';
      rules = 'unavailable';
      version = '';
    }
    checkedAt = new Intl.DateTimeFormat('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date());
  }

  onMount(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 30_000);
    return () => clearInterval(timer);
  });
</script>

<svelte:head>
  <title>Рабочий пульт · SiteWatch</title>
  <meta name="robots" content="noindex" />
  <meta
    name="description"
    content="Живой рабочий контур SiteWatch: проверка кадра моделью и сопоставление наблюдений с планом."
  />
</svelte:head>

<header class="app-header">
  <Brand compact />
  <nav aria-label="Навигация пульта">
    <a href="/app" aria-current="page">Пульт</a>
    <a href="/app/model">Проверка кадра</a>
  </nav>
  <ThemeToggle />
</header>

<main id="main" class="control-room">
  <section class="intro" aria-labelledby="intro-title">
    <div class="intro-image" aria-hidden="true"></div>
    <div class="intro-content">
      <p class="eyebrow"><span class="signal"></span> SITEWATCH / РАБОЧИЙ КОНТУР</p>
      <h1 id="intro-title">Сначала кадр.<br /><span>Затем вывод.</span></h1>
      <p class="intro-copy">
        Загрузите снимок площадки, посмотрите результат настоящей модели и сопоставьте несколько
        кадров с вашим графиком работ. Здесь нет подставленных объектов или готовых «нарушений».
      </p>
      <a class="button primary" href="/app/model">
        Проверить кадр <ArrowUpRightIcon size={19} />
      </a>
    </div>
    <div class="intro-index" aria-hidden="true">01 / 03</div>
  </section>

  <section class="status-section" aria-labelledby="status-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">СОСТОЯНИЕ СИСТЕМЫ</p>
        <h2 id="status-title">Сейчас на связи</h2>
      </div>
      <button class="refresh" onclick={refresh} aria-label="Обновить состояние сервисов">
        <ClockCounterClockwiseIcon size={17} /> Обновить
      </button>
    </div>
    <div class="status-grid" aria-live="polite">
      <article class="service" class:online={model === 'ready'}>
        <div class="service-top"><CameraIcon size={25} /><span>01 / ЗРЕНИЕ</span></div>
        <h3>Распознавание техники</h3>
        <p>Детектор и классификатор обрабатывают загруженный кадр. Рамки — свидетельства модели.</p>
        <div class="service-foot">
          <span class="state-dot"></span><strong>{label(model)}</strong>
          {#if version}<small title={version}>{version}</small>{/if}
        </div>
      </article>
      <article class="service" class:online={rules === 'ready'}>
        <div class="service-top"><StackIcon size={25} /><span>02 / КОНТЕКСТ</span></div>
        <h3>Правила и график</h3>
        <p>Отдельный сервис сравнивает независимые кадры с правилами этапа и ручным замером.</p>
        <div class="service-foot">
          <span class="state-dot"></span><strong>{label(rules)}</strong>
        </div>
      </article>
      <article class="service pending">
        <div class="service-top"><CheckCircleIcon size={25} /><span>03 / УЧЁТ</span></div>
        <h3>Архив наблюдений</h3>
        <p>Постоянное хранение снимков и решений пока не подключено к этому интерфейсу.</p>
        <div class="service-foot"><span class="state-dot"></span><strong>Не подключён</strong></div>
      </article>
    </div>
    <p class="checked">
      {checkedAt
        ? `Проверено в ${checkedAt} по времени вашего устройства`
        : 'Проверяем состояние сервисов…'}
    </p>
  </section>

  <section class="process" aria-labelledby="process-title">
    <div class="process-intro">
      <p class="eyebrow">КАК РАБОТАТЬ</p>
      <h2 id="process-title">Один контур.<br />Три честных шага.</h2>
      <p>
        Система не превращает отсутствие машины на одной фотографии в нарушение. Оператор задаёт
        источник плана и проверяет полноту обзора.
      </p>
    </div>
    <ol class="steps">
      <li>
        <span>01</span>
        <div>
          <h3>Загрузите настоящий снимок</h3>
          <p>JPEG, PNG или WebP до 12 МБ. Файл анализируется без добавления в архив.</p>
        </div>
      </li>
      <li>
        <span>02</span>
        <div>
          <h3>Соберите окно наблюдений</h3>
          <p>
            Укажите время и происхождение каждого кадра. Повторный файл не считается новым
            свидетельством.
          </p>
        </div>
      </li>
      <li>
        <span>03</span>
        <div>
          <h3>Сравните с вашим планом</h3>
          <p>
            Введите сроки, ожидаемую технику, количество и источник правила. Результат остаётся
            предпросмотром.
          </p>
        </div>
      </li>
    </ol>
  </section>

  <aside class="boundary" aria-label="Границы текущего контура">
    <InfoIcon size={21} />
    <p>
      <strong>Это не потоковый мониторинг и не журнал алертов.</strong> Камеры, проекты и автоматическая
      отправка уведомлений здесь ещё не подключены. Каждый результат относится только к данным, которые
      вы ввели в текущей вкладке.
    </p>
    <a href="/app/model">Перейти к анализу <ArrowRightIcon size={17} /></a>
  </aside>
</main>

<footer class="app-footer">
  <Brand compact /><span>SiteWatch · Проверяем факты, не имитируем их.</span>
</footer>

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
    gap: clamp(20px, 3vw, 38px);
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
  .control-room {
    max-width: 1680px;
    margin: auto;
  }
  .intro {
    position: relative;
    min-height: 580px;
    display: flex;
    align-items: center;
    padding: 72px clamp(24px, 5vw, 80px) 88px;
    isolation: isolate;
    overflow: hidden;
    background: #121711;
    color: #f2f3eb;
  }
  .intro-image {
    position: absolute;
    inset: 0;
    z-index: -1;
    background:
      linear-gradient(90deg, #101810 0%, rgb(16 24 16 / 0.94) 32%, rgb(16 24 16 / 0.2) 100%),
      url('/images/site-aerial.webp') 64% 58% / cover;
  }
  .intro-content {
    max-width: 730px;
  }
  .eyebrow {
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--muted);
    font:
      11px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    letter-spacing: 0.12em;
  }
  .intro .eyebrow {
    color: #dae2d1;
  }
  .signal {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 5px rgb(198 220 145 / 0.14);
  }
  h1 {
    margin-top: 31px;
    font-size: clamp(54px, 6.4vw, 104px);
    line-height: 1.04;
    letter-spacing: -0.075em;
    font-weight: 680;
  }
  h1 span {
    color: #d4e7af;
  }
  .intro-copy {
    max-width: 57ch;
    margin: 29px 0 30px;
    color: #dde4d6;
    font-size: clamp(14px, 1.25vw, 17px);
    line-height: 1.7;
  }
  .intro .button {
    min-height: 54px;
  }
  .intro-index {
    position: absolute;
    bottom: 31px;
    right: clamp(24px, 5vw, 80px);
    font:
      11px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    color: #e2e8d9;
    letter-spacing: 0.13em;
  }
  .status-section,
  .process {
    padding-inline: clamp(24px, 5vw, 80px);
  }
  .status-section {
    padding-top: 90px;
  }
  .section-heading {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 32px;
  }
  h2 {
    font-size: clamp(34px, 4.1vw, 64px);
    line-height: 1.04;
    letter-spacing: -0.065em;
    font-weight: 590;
  }
  .section-heading h2 {
    margin-top: 15px;
  }
  .refresh {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    min-height: 44px;
    padding: 10px 14px;
    border: 1px solid var(--line);
    font-size: 12px;
  }
  .refresh:hover {
    background: var(--raised);
  }
  .status-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    border: 1px solid var(--line);
    background: var(--surface);
  }
  .service {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 285px;
    padding: clamp(24px, 2.6vw, 36px);
  }
  .service + .service {
    border-left: 1px solid var(--line);
  }
  .service-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    color: var(--muted);
  }
  .service-top span {
    font:
      10px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    letter-spacing: 0.1em;
  }
  .service h3 {
    margin-top: 30px;
    font-size: clamp(19px, 1.8vw, 26px);
    letter-spacing: -0.045em;
  }
  .service p {
    color: var(--muted);
    font-size: 12px;
    line-height: 1.7;
    max-width: 36ch;
    margin-top: 10px;
  }
  .service-foot {
    display: flex;
    align-items: center;
    gap: 9px;
    margin-top: auto;
    padding-top: 24px;
    min-width: 0;
  }
  .service-foot strong {
    font-size: 12px;
    white-space: nowrap;
  }
  .service-foot small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-left: auto;
    color: var(--muted);
    font-size: 10px;
  }
  .state-dot {
    width: 7px;
    height: 7px;
    flex: 0 0 auto;
    border-radius: 50%;
    background: var(--muted);
  }
  .service.online .state-dot {
    background: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-soft);
  }
  .checked {
    color: var(--muted);
    font-size: 11px;
    margin-top: 13px;
  }
  .process {
    display: grid;
    grid-template-columns: 0.9fr 1.1fr;
    gap: 11%;
    padding-top: 130px;
    padding-bottom: 110px;
  }
  .process-intro h2 {
    margin-top: 20px;
  }
  .process-intro > p:last-child {
    color: var(--muted);
    max-width: 43ch;
    margin-top: 25px;
    font-size: 14px;
    line-height: 1.75;
  }
  .steps {
    margin: 0;
    padding: 0;
    list-style: none;
    border-top: 1px solid var(--line);
  }
  .steps li {
    display: grid;
    grid-template-columns: 65px 1fr;
    gap: 15px;
    padding: 27px 0 30px;
    border-bottom: 1px solid var(--line);
  }
  .steps li > span {
    font:
      13px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    color: var(--accent);
  }
  .steps h3 {
    font-size: 18px;
    letter-spacing: -0.03em;
  }
  .steps p {
    color: var(--muted);
    font-size: 12px;
    line-height: 1.7;
    max-width: 52ch;
    margin-top: 9px;
  }
  .boundary {
    display: flex;
    align-items: start;
    gap: 19px;
    margin: 0 clamp(24px, 5vw, 80px) 92px;
    padding: 26px 28px;
    border-left: 2px solid var(--accent);
    background: var(--surface);
  }
  .boundary > :global(svg) {
    flex: 0 0 auto;
    color: var(--accent);
  }
  .boundary p {
    color: var(--muted);
    line-height: 1.65;
    font-size: 12px;
    max-width: 75ch;
  }
  .boundary p strong {
    color: var(--text);
  }
  .boundary a {
    margin-left: auto;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    font-weight: 700;
  }
  .boundary a:hover {
    color: var(--accent);
  }
  .app-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    border-top: 1px solid var(--line);
    padding: 25px clamp(24px, 5vw, 80px);
  }
  .app-footer span {
    color: var(--muted);
    font-size: 11px;
  }
  @media (max-width: 900px) {
    .status-grid {
      grid-template-columns: 1fr;
    }
    .service {
      min-height: 205px;
    }
    .service + .service {
      border-left: 0;
      border-top: 1px solid var(--line);
    }
    .process {
      grid-template-columns: 1fr;
      gap: 45px;
      padding-top: 90px;
    }
    .boundary {
      flex-wrap: wrap;
    }
    .boundary a {
      margin-left: 40px;
    }
  }
  @media (max-width: 560px) {
    .app-header {
      gap: 13px;
      min-height: 64px;
      padding-inline: 18px;
    }
    .app-header nav {
      gap: 14px;
      font-size: 11px;
    }
    .app-header nav a {
      min-height: 64px;
    }
    .intro {
      min-height: 610px;
      padding: 60px 24px 76px;
      align-items: start;
    }
    .intro-image {
      background:
        linear-gradient(
          180deg,
          rgb(13 22 13 / 0.92),
          rgb(13 22 13 / 0.73) 65%,
          rgb(13 22 13 / 0.24)
        ),
        url('/images/site-aerial-768.webp') 55% center / cover;
    }
    h1 {
      font-size: clamp(50px, 11vw, 66px);
    }
    .intro-copy {
      margin-top: 24px;
    }
    .section-heading {
      align-items: start;
    }
    .refresh {
      font-size: 0;
      gap: 0;
    }
    .refresh :global(svg) {
      width: 19px;
      height: 19px;
    }
    .status-section {
      padding-top: 65px;
    }
    .process {
      padding-top: 80px;
      padding-bottom: 80px;
    }
    .boundary {
      margin-bottom: 64px;
      padding: 22px;
    }
    .boundary a {
      margin-left: 0;
      width: 100%;
    }
    .app-footer {
      flex-wrap: wrap;
    }
  }
</style>
