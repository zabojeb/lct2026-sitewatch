<script lang="ts">
  import ArrowUpRightIcon from 'phosphor-svelte/lib/ArrowUpRightIcon';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import CameraIcon from 'phosphor-svelte/lib/CameraIcon';
  import StackIcon from 'phosphor-svelte/lib/StackIcon';
  import CheckSquareIcon from 'phosphor-svelte/lib/CheckSquareIcon';
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import Brand from '$lib/components/Brand.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import { onMount } from 'svelte';
  let about: HTMLDialogElement;
  onMount(() => {
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('revealed');
            observer.unobserve(e.target);
          }
        }),
      { threshold: 0.12 },
    );
    document.querySelectorAll('[data-reveal]').forEach((el) => {
      el.classList.add('reveal-ready');
      observer.observe(el);
    });
    return () => observer.disconnect();
  });
</script>

<svelte:head>
  <title>SiteWatch · Вся стройка. В поле зрения.</title>
  <meta property="og:title" content="SiteWatch · Вся стройка. В поле зрения." />
  <meta
    property="og:description"
    content="Объяснимый контроль строительных площадок: кадр камеры, план работ, основание для решения."
  />
  <meta property="og:image" content="/images/site-aerial.webp" />
  <link
    rel="preload"
    as="image"
    href="/images/site-aerial.webp"
    imagesrcset="/images/site-aerial-768.webp 768w, /images/site-aerial.webp 1536w"
    imagesizes="100vw"
    fetchpriority="high"
  />
</svelte:head>

<header class="landing-nav">
  <Brand compact />
  <nav aria-label="Главная навигация">
    <a href="#capabilities">Возможности</a>
    <a href="#workflow">Как это работает</a>
  </nav>
  <div class="nav-actions">
    <ThemeToggle /><a class="nav-cta" href="/app/model">Начать анализ <ArrowUpRightIcon size={19} /></a>
  </div>
</header>

<main id="main">
  <section class="hero" aria-labelledby="hero-title">
    <img
      class="hero-image"
      src="/images/site-aerial.webp"
      srcset="/images/site-aerial-768.webp 768w, /images/site-aerial.webp 1536w"
      sizes="100vw"
      alt="Башенный кран над строящимся бетонным корпусом. Синтетическая архитектурная иллюстрация."
      width="1536"
      height="1024"
      fetchpriority="high"
    />
    <div class="hero-shade"></div>
    <div class="hero-copy">
      <p class="eyebrow">SITEWATCH / КОНТРОЛЬ СТРОЙКИ</p>
      <h1 id="hero-title">Вся стройка.<br /><span>В поле зрения.</span></h1>
      <p class="hero-description">
        Распознавайте технику на кадрах камер, проверяйте находки<br class="desktop-break" /> и
        сравнивайте наблюдения с планом работ.
      </p>
      <div class="hero-actions">
        <a href="/app/model" class="button primary">Начать анализ <ArrowUpRightIcon size={20} /></a>
        <a href="#workflow" class="button quiet">Как это работает <ArrowRightIcon size={20} /></a>
      </div>
    </div>
  </section>

  <section id="capabilities" class="capabilities section-wrap" aria-labelledby="capabilities-title">
    <div class="intro" data-reveal>
      <p class="section-kicker">РАБОТА С КАДРАМИ</p>
      <h2 id="capabilities-title">Кадр, техника,<br /><span>правило из плана.</span></h2>
      <p>Сервис показывает кадр, найденную технику и описание видимых работ. Проверку по плану оператор запускает отдельно.</p>
    </div>
    <div class="product-example" data-reveal>
      <div class="example-top">
        <span>01 / АНАЛИЗ СЦЕНЫ</span>
        <span>РАСПОЗНАВАНИЕ + ПЛАН</span>
      </div>
      <div class="example-grid">
        <div class="example-visual">
          <img
            src="/images/excavation.webp"
            srcset="/images/excavation-768.webp 768w, /images/excavation.webp 1536w"
            sizes="(max-width: 767px) 100vw, 65vw"
            alt="Экскаватор в котловане. Иллюстрация, не результат модели."
            width="1536"
            height="1024"
            loading="lazy"
          />
          <span>ИЛЛЮСТРАЦИЯ / НЕ РЕЗУЛЬТАТ АНАЛИЗА</span>
        </div>
        <div class="explanation">
          <span class="step-marker" aria-hidden="true">01—03</span>
          <h3>Разберите сцену.</h3>
          <p>
            Выберите готовую сцену или свои кадры. Модель покажет технику на каждом кадре. Для
            проверки по плану добавьте этап, правило и данные о камере — у демосцен они уже заполнены.
          </p>
          <dl>
            <dt>Два режима распознавания</dt>
            <dd>Стандартный и детальный (YOLO 640 и 960).</dd>
          </dl>
          <p class="detail-foot">Один кадр не доказывает отсутствие техники или простой.</p>
          <a href="/app/model" class="text-link">Анализировать сцену <ArrowUpRightIcon size={19} /></a>
        </div>
      </div>
    </div>
    <div class="principle" data-reveal>
      <span class="principle-mark" aria-hidden="true">↳</span>
      <p>Найденная техника — наблюдение на кадре.<br /><span>Этап работ подтверждается отдельно.</span></p>
    </div>
  </section>

  <section id="workflow" class="workflow section-wrap" aria-labelledby="workflow-title">
    <div class="workflow-copy" data-reveal>
      <h2 id="workflow-title">Как работает<br />проверка.</h2>
      <ol class="workflow-steps">
        <li>
          <CameraIcon size={24} />
          <div>
            <h3>Кадр</h3>
            <p>
              Выберите сцену или загрузите один кадр, несколько файлов либо папку.
            </p>
          </div>
        </li>
        <li>
          <StackIcon size={24} />
          <div>
            <h3>Контекст</h3>
            <p>Проверьте объекты на кадрах. Для сопоставления укажите этап и источник правила.</p>
          </div>
        </li>
        <li>
          <CheckSquareIcon size={24} />
          <div>
            <h3>Проверка</h3>
            <p>
              Сервис правил покажет основания и ограничения. Если кадров или обзора недостаточно,
              вывод об отклонении не появится.
            </p>
          </div>
        </li>
      </ol>
      <div class="closing-cta">
        <h3>Откройте сцену или свои кадры.</h3>
        <a href="/app/model" class="button primary">Анализировать сцену <ArrowUpRightIcon size={20} /></a
        >
      </div>
    </div>
    <div class="facade" data-reveal>
      <img
        src="/images/concrete.webp"
        srcset="/images/concrete-768.webp 768w, /images/concrete.webp 1536w"
        sizes="(max-width: 767px) 100vw, 45vw"
        alt="Геометрия бетонного каркаса и башенный кран. Синтетическая иллюстрация."
        width="1536"
        height="1024"
        loading="lazy"
      />
      <div></div>
    </div>
  </section>
</main>

<footer class="landing-footer">
  <Brand />
  <span>Демонстрационный контур анализа сцен</span>
  <button onclick={() => about.showModal()}>О демо <ArrowUpRightIcon size={16} /></button>
</footer>

<dialog bind:this={about} aria-labelledby="about-title">
  <div class="dialog-heading">
    <h2 id="about-title">Что работает в этом демо</h2>
    <button class="icon-button" aria-label="Закрыть" onclick={() => about.close()}
      ><XIcon size={22} /></button
    >
  </div>
  <div class="dialog-body about-copy">
    <p>
      Работают загрузка кадров, распознавание техники (детектор и классификатор), описание видимых
      работ мультимодальной моделью, ввод плана, правил и замеров и предварительная проверка по плану
      отдельным сервисом правил.
    </p>
    <p>
      Фотографии на этой странице — иллюстрации, не результат модели. В рабочем экране девять сцен:
      камера стройки, кадры из видеоролика и подборка команды; можно загрузить свои кадры. Камеры
      в реальном времени и автоматический поток ещё не подключены.
    </p>
    <p>
      Кадры распознаются сервисом SiteWatch и не хранятся на сервере. Для описания работ открытый
      кадр передаётся модели описания. Результаты и уменьшенные копии кадров сохраняются в архиве
      этого браузера. Не загружайте чувствительные материалы без согласования.
    </p>
    <a href="/app/model" class="button primary">Начать анализ <ArrowUpRightIcon size={20} /></a>
  </div>
</dialog>

<style>
  .landing-nav {
    height: 78px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    padding-inline: clamp(24px, 4vw, 64px);
    background: var(--bg);
  }
  nav {
    display: flex;
    gap: 34px;
    margin-left: auto;
    margin-right: auto;
    font-size: 12px;
    color: var(--muted);
  }
  nav a:hover {
    color: var(--text);
  }
  .nav-actions {
    display: flex;
    align-items: center;
    gap: 22px;
  }
  .nav-cta {
    display: flex;
    gap: 25px;
    align-items: center;
    font-size: 12px;
    font-weight: 700;
  }
  .hero {
    position: relative;
    min-height: 620px;
    height: min(800px, calc(100dvh - 78px));
    isolation: isolate;
    color: #f3f3eb;
    background: #171a16;
    overflow: hidden;
  }
  .hero-image {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: 50% 56%;
    z-index: -2;
  }
  .hero-shade {
    position: absolute;
    inset: 0;
    background:
      linear-gradient(90deg, rgb(12 18 12 / 0.86), rgb(12 18 12 / 0.4) 55%, rgb(12 18 12 / 0.1)),
      linear-gradient(0deg, rgb(16 23 15 / 0.3), transparent 35%);
    z-index: -1;
  }
  .hero-copy {
    max-width: 1600px;
    margin: auto;
    padding: clamp(66px, 9vh, 108px) clamp(24px, 4vw, 64px) 48px;
  }
  .eyebrow {
    color: #d7ddcf;
    font-size: 10px;
    font-weight: 550;
    letter-spacing: 0.14em;
    margin-bottom: 36px;
  }
  h1 {
    font-size: clamp(56px, 6.6vw, 104px);
    font-weight: 650;
    line-height: 1.04;
    letter-spacing: -0.067em;
    margin-left: -5px;
  }
  h1 span {
    color: #d4e7af;
  }
  .hero-description {
    font-size: clamp(14px, 1.3vw, 19px);
    line-height: 1.65;
    color: #e0e4d9;
    margin-top: 29px;
    max-width: 550px;
  }
  .hero-actions {
    display: flex;
    gap: 35px;
    margin-top: 34px;
  }
  .hero-actions .button {
    min-height: 53px;
  }
  .hero-actions .quiet {
    color: #f3f3eb;
  }
  .section-wrap {
    padding-inline: clamp(24px, 4vw, 64px);
    max-width: 1600px;
    margin: auto;
  }
  .capabilities {
    padding-top: 106px;
    padding-bottom: 88px;
  }
  .section-kicker {
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 20px;
  }
  h2 {
    font-size: clamp(38px, 4.8vw, 72px);
    font-weight: 550;
    letter-spacing: -0.065em;
    line-height: 1.08;
  }
  h2 span {
    color: var(--muted);
  }
  .intro > p:last-child {
    margin-top: 25px;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.7;
    max-width: 580px;
  }
  .product-example {
    margin-top: 48px;
  }
  .example-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--line);
    gap: 20px;
    padding: 17px 0;
    color: var(--muted);
    font:
      10px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    letter-spacing: 0.1em;
  }
  .example-grid {
    display: grid;
    grid-template-columns: 1.8fr 1fr;
    background: var(--surface);
  }
  .example-visual {
    position: relative;
    min-width: 0;
    min-height: 470px;
    overflow: hidden;
    background: var(--raised);
  }
  .example-visual img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .example-visual span {
    position: absolute;
    left: 20px;
    bottom: 20px;
    padding: 9px 11px;
    background: rgb(20 25 18 / 0.88);
    color: #edf0e8;
    font:
      10px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    letter-spacing: 0.08em;
  }
  .explanation {
    padding: clamp(24px, 3vw, 46px);
    display: flex;
    flex-direction: column;
  }
  .step-marker {
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 35px;
    font-family: monospace;
  }
  .explanation h3 {
    font-size: clamp(23px, 2.3vw, 34px);
    line-height: 1.18;
    font-weight: 550;
    letter-spacing: -0.05em;
  }
  .explanation > p {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.75;
    margin-top: 17px;
  }
  dl {
    margin: 30px 0 0;
    padding-top: 22px;
    border-top: 1px solid var(--line);
  }
  dt {
    color: var(--muted);
    font-size: 11px;
  }
  dd {
    margin: 7px 0 0;
    font-size: 17px;
  }
  .explanation .detail-foot {
    font-size: 11px;
  }
  .text-link {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: auto;
    padding-top: 32px;
    font-size: 12px;
  }
  .text-link:hover {
    color: var(--muted);
  }
  .principle {
    display: flex;
    align-items: start;
    gap: 30px;
    padding-top: 45px;
  }
  .principle-mark {
    font-size: 40px;
    line-height: 1;
    color: var(--muted);
  }
  .principle p {
    font-size: clamp(20px, 2.3vw, 34px);
    line-height: 1.35;
    letter-spacing: -0.04em;
  }
  .principle p span {
    color: var(--muted);
  }
  .workflow {
    display: grid;
    grid-template-columns: 1.1fr 1fr;
    padding-block: 80px 100px;
    border-top: 1px solid var(--line);
    gap: 9%;
  }
  .workflow-copy {
    padding-top: 15px;
  }
  .workflow-steps {
    margin: 40px 0 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 27px;
  }
  .workflow-steps li {
    display: flex;
    gap: 22px;
    align-items: start;
  }
  .workflow-steps :global(svg) {
    margin-top: 4px;
    color: var(--muted);
    flex-shrink: 0;
  }
  .workflow-steps h3 {
    font-size: 16px;
    font-weight: 600;
  }
  .workflow-steps p {
    margin-top: 7px;
    font-size: 12px;
    line-height: 1.7;
    max-width: 300px;
    color: var(--muted);
  }
  .closing-cta {
    margin-top: 52px;
  }
  .closing-cta h3 {
    font-size: 24px;
    max-width: 300px;
    font-weight: 500;
    letter-spacing: -0.04em;
    margin-bottom: 22px;
  }
  .facade {
    position: relative;
    min-height: 580px;
    overflow: hidden;
  }
  .facade img {
    height: 100%;
    width: 100%;
    object-fit: cover;
    object-position: 60%;
    filter: saturate(0.28);
  }
  .facade > div {
    position: absolute;
    inset: 0;
    background: linear-gradient(0deg, rgb(23 26 22 / 0.4), transparent 50%);
  }
  .landing-footer {
    padding: 30px clamp(24px, 4vw, 64px);
    border-top: 1px solid var(--line);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 25px;
  }
  .landing-footer > span {
    color: var(--muted);
    font-size: 12px;
  }
  .landing-footer button {
    display: flex;
    align-items: center;
    gap: 22px;
    font-size: 12px;
  }
  dialog {
    width: 620px;
  }
  .about-copy {
    display: grid;
    gap: 20px;
    font-size: 14px;
    line-height: 1.75;
    color: var(--muted);
  }
  .about-copy .button {
    justify-self: start;
  }
  @media (prefers-reduced-motion: no-preference) {
    .hero-copy {
      animation: enter 750ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
    }
    [data-reveal]:global(.reveal-ready) {
      opacity: 0;
      transform: translateY(22px);
      transition:
        opacity 650ms,
        transform 650ms;
    }
    [data-reveal]:global(.revealed) {
      opacity: 1;
      transform: none;
    }
    @keyframes enter {
      from {
        opacity: 0;
        transform: translateY(18px);
      }
      to {
        opacity: 1;
        transform: none;
      }
    }
  }
  @media (max-width: 1000px) {
    .landing-nav nav {
      gap: 20px;
    }
    .nav-actions {
      gap: 12px;
    }
    .hero {
      min-height: 580px;
    }
    .example-grid {
      grid-template-columns: 1.4fr 1fr;
    }
    .explanation {
      padding: 24px;
    }
    .step-marker {
      margin-bottom: 20px;
    }
    .explanation dl {
      margin-top: 18px;
    }
    .workflow {
      gap: 6%;
    }
  }
  @media (max-width: 767px) {
    .landing-nav {
      height: 68px;
      gap: 12px;
      padding-inline: 20px;
    }
    .landing-nav nav {
      display: none;
    }
    .nav-cta {
      font-size: 11px;
      gap: 8px;
    }
    .nav-actions {
      gap: 6px;
    }
    .hero {
      height: calc(100svh - 68px);
      min-height: 540px;
      max-height: 740px;
    }
    .hero-copy {
      padding: 64px 24px 40px;
    }
    .hero-image {
      object-position: 58%;
    }
    .hero-shade {
      background: linear-gradient(90deg, rgb(12 18 12 / 0.82), rgb(12 18 12 / 0.35));
    }
    .eyebrow {
      font-size: 8px;
      letter-spacing: 0.11em;
      margin-bottom: 32px;
    }
    h1 {
      font-size: clamp(43px, 9.2vw, 68px);
      margin-left: -2px;
    }
    .hero-description {
      font-size: 14px;
      max-width: 330px;
      margin-top: 24px;
    }
    .desktop-break {
      display: none;
    }
    .hero-actions {
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 28px;
    }
    .hero-actions .button {
      font-size: 12px;
      gap: 14px;
    }
    .capabilities {
      padding-block: 64px;
    }
    .example-grid {
      grid-template-columns: 1fr;
    }
    .example-visual {
      min-height: 300px;
    }
    .product-example {
      margin-top: 28px;
    }
    .explanation {
      padding: 28px;
    }
    .step-marker {
      display: none;
    }
    .explanation h3 {
      max-width: 290px;
    }
    .principle {
      gap: 18px;
    }
    .workflow {
      grid-template-columns: 1fr;
      padding-block: 50px 64px;
      gap: 40px;
    }
    .facade {
      min-height: 0;
      height: 380px;
      order: -1;
    }
    .workflow-steps {
      gap: 26px;
    }
    .landing-footer {
      flex-wrap: wrap;
      padding: 25px 24px;
    }
    .landing-footer > span {
      order: 3;
      width: 100%;
    }
  }
</style>
