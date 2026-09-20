<script lang="ts">
  import {
    analyze,
    progressEstimate,
    scenarios,
    summary,
    type Scenario,
    type Workspace,
  } from '$lib/demo/workspace';
  import { assessmentLabels, formatTime, type Observation } from '$lib/demo/data';
  let {
    observation,
    workspace,
    scenario = 'original',
    onplan,
    onzones,
  }: {
    observation: Observation;
    workspace: Workspace;
    scenario?: Scenario;
    onplan: () => void;
    onzones: () => void;
  } = $props();
  const analysis = $derived(analyze(observation, workspace, scenario));
  const progress = $derived(progressEstimate(analysis.stage));
  const report = $derived(summary(observation, analysis, scenario));
  const next = $derived(
    new Date(Date.parse(observation.time) + workspace.interval * 60000).toISOString(),
  );
  let copied = $state('');
  let draft = $state(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(report);
      copied = 'Сводка скопирована. Внешняя отправка не выполнялась.';
    } catch {
      copied = 'Копирование недоступно. Выделите текст сводки вручную.';
    }
  }
</script>

<section class="work-section analysis-section" aria-labelledby="analysis-title">
  <div class="work-heading">
    <div>
      <p class="eyebrow-small">03 / Основания для решения</p>
      <h2 id="analysis-title">Что говорит этот снимок.</h2>
    </div>
    <span class={`status ${analysis.assessment}`}>{assessmentLabels[analysis.assessment]}</span>
  </div>
  <div class="cadence-strip">
    <span><b>{workspace.interval} мин</b> интервал снимков</span><span
      >Кадр: <b>{formatTime(observation.time)} МСК</b></span
    ><span>Следующий по сценарию: <b>{formatTime(next)} МСК</b></span><span class="muted"
      >Архивное демо · не live</span
    >
  </div>
  {#if scenario !== 'original'}<p class="simulation-notice">
      Симуляция: {scenarios.find((s) => s.id === scenario)?.detail} Эти входы не распознаны на фотографии.
    </p>{/if}
  <div class="analysis-columns">
    <div>
      <div class="section-label">
        <h3>{analysis.stage.name}</h3>
        <button class="text-action" onclick={onplan}>Изменить правила ↗</button>
      </div>
      <dl class="evidence-facts">
        <div>
          <dt>Обязательная</dt>
          <dd>{analysis.required.join(', ') || 'Перечень не установлен'}</dd>
        </div>
        <div>
          <dt>Возможная</dt>
          <dd>{analysis.possible.join(', ') || 'Не задана'}</dd>
        </div>
        <div>
          <dt>Наблюдается</dt>
          <dd>{analysis.detected.join(', ') || 'Нет объектов'}</dd>
        </div>
        <div>
          <dt>Вне перечня</dt>
          <dd
            class:signal-red={analysis.extra.length > 0 &&
              analysis.assessment !== 'insufficient_evidence'}
          >
            {analysis.assessment === 'insufficient_evidence'
              ? 'Не оценивается: недостаточно данных'
              : analysis.extra.join(', ') || 'Нет'}
          </dd>
        </div>
      </dl>
      {#if analysis.alternatives.length}<div class="context-note">
          <strong>Другой возможный контекст</strong>
          <p>{analysis.alternatives.join(' · ')}</p>
          <small>Совпадение по технике, не вероятность и не установленный этап.</small>
        </div>{/if}
      <details class="method-detail">
        <summary>Источник правил и показателей</summary>
        <p>{analysis.stage.source}</p>
        <p>
          Правила введены командой / оператором. Обзор ({analysis.coverage}%) задан вручную. Объекты
          и уверенность размечены в демо, не получены моделью.
        </p>
        <p>
          Порог обзора 80%, временные аномалии и линейный план — демонстрационные допущения, а не
          строительные нормативы.
        </p>
      </details>
    </div>
    <div>
      <div class="section-label">
        <h3>Проверки и ограничения</h3>
        <button class="text-action" onclick={onzones}>Зона и обзор ↗</button>
      </div>
      <div class="findings">
        {#each analysis.findings as finding}<article class={`finding ${finding.level}`}>
            <span class="mono">{finding.code}</span>
            <h4>{finding.title}</h4>
            <dl>
              <dt>Ожидается</dt>
              <dd>{finding.expected}</dd>
              <dt>Наблюдается</dt>
              <dd>{finding.observed}</dd>
            </dl>
          </article>{:else}<article class="finding info">
            <h4>Набор техники согласуется с правилами</h4>
            <p>Это не подтверждение объёма, производительности или сроков.</p>
          </article>{/each}
      </div>
      <p class="work-note">
        Простой по одному кадру не устанавливается. Неизменное положение не исключает работу крана,
        насоса или экскаватора.
      </p>
    </div>
  </div>
  <div class="progress-summary">
    <div>
      <p class="eyebrow-small">Фактическая готовность</p>
      <strong
        >{analysis.stage.progress === null ? 'Нет замера' : `${analysis.stage.progress}%`}</strong
      ><small
        >{analysis.stage.progressSource ||
          'Добавьте акт или ручной замер в плане работ. VLM не подключена.'}</small
      >
    </div>
    <div>
      <p class="eyebrow-small">Сравнение с планом</p>
      <strong
        >{progress.delta === null
          ? 'Не оценивается'
          : progress.delta < 0
            ? `Отставание ${Math.abs(progress.delta)} п.п.`
            : progress.delta > 0
              ? `Опережение ${progress.delta} п.п.`
              : 'На уровне плана'}</strong
      ><small
        >Линейный план: {progress.planned}% на {analysis.stage.progressDate}. Не оценка по технике.</small
      >
    </div>
    <div>
      <p class="eyebrow-small">Сценарий завершения</p>
      <strong>{progress.finish || 'Недостаточно замеров'}</strong><small
        >{progress.delay === null
          ? 'Нужны два замера с положительным темпом.'
          : progress.delay > 0
            ? `На ${progress.delay} дн. позже плана при неизменном темпе.`
            : `${Math.abs(progress.delay)} дн. запаса при неизменном темпе.`} Не ML-прогноз.</small
      >
    </div>
  </div>
  <details class="summary-panel">
    <summary>Итоговая сводка и черновик алерта</summary>
    <p class="work-note">
      Детерминированная сводка с основаниями. LLM не подключена. Уведомления прорабу здесь не
      отправляются.
    </p>
    <pre>{report}</pre>
    <div class="editor-actions">
      <button class="button secondary" onclick={copy}>Копировать сводку</button><button
        class="button primary"
        onclick={() => (draft = !draft)}>{draft ? 'Скрыть черновик' : 'Подготовить алерт'}</button
      >
    </div>
    {#if draft}<div class="notification-draft">
        <strong>Черновик для прораба · не отправлен</strong>
        <p>
          {analysis.zone.name}: {analysis.findings
            .filter((f) => f.level !== 'info')
            .map((f) => f.title)
            .join('; ') || 'Сигналов для проверки нет'}. Снимок {observation.id}, {formatTime(
            observation.time,
          )} МСК.
        </p>
        <a href={`/app?observation=${observation.id}`}>Открыть доказательства ↗</a>
      </div>{/if}
    <p class="save-message" role="status">{copied}</p>
  </details>
</section>
