<script lang="ts">
  import { untrack } from 'svelte';
  import { validateWorkspace, type Workspace } from '$lib/demo/workspace';
  let { workspace, onchange }: { workspace: Workspace; onchange: (w: Workspace) => void } =
    $props();
  let draft = $state<Workspace>(untrack(() => structuredClone($state.snapshot(workspace))));
  let selected = $state(untrack(() => workspace.zones[0].id));
  let error = $state('');
  $effect(() => {
    const next = structuredClone($state.snapshot(workspace));
    draft = next;
    untrack(() => {
      if (!next.zones.some((z) => z.id === selected)) selected = next.zones[0].id;
    });
  });
  const zone = $derived(draft.zones.find((z) => z.id === selected)!);
  function bounds(index: number, value: string) {
    zone.bounds[index] = Number(value) / 100;
  }
  function save(event: SubmitEvent) {
    event.preventDefault();
    error = validateWorkspace(draft);
    if (!error) onchange(structuredClone($state.snapshot(draft)));
  }
</script>

<section class="work-section" aria-labelledby="zones-title">
  <div class="work-heading">
    <div>
      <p class="eyebrow-small">02 / Пространственный контекст</p>
      <h2 id="zones-title">У каждой зоны — свой этап.</h2>
    </div>
    <span class="status">Ручная схема</span>
  </div>
  <p class="work-note">
    Выберите зону на схеме. Положение и обзор задаются вручную, не рассчитаны по камерам.
    Геореконструкция и калибровка камер пока не подключены.
  </p>
  <div class="zone-layout">
    <div>
      <div class="zone-map" aria-label="Схема зон площадки">
        <img
          src="/images/site-aerial.webp"
          alt="Синтетический общий вид стройки с условной схемой рабочих зон"
          width="1536"
          height="1024"
        />
        {#each draft.zones as item, i}<button
            class="zone-shape"
            class:chosen={zone.id === item.id}
            class:hidden-zone={item.coverage < 80}
            style:left={`${item.bounds[0] * 100}%`}
            style:top={`${item.bounds[1] * 100}%`}
            style:width={`${item.bounds[2] * 100}%`}
            style:height={`${item.bounds[3] * 100}%`}
            aria-label={`Редактировать зону: ${item.name}`}
            aria-pressed={zone.id === item.id}
            onclick={() => (selected = item.id)}
            ><span>0{i + 1} / {item.name}</span><b>{item.coverage}% обзора</b></button
          >{/each}
      </div>
      <p class="work-note">
        Сплошной контур — достаточно обзора по демо-порогу 80%. Штриховка — недостаточно данных, не
        нарушение.
      </p>
    </div>
    <form class="editor-form" onsubmit={save}>
      <label class="field"
        >Зона<select class="control" bind:value={selected}
          >{#each draft.zones as item}<option value={item.id}>{item.name}</option>{/each}</select
        ></label
      >
      <label class="field"
        >Название зоны<input bind:value={zone.name} maxlength={120} required /></label
      >
      <label class="field"
        >Основной этап<select
          class="control"
          bind:value={zone.stageId}
          onchange={() => (zone.adjacent = zone.adjacent.filter((id) => id !== zone.stageId))}
          >{#each draft.stages as stage}<option value={stage.id}>{stage.name}</option
            >{/each}</select
        ></label
      >
      <fieldset class="neighbor-fields">
        <legend>Разрешённые соседние этапы</legend
        >{#each draft.stages.filter((s) => s.id !== zone.stageId) as stage}<label
            class="check-field"
            ><input
              type="checkbox"
              checked={zone.adjacent.includes(stage.id)}
              onchange={(e) =>
                (zone.adjacent = e.currentTarget.checked
                  ? [...zone.adjacent, stage.id]
                  : zone.adjacent.filter((id) => id !== stage.id))}
            />{stage.name}</label
          >{/each}
        <p class="work-note">Учитываются только этапы, активные на дату снимка.</p>
      </fieldset>
      <label class="field"
        >Видимость зоны, %<input
          type="range"
          min="0"
          max="100"
          step="5"
          bind:value={zone.coverage}
        /><span>{zone.coverage}% · {zone.camera}</span></label
      >
      <fieldset class="bounds-fields">
        <legend>Границы на схеме, %</legend>
        <div class="field-grid">
          {#each ['Слева', 'Сверху', 'Ширина', 'Высота'] as label, i}<label class="field"
              >{label}<input
                type="number"
                min={i > 1 ? 5 : 0}
                max="100"
                step="1"
                value={Math.round(zone.bounds[i] * 100)}
                oninput={(e) => bounds(i, e.currentTarget.value)}
                required
              /></label
            >{/each}
        </div>
      </fieldset>
      <p class="error-message" role="alert">{error}</p>
      <button class="button primary" type="submit">Сохранить зону</button>
    </form>
  </div>
</section>
