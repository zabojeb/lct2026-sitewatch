<script lang="ts">
  import { onMount } from 'svelte';
  import ArrowLeftIcon from 'phosphor-svelte/lib/ArrowLeftIcon';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import UploadSimpleIcon from 'phosphor-svelte/lib/UploadSimpleIcon';
  import Brand from '$lib/components/Brand.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import LiveEvaluation from '$lib/components/LiveEvaluation.svelte';
  import { detectionLabel, type ModelPrediction } from '$lib/model';

  let file = $state<File | null>(null);
  let preview = $state('');
  let prediction = $state<ModelPrediction | null>(null);
  let selected = $state<number | null>(null);
  let busy = $state(false);
  let error = $state('');
  let status = $state<'checking' | 'ready' | 'unavailable' | 'disabled'>('checking');
  let rulesStatus = $state<'checking' | 'ready' | 'unavailable' | 'disabled'>('checking');
  let modelVersion = $state('');
  const maxBytes = 12 * 1024 * 1024;
  const acceptedTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
  const mappedCount = $derived(
    prediction?.detections.filter((d) => d.mapping_status === 'mapped').length ?? 0,
  );

  async function refreshStatus() {
    try {
      const response = await fetch('/api/model/status', { cache: 'no-store' });
      const result = (await response.json()) as {
        status: typeof status;
        rules_status?: typeof rulesStatus;
        model_version?: string;
      };
      status = result.status;
      rulesStatus = result.rules_status ?? 'unavailable';
      modelVersion = result.model_version ?? '';
    } catch {
      status = 'unavailable';
      rulesStatus = 'unavailable';
    }
  }

  function choose(next: File | null) {
    if (preview) URL.revokeObjectURL(preview);
    if (next && !acceptedTypes.has(next.type)) {
      file = null;
      preview = '';
      prediction = null;
      selected = null;
      error = 'Выберите JPEG, PNG или WebP.';
      return;
    }
    if (next && (!next.size || next.size > maxBytes)) {
      file = null;
      preview = '';
      prediction = null;
      selected = null;
      error = 'Файл должен быть не больше 12 МБ.';
      return;
    }
    file = next;
    preview = next ? URL.createObjectURL(next) : '';
    prediction = null;
    selected = null;
    error = '';
  }

  async function analyze() {
    if (!file || busy) return;
    busy = true;
    error = '';
    prediction = null;
    try {
      const body = new FormData();
      body.set('image', file);
      const response = await fetch('/api/model/predict', { method: 'POST', body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Не удалось обработать кадр.');
      if (result.schema !== 'sitewatch.inference.v1' || !Array.isArray(result.detections)) {
        throw new Error('Сервис вернул несовместимый результат.');
      }
      prediction = result as ModelPrediction;
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Не удалось обработать кадр.';
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void refreshStatus();
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  });
</script>

<svelte:head>
  <title>Проверка кадра · SiteWatch</title>
  <meta name="robots" content="noindex" />
  <meta
    name="description"
    content="Живая проверка снимка моделью SiteWatch: детектор объектов и классификатор техники."
  />
</svelte:head>

<header class="model-header">
  <Brand compact />
  <a href="/app" class="back"><ArrowLeftIcon size={16} /> Вернуться в пульт</a>
  <ThemeToggle />
</header>

<main id="main" class="model-workspace">
  <div class="eyebrow"><span class="live-dot"></span> COMPUTER VISION / LIVE INFERENCE</div>
  <div class="intro">
    <div>
      <h1>Проверка кадра</h1>
      <p>Реальные веса модели: детектор объектов → ConvNeXt на каждом вырезанном объекте.</p>
    </div>
    <div class="service-state" class:online={status === 'ready'} aria-live="polite">
      <span
        >{status === 'ready'
          ? 'МОДЕЛЬ ГОТОВА'
          : status === 'checking'
            ? 'ПРОВЕРКА'
            : status === 'disabled'
              ? 'РЕЖИМ ВЫКЛЮЧЕН'
              : 'НЕТ СОЕДИНЕНИЯ'}</span
      >
      <small
        >{status === 'disabled'
          ? 'Живой режим выключен в конфигурации'
          : modelVersion || 'Сервис инференса'}</small
      >
    </div>
  </div>

  <div class="model-grid">
    <section class="upload-panel" aria-labelledby="source-title">
      <div class="section-caption">
        <span>01 / ИСТОЧНИК</span><span>JPEG · PNG · WEBP / ≤12 МБ</span>
      </div>
      <h2 id="source-title">Загрузите кадр площадки</h2>
      <p>
        Файл отправляется только внутреннему сервису модели и не добавляется в архив наблюдений.
      </p>
      <label class="upload-target">
        <UploadSimpleIcon size={32} />
        <strong>{file ? file.name : 'Выбрать изображение'}</strong>
        <span
          >{file
            ? `${(file.size / 1024 / 1024).toFixed(2)} МБ · можно заменить`
            : 'Снимок с камеры или фотография техники'}</span
        >
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onchange={(event) => choose(event.currentTarget.files?.[0] ?? null)}
        />
      </label>
      <button
        class="button primary run"
        disabled={!file || busy || status !== 'ready'}
        onclick={analyze}
      >
        {busy ? 'Анализируем кадр…' : 'Запустить анализ'}
        <ArrowRightIcon size={17} />
      </button>
      {#if status === 'disabled'}
        <p class="message">
          Для запуска включите <code>INFERENCE_DEMO_ENABLED=true</code> и поднимите inference-сервис.
        </p>
      {:else if status === 'unavailable'}
        <p class="message">Сервис не отвечает. Проверьте веса, контейнер и внутренний токен.</p>
      {/if}
      {#if status === 'unavailable' || rulesStatus === 'unavailable'}
        <button class="retry" onclick={refreshStatus}>Проверить соединение ещё раз</button>
      {/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <div class="privacy">
        Исходный кадр не сохраняется на сервере этим инструментом. Результат виден только в текущей
        вкладке.
      </div>
    </section>

    <section class="result-panel" aria-labelledby="result-title">
      <div class="section-caption">
        <span>02 / РЕЗУЛЬТАТ МОДЕЛИ</span><span
          >{prediction ? `${prediction.detections.length} ОБЪЕКТОВ` : 'ОЖИДАЕТ КАДР'}</span
        >
      </div>
      <h2 id="result-title">Обнаруженная техника</h2>
      {#if preview}
        <div class="image-shell">
          <div class="image-plane">
            <img src={preview} alt="Загруженный кадр для проверки моделью" />
            {#if prediction}
              {#each prediction.detections as detection, index}
                <button
                  class="box"
                  class:other={detection.mapping_status !== 'mapped'}
                  class:selected={selected === index}
                  style:left={`${detection.bounding_box.x_min * 100}%`}
                  style:top={`${detection.bounding_box.y_min * 100}%`}
                  style:width={`${(detection.bounding_box.x_max - detection.bounding_box.x_min) * 100}%`}
                  style:height={`${(detection.bounding_box.y_max - detection.bounding_box.y_min) * 100}%`}
                  aria-label={`${detectionLabel(detection)}, score классификатора ${detection.classifier_score.toFixed(3)}`}
                  aria-pressed={selected === index}
                  onclick={() => (selected = selected === index ? null : index)}
                  ><span>{detectionLabel(detection)}</span></button
                >
              {/each}
            {/if}
          </div>
        </div>
      {:else}
        <div class="empty-frame">
          <span>NO IMAGE / NO INFERENCE</span>
          <p>Рамки объектов появятся здесь после анализа.</p>
        </div>
      {/if}
      {#if prediction}
        <div class="result-summary">
          <strong>{mappedCount.toString().padStart(2, '0')}</strong><span
            >объектов сопоставлены с текущими классами правил</span
          >
          <strong>{(prediction.detections.length - mappedCount).toString().padStart(2, '0')}</strong
          ><span>остальные: other, человек или низкая уверенность</span>
        </div>
        {#if prediction.detections.length}
          <div class="detection-list">
            {#each prediction.detections as detection, index}
              <button
                class:active={selected === index}
                onclick={() => (selected = selected === index ? null : index)}
              >
                <span class="index">{String(index + 1).padStart(2, '0')}</span>
                <span class="name"
                  ><strong>{detectionLabel(detection)}</strong><small
                    >{detection.equipment_class ?? detection.mapping_status} · {detection.raw_class}</small
                  ></span
                >
                <span class="scores"
                  ><b>{detection.classifier_score.toFixed(3)}</b><small
                    >score класса · детектор {detection.detector_score.toFixed(3)}</small
                  ></span
                >
              </button>
            {/each}
          </div>
        {:else}
          <p class="no-objects">
            Объекты не найдены при текущем пороге детектора. Это не доказывает, что техники на
            площадке нет.
          </p>
        {/if}
      {/if}
    </section>
  </div>
  <LiveEvaluation {prediction} {file} {rulesStatus} />
  <aside class="evidence-note">
    <span>ВАЖНО / ГРАНИЦЫ ВЫВОДА</span>
    <p>
      Это результат моделей, а не вердикт о стройке. Для отклонения от графика нужны наблюдаемость
      зоны, актуальный этап, правила количества техники и подтверждение во времени. Уверенности
      моделей не откалиброваны как вероятности.
    </p>
  </aside>
</main>

<style>
  .model-header {
    min-height: 76px;
    padding: 0 clamp(20px, 4vw, 72px);
    display: flex;
    align-items: center;
    gap: 28px;
    border-bottom: 1px solid var(--line);
  }
  .back {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 9px;
    color: var(--muted);
    font-size: 13px;
  }
  .back:hover {
    color: var(--text);
  }
  .model-workspace {
    max-width: 1680px;
    margin: 0 auto;
    padding: clamp(28px, 4vw, 64px) clamp(20px, 4vw, 72px) 80px;
  }
  .eyebrow,
  .section-caption,
  .evidence-note > span {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    color: var(--muted);
  }
  .eyebrow {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 18px;
  }
  .live-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-soft);
  }
  .intro {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 28px;
    padding-bottom: 40px;
  }
  h1 {
    font-size: clamp(44px, 5.7vw, 88px);
    letter-spacing: -0.075em;
    line-height: 0.98;
    font-weight: 700;
  }
  .intro p {
    color: var(--muted);
    margin-top: 18px;
    font-size: 15px;
  }
  .service-state {
    border: 1px solid var(--line);
    padding: 14px 18px;
    min-width: 220px;
    display: grid;
    gap: 5px;
  }
  .service-state.online {
    border-color: var(--accent);
  }
  .service-state span {
    font-size: 11px;
    letter-spacing: 0.1em;
    font-weight: 800;
  }
  .service-state small {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--muted);
    font-size: 10px;
    overflow-wrap: anywhere;
  }
  .model-grid {
    display: grid;
    grid-template-columns: minmax(340px, 0.82fr) minmax(0, 1.4fr);
    border: 1px solid var(--line);
    background: var(--surface);
  }
  .upload-panel,
  .result-panel {
    min-width: 0;
    padding: clamp(24px, 3vw, 44px);
  }
  .upload-panel {
    border-right: 1px solid var(--line);
  }
  .section-caption {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 28px;
    border-bottom: 1px solid var(--line);
  }
  .section-caption span:last-child {
    color: var(--muted);
    text-align: right;
  }
  h2 {
    font-size: clamp(23px, 2.2vw, 34px);
    letter-spacing: -0.055em;
    line-height: 1.12;
    margin-top: 32px;
  }
  .upload-panel > p {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.6;
    margin-top: 12px;
    max-width: 42ch;
  }
  .upload-target {
    position: relative;
    cursor: pointer;
    margin-top: 34px;
    border: 1px dashed var(--muted);
    min-height: 230px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 10px;
    background: var(--bg);
  }
  .upload-target:hover {
    border-color: var(--accent);
  }
  .upload-target :global(svg) {
    color: var(--text);
    margin-bottom: 4px;
  }
  .upload-target strong {
    font-size: 15px;
    max-width: 100%;
    overflow-wrap: anywhere;
  }
  .upload-target span {
    color: var(--muted);
    font-size: 12px;
  }
  .upload-target input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
  }
  .upload-target:focus-within {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }
  .run {
    width: 100%;
    justify-content: space-between;
    margin-top: 18px;
  }
  .message,
  .error {
    margin-top: 18px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--warning);
  }
  .error {
    color: var(--danger);
  }
  .retry {
    margin-top: 10px;
    padding: 5px 0;
    color: var(--accent);
    font-size: 12px;
    border-bottom: 1px solid currentColor;
  }
  .retry:hover {
    color: var(--text);
  }
  code {
    font-size: 11px;
  }
  .privacy {
    margin-top: 30px;
    padding-top: 20px;
    border-top: 1px solid var(--line);
    color: var(--muted);
    font-size: 11px;
    line-height: 1.6;
  }
  .result-panel h2 {
    margin-bottom: 28px;
  }
  .image-shell {
    background: #10120f;
    border: 1px solid var(--line);
    padding: 12px;
  }
  .image-plane {
    position: relative;
    width: fit-content;
    max-width: 100%;
    margin: auto;
  }
  .image-plane img {
    display: block;
    max-width: 100%;
    max-height: 550px;
    width: auto;
    height: auto;
  }
  .box {
    position: absolute;
    border: 2px solid var(--accent);
    padding: 0;
  }
  .box.other {
    border-color: var(--warning);
  }
  .box.selected {
    outline: 2px solid white;
    outline-offset: 3px;
  }
  .box span {
    position: absolute;
    left: -2px;
    bottom: 100%;
    background: var(--accent);
    color: var(--accent-ink);
    font-size: 10px;
    font-weight: 800;
    white-space: nowrap;
    padding: 4px 7px;
  }
  .box.other span {
    background: var(--warning);
    color: var(--bg);
  }
  .empty-frame {
    aspect-ratio: 1.55;
    border: 1px dashed var(--line);
    background: repeating-linear-gradient(
      135deg,
      transparent 0 12px,
      color-mix(in srgb, var(--line) 16%, transparent) 12px 13px
    );
    display: grid;
    place-content: center;
    text-align: center;
    gap: 12px;
  }
  .empty-frame span {
    color: var(--muted);
    font:
      11px ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    letter-spacing: 0.12em;
  }
  .empty-frame p {
    color: var(--muted);
    font-size: 12px;
  }
  .result-summary {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 16px;
    margin-top: 26px;
    align-items: center;
  }
  .result-summary strong {
    font-size: 28px;
    letter-spacing: -0.06em;
  }
  .result-summary span {
    font-size: 12px;
    color: var(--muted);
  }
  .detection-list {
    margin-top: 26px;
    border-top: 1px solid var(--line);
  }
  .detection-list button {
    width: 100%;
    text-align: left;
    display: grid;
    grid-template-columns: 36px minmax(0, 1fr) auto;
    gap: 14px;
    align-items: center;
    border-bottom: 1px solid var(--line);
    padding: 14px 5px;
  }
  .detection-list button:hover,
  .detection-list button.active {
    background: var(--raised);
  }
  .index {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--text);
    font-size: 12px;
  }
  .name,
  .scores {
    display: grid;
    gap: 3px;
  }
  .name strong {
    font-size: 13px;
  }
  .name small,
  .scores small {
    font-size: 10px;
    color: var(--muted);
  }
  .scores {
    text-align: right;
  }
  .scores b {
    font-size: 14px;
  }
  .no-objects {
    color: var(--muted);
    font-size: 13px;
    margin-top: 24px;
    line-height: 1.6;
  }
  .evidence-note {
    border-left: 2px solid var(--accent);
    padding: 0 0 0 20px;
    margin-top: 34px;
    max-width: 1050px;
  }
  .evidence-note p {
    margin-top: 8px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.7;
  }
  @media (max-width: 920px) {
    .model-grid {
      grid-template-columns: 1fr;
    }
    .upload-panel {
      border-right: 0;
      border-bottom: 1px solid var(--line);
    }
    .intro {
      align-items: start;
      flex-direction: column;
    }
  }
  @media (max-width: 560px) {
    .model-header {
      gap: 12px;
    }
    .back {
      font-size: 0;
      gap: 0;
    }
    .back :global(svg) {
      width: 20px;
      height: 20px;
    }
    .section-caption {
      font-size: 9px;
    }
    .image-shell {
      padding: 4px;
    }
    .box span {
      max-width: 100px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }
</style>
