<script lang="ts">
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();
  let error = $state('');
  const close = () => (site.designDialog = false);

  /** Downscale to at most 1280 px so the view fits into browser storage. */
  async function importView(file: File) {
    error = '';
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
      error = 'Выберите JPEG, PNG или WebP.';
      return;
    }
    const source = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = reject;
      image.src = source;
    });
    const scale = Math.min(1, 1280 / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    canvas.getContext('2d')?.drawImage(image, 0, 0, canvas.width, canvas.height);
    site.setDesignView({ image: canvas.toDataURL('image/jpeg', 0.82), name: file.name });
  }
</script>

<svelte:window onkeydown={(event) => event.key === 'Escape' && close()} />

<div
  class="backdrop"
  role="presentation"
  onclick={(event) => event.target === event.currentTarget && close()}
>
  <div class="dialog narrow" role="dialog" aria-modal="true" aria-label="Проектный вид">
    <header>
      <div>
        <span class="eyebrow">Визуальная готовность</span>
        <h2>Проектный вид</h2>
      </div>
      <button class="icon-button" onclick={close} aria-label="Закрыть"><XIcon size={20} /></button>
    </header>
    <div class="dialog-body">
      {#if site.designView}
        <figure>
          <img src={site.designView.image} alt="Загруженный проектный вид" />
          <figcaption>
            <b>{site.designView.name}</b>
            <span>
              {#if site.readiness}
                Готовность {site.readiness.score}% · сходство ракурса {site.readiness.similarity}% ·
                уверенность {site.readiness.confidence}
              {:else}
                Сравнение выполняется на странице контроля для текущего кадра
              {/if}
            </span>
          </figcaption>
        </figure>
      {/if}
      <label class="upload">
        <span class="button primary"
          >{site.designView ? 'Заменить изображение' : 'Выбрать изображение'}</span
        >
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onchange={(event) => {
            const file = event.currentTarget.files?.[0];
            if (file) void importView(file);
          }}
        />
      </label>
      {#if error}<p role="alert" class="error">{error}</p>{/if}
      <p class="hint">
        Загрузите визуализацию итогового здания примерно с того же ракурса, что и камера. Оценка
        складывается из структурного сходства кадра и проекта (55%), положения принятого этапа в
        графике (30%) и контекста сцены (15%). Это предварительная визуальная оценка для оператора,
        а не приёмка объёмов: для неё нужны элементы BIM и поэлементное сравнение.
      </p>
      {#if site.designView}
        <button class="button quiet" onclick={() => site.setDesignView(null)}
          >Удалить проектный вид</button
        >
      {/if}
    </div>
  </div>
</div>

<style>
  figure {
    margin: 0;
    display: grid;
    gap: 8px;
  }
  figure img {
    width: 100%;
    border-radius: var(--radius);
  }
  figcaption {
    display: grid;
    gap: 2px;
    font-size: 13px;
  }
  figcaption span {
    color: var(--muted);
    font-size: 12px;
  }
  .upload input {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
  }
  .upload {
    position: relative;
    width: fit-content;
    cursor: pointer;
  }
  .upload:focus-within .button {
    outline: 2px solid var(--accent);
  }
  .error {
    margin: 0;
    color: var(--danger);
    font-size: 13px;
  }
</style>
