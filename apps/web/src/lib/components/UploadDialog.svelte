<script lang="ts">
  import { onDestroy } from 'svelte';
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import UploadSimpleIcon from 'phosphor-svelte/lib/UploadSimpleIcon';
  import ImageIcon from 'phosphor-svelte/lib/ImageIcon';
  let dialog: HTMLDialogElement;
  let preview = $state('');
  let filename = $state('');
  let error = $state('');
  let loading = $state(false);
  let sequence = 0;
  export function open() {
    dialog.showModal();
  }
  function clear() {
    sequence++;
    if (preview) URL.revokeObjectURL(preview);
    preview = '';
    filename = '';
    error = '';
    loading = false;
  }
  async function load(file?: File) {
    clear();
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      error = 'Выберите JPEG, PNG или WebP.';
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      error = 'Файл слишком большой. Максимум 15 МБ.';
      return;
    }
    loading = true;
    const current = sequence;
    const url = URL.createObjectURL(file);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      if (current !== sequence) {
        URL.revokeObjectURL(url);
        return;
      }
      preview = url;
      filename = file.name;
    } catch {
      URL.revokeObjectURL(url);
      if (current === sequence) error = 'Изображение повреждено или не поддерживается.';
    } finally {
      if (current === sequence) loading = false;
    }
  }
  onDestroy(clear);
</script>

<dialog bind:this={dialog} aria-labelledby="upload-title" onclose={clear}>
  <div class="dialog-heading">
    <h2 id="upload-title">Проверить свой снимок</h2>
    <button class="icon-button" aria-label="Закрыть загрузку" onclick={() => dialog.close()}
      ><XIcon size={22} /></button
    >
  </div>
  <div class="dialog-body upload-body">
    <p class="muted">
      Локальный предпросмотр. Изображение не покидает браузер. Модель пока не подключена, поэтому
      автоматической разметки не будет.
    </p>
    <label
      class="drop-zone"
      ondragover={(event) => event.preventDefault()}
      ondrop={(event) => {
        event.preventDefault();
        load(event.dataTransfer?.files[0]);
      }}
    >
      <UploadSimpleIcon size={32} /><strong>Выберите или перетащите снимок</strong><span
        >JPEG, PNG, WebP до 15 МБ</span
      >
      <input
        type="file"
        aria-label="Выбрать изображение"
        accept="image/jpeg,image/png,image/webp"
        onchange={(event) => {
          load(event.currentTarget.files?.[0]);
          event.currentTarget.value = '';
        }}
      />
    </label>
    <p class="error-message" aria-live="polite">{error}</p>
    {#if loading}<div class="loading" role="status">
        <ImageIcon size={30} />Подготовка изображения…
      </div>{/if}
    {#if preview}<figure>
        <img src={preview} alt="Локальный предпросмотр выбранного изображения" />
        <figcaption>{filename}</figcaption>
      </figure>
      <div class="result">
        <strong>Недостаточно данных для оценки</strong>
        <p>
          Нужны результаты детектора, площадка и активный этап. Загрузка снимка сама по себе не
          создаёт отклонение.
        </p>
      </div>
      <button class="button secondary" onclick={clear}>Убрать снимок</button>{/if}
  </div>
</dialog>

<style>
  dialog {
    width: 640px;
  }
  .upload-body {
    display: grid;
    gap: 16px;
    font-size: 13px;
    line-height: 1.7;
  }
  .drop-zone {
    position: relative;
    display: grid;
    justify-items: center;
    gap: 12px;
    border: 1px dashed var(--muted);
    background: var(--surface);
    padding: 36px 24px;
    border-radius: 4px;
    text-align: center;
    cursor: pointer;
  }
  .drop-zone:focus-within {
    outline: 2px solid var(--accent);
    outline-offset: 4px;
  }
  .drop-zone:hover {
    background: var(--raised);
  }
  .drop-zone span {
    font-size: 11px;
    color: var(--muted);
  }
  .drop-zone input {
    position: absolute;
    inset: 0;
    width: 100%;
    opacity: 0;
    cursor: pointer;
  }
  figure {
    margin: 0;
  }
  figure img {
    width: 100%;
    max-height: 300px;
    object-fit: contain;
    background: var(--surface);
  }
  figcaption {
    overflow-wrap: anywhere;
    font-size: 11px;
    color: var(--muted);
    padding-top: 12px;
  }
  .result {
    padding: 18px;
    background: var(--raised);
  }
  .result p {
    margin-top: 8px;
    color: var(--muted);
    font-size: 12px;
  }
  .loading {
    min-height: 150px;
    display: grid;
    place-content: center;
    gap: 15px;
    justify-items: center;
    background: var(--raised);
  }
</style>
