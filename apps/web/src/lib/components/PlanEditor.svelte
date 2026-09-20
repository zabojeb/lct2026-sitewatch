<script lang="ts">
  import { untrack } from 'svelte';
  import {
    equipment,
    validateWorkspace,
    type Equipment,
    type Workspace,
  } from '$lib/demo/workspace';
  let { workspace, onchange }: { workspace: Workspace; onchange: (w: Workspace) => void } =
    $props();
  let draft = $state<Workspace>(untrack(() => structuredClone($state.snapshot(workspace))));
  let selected = $state('excavation');
  let error = $state('');
  let importText = $state('');
  let importing = $state(false);
  let message = $state('');
  $effect(() => {
    draft = structuredClone($state.snapshot(workspace));
  });
  const stage = $derived(draft.stages.find((s) => s.id === selected) || draft.stages[0]);
  function setEquipment(key: Equipment, value: string) {
    stage.required = stage.required.filter((e) => e !== key);
    stage.possible = stage.possible.filter((e) => e !== key);
    if (value === 'required') stage.required = [...stage.required, key];
    if (value === 'possible') stage.possible = [...stage.possible, key];
    message = '';
  }
  function save(event: SubmitEvent) {
    event.preventDefault();
    error = validateWorkspace(draft);
    if (error) return;
    onchange(structuredClone($state.snapshot(draft)));
    message = 'План применён. Разбор наблюдений пересчитан.';
  }
  function importPlan() {
    try {
      if (importText.length > 100000) throw new Error('Слишком большой JSON (максимум 100 КБ).');
      const value = JSON.parse(importText);
      const next = value.workspace || value;
      const validation = validateWorkspace(next);
      if (validation) throw new Error(validation);
      if (
        next.stages.some((s: { id: string }) => !workspace.stages.some((b) => b.id === s.id)) ||
        next.zones.length !== workspace.zones.length ||
        next.zones.some((z: { id: string }) => !workspace.zones.some((b) => b.id === z.id))
      )
        throw new Error('План должен относиться к выбранной площадке и её этапам.');
      draft = structuredClone(next);
      importing = false;
      error = '';
      message = 'План проверен и загружен в редактор. Нажмите «Применить план» для сохранения.';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Некорректный JSON.';
    }
  }
</script>

<section class="work-section" aria-labelledby="rules-title">
  <div class="work-heading">
    <div>
      <p class="eyebrow-small">01 / Методика и график</p>
      <h2 id="rules-title">План, который можно проверить.</h2>
    </div>
    <button class="button secondary" onclick={() => (importing = !importing)}>Импорт JSON</button>
  </div>
  <p class="work-note">
    Настройки этой площадки сохраняются только в браузере. ГЭСН — кандидат на источник, не
    подтверждённое нормативное основание демо.
  </p>
  {#if importing}<div class="import-panel">
      <label class="field"
        >План JSON<textarea
          bind:value={importText}
          placeholder="Вставьте workspace из экспортированного отчёта"
          maxlength={100000}></textarea></label
      ><button class="button secondary" onclick={importPlan}>Проверить и загрузить</button>
    </div>{/if}
  <div class="editor-layout">
    <div class="stage-list" aria-label="Редактируемый этап">
      {#each draft.stages as item}<button
          class:chosen={stage.id === item.id}
          aria-pressed={stage.id === item.id}
          onclick={() => {
            selected = item.id;
            error = '';
            message = '';
          }}
          ><span>{item.name}</span><small
            >{item.observable ? 'Визуальный контроль' : 'Нужен другой источник данных'}</small
          ></button
        >{/each}
    </div>
    <form onsubmit={save} class="editor-form">
      <div class="field-grid">
        <label class="field"
          >Название этапа<input bind:value={stage.name} maxlength={120} required /></label
        ><label class="field"
          >Интервал снимков, мин<input
            type="number"
            bind:value={draft.interval}
            min="1"
            max="1440"
            step="1"
            required
          /></label
        ><label class="field"
          >Начало этапа<input type="date" bind:value={stage.start} required /></label
        ><label class="field"
          >Окончание этапа<input type="date" bind:value={stage.end} required /></label
        >
      </div>
      <label class="check-field"
        ><input type="checkbox" bind:checked={stage.observable} /> Этап можно оценить по внешним камерам</label
      >
      <fieldset class="equipment-editor">
        <legend>Требования к технике</legend>{#each Object.entries(equipment) as [key, label]}<label
            ><span>{label}</span><select
              class="control"
              aria-label={`${label}: требование`}
              value={stage.required.includes(key as Equipment)
                ? 'required'
                : stage.possible.includes(key as Equipment)
                  ? 'possible'
                  : 'none'}
              onchange={(e) => setEquipment(key as Equipment, e.currentTarget.value)}
              ><option value="none">Не предусмотрена</option><option value="required"
                >Обязательная</option
              ><option value="possible">Возможная</option></select
            ></label
          >{/each}
      </fieldset>
      <label class="field"
        >Основание правил<textarea bind:value={stage.source} maxlength={1000} required
        ></textarea><small
          >Документ, таблица, редакция и пункт либо явно указанная методика команды. Само заполнение
          поля не подтверждает норматив.</small
        ></label
      >
      <details class="progress-editor">
        <summary>Замеры готовности и сценарий завершения</summary>
        <p class="work-note">
          Ручной ввод по акту или замеру. Оставьте проценты пустыми, если данных нет. VLM не
          подключена.
        </p>
        <div class="field-grid">
          <label class="field"
            >Предыдущая готовность, %<input
              type="number"
              value={stage.previousProgress ?? ''}
              min="0"
              max="100"
              step="0.1"
              oninput={(e) =>
                (stage.previousProgress =
                  e.currentTarget.value === '' ? null : Number(e.currentTarget.value))}
            /></label
          >
          <label class="field"
            >Предыдущий замер<input type="date" bind:value={stage.previousDate} required /></label
          >
          <label class="field"
            >Текущая готовность, %<input
              type="number"
              value={stage.progress ?? ''}
              min="0"
              max="100"
              step="0.1"
              oninput={(e) =>
                (stage.progress =
                  e.currentTarget.value === '' ? null : Number(e.currentTarget.value))}
            /></label
          >
          <label class="field"
            >Текущий замер<input type="date" bind:value={stage.progressDate} required /></label
          >
        </div>
        <label class="field"
          >Источник готовности<input
            bind:value={stage.progressSource}
            maxlength={500}
            placeholder="Например: демонстрационный ручной замер"
          /></label
        >
      </details>
      <p class="error-message" role="alert">{error}</p>
      <p class="save-message" role="status">{message}</p>
      <div class="editor-actions">
        <button class="button primary" type="submit">Применить план</button><button
          type="button"
          class="button secondary"
          onclick={() => {
            draft = structuredClone($state.snapshot(workspace));
            error = '';
            message = 'Несохранённые изменения отменены.';
          }}>Отменить изменения</button
        >
      </div>
    </form>
  </div>
</section>
