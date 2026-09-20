<script lang="ts">
  import { scenarios, type Scenario } from '$lib/demo/workspace';
  let { selected, onchange }: { selected: Scenario; onchange: (s: Scenario) => void } = $props();
  let season = $state('summer');
  let weather = $state('dry');
  let background = $state('excavation');
  let position = $state('near');
  let notice = $state('');
  function download() {
    const manifest = {
      schema: 'sitewatch.synthetic.plan.v1',
      status: 'planned_not_generated',
      source: 'operator_configuration',
      season,
      weather,
      background,
      position,
      scenarios: scenarios.map((s) => ({ code: s.id, title: s.name })),
      constraints: [
        'No source camera images',
        'Do not use demo illustrations as evaluation evidence',
        'Split by site/camera before training',
      ],
      generatedAt: new Date().toISOString(),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' }),
    );
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sitewatch-synthetic-plan.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notice = 'План выгружен. Изображения и обучающий датасет не создавались.';
  }
</script>

<section class="work-section" aria-labelledby="scenarios-title">
  <div class="work-heading">
    <div>
      <p class="eyebrow-small">04 / Стенд проверок</p>
      <h2 id="scenarios-title">Не один удобный пример.</h2>
    </div>
    <span class="status">Синтетические входы</span>
  </div>
  <p class="work-note">
    Проверьте поведение интерфейса на пропусках обзора, соседних этапах и ошибках времени. Сценарии
    не изменяют исходный снимок и не являются измерением качества ML.
  </p>
  <div class="scenario-grid">
    {#each scenarios as item, index}<button
        class="scenario-option"
        class:chosen={selected === item.id}
        aria-pressed={selected === item.id}
        onclick={() => onchange(item.id)}
        ><span class="mono">{String(index + 1).padStart(2, '0')}</span><strong>{item.name}</strong
        ><small>{item.detail}</small></button
      >{/each}
  </div>
  <details class="dataset-plan">
    <summary>Разнообразие синтетических данных</summary>
    <p class="work-note">
      Конструктор задания для ML-команды. Генерация не запускается. Ракурсы, сезон, погода и фон
      должны быть покрыты реальным датасетом отдельно.
    </p>
    <div class="field-grid">
      <label class="field"
        >Сезон<select class="control" bind:value={season}
          ><option value="summer">Лето</option><option value="winter">Зима</option><option
            value="autumn">Осень</option
          ></select
        ></label
      ><label class="field"
        >Погода<select class="control" bind:value={weather}
          ><option value="dry">Ясно / сухо</option><option value="rain">Дождь</option><option
            value="fog">Туман</option
          ></select
        ></label
      ><label class="field"
        >Фон и объект<select class="control" bind:value={background}
          ><option value="excavation">Котлован</option><option value="frame">Каркас здания</option
          ><option value="urban">Плотная городская застройка</option></select
        ></label
      ><label class="field"
        >Положение техники<select class="control" bind:value={position}
          ><option value="near">Близко к камере</option><option value="far">Дальний план</option
          ><option value="occluded">Частично перекрыта</option></select
        ></label
      >
    </div>
    <button class="button secondary" onclick={download}>Экспорт задания для датасета</button>
    <p class="save-message" role="status">{notice}</p>
  </details>
</section>
