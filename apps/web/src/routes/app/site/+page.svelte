<script lang="ts">
  import { onMount } from 'svelte';
  import ArrowLeftIcon from 'phosphor-svelte/lib/ArrowLeftIcon';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import DownloadSimpleIcon from 'phosphor-svelte/lib/DownloadSimpleIcon';
  import FrameView from '$lib/components/site/FrameView.svelte';
  import ShiftTimeline from '$lib/components/site/ShiftTimeline.svelte';
  import ScheduleEvidence from '$lib/components/site/ScheduleEvidence.svelte';
  import { isControllable } from '$lib/site/analysis';
  import { listArchivedRuns } from '$lib/model/archive';
  import { equipmentIcon } from '$lib/site/icons';
  import { cameras, clock, days, duration, numericDate, plural } from '$lib/site/format';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();
  let savedRuns = $state<{ count: number; latest: string }>({ count: 0, latest: '' });
  onMount(() => { void listArchivedRuns().then((runs) => { savedRuns = { count: runs.length, latest: runs[0]?.title ?? '' }; }).catch(() => {}); });
  const project = $derived(site.project!);
  const frame = $derived(site.frame);
  const analysis = $derived(site.analysis);
  const planned = $derived(site.plannedWindow);
  const reviewSignals = $derived(
    analysis?.alerts.filter((alert) => alert.code === 'extra' || alert.code === 'zone') ?? [],
  );

  const ROLE = {
    required: 'Обязательная',
    any: 'Одна из группы',
    optional: 'Допустимая',
    outside: 'Вне профиля',
  };

  const conclusion = $derived.by(() => {
    if (!analysis || !frame) return null;
    const plan = planned
      ? `По графику на ${numericDate(frame.timestamp)} запланирован этап «${planned.name}».`
      : `На ${numericDate(frame.timestamp)} этап в графике не задан.`;
    return `${plan} На снимках показаны обнаруженные объекты и гипотезы для проверки. Состав техники сам по себе не подтверждает фактический этап или отставание; отсутствие машины на одном срезе не доказывает нарушение.`;
  });

  function download() {
    const report = site.report();
    if (!report) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `sitewatch-${project.id}-${frame?.id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
</script>

{#if frame && analysis}
  <div class="page-heading">
    <div>
      <h1>Обзор проекта</h1>
      <p>
        {numericDate(frame.timestamp)} · срез: {analysis.snapshot.members.length} из {cameras(
          project.cameras.length,
        )}
      </p>
    </div>
    <div class="heading-actions">
      <label>
        Камера
        <select
          aria-label="Камера"
          value={site.cameraId}
          onchange={(e) => site.selectCamera(e.currentTarget.value)}
        >
          {#each project.cameras as camera (camera.id)}<option value={camera.id}
              >{camera.name}</option
            >{/each}
        </select>
      </label>
      <label>
        Профиль для сравнения
        <select
          aria-label="Профиль для сравнения"
          value={site.acceptedProfileId}
          onchange={(e) => {
            site.stageMode = 'manual';
            site.acceptedProfileId = e.currentTarget.value;
          }}
        >
          <option value="">По плану · {site.plannedProfile?.name ?? 'не задан'}</option>
          {#each site.profiles.filter(isControllable) as profile (profile.id)}
            <option value={profile.id}>{profile.name}</option>
          {/each}
        </select>
      </label>
      <button class="button secondary" onclick={download}
        ><DownloadSimpleIcon size={16} /> Скачать отчёт</button
      >
    </div>
  </div>

  <a class="my-runs-entry" href="/app/site/history">
    <span><span class="eyebrow">Ваши результаты</span><b>{savedRuns.count ? `${savedRuns.count} ${plural(savedRuns.count, ['запуск', 'запуска', 'запусков'])} в локальном архиве` : 'Сохранённых запусков пока нет'}</b><small>{savedRuns.latest || 'После распознавания кадры и выводы появятся здесь'}</small></span>
    <strong>Открыть архив ↗</strong>
  </a>

  <section class="scenario-picker" aria-label="Сценарии сравнения с планом">
    <div><span class="eyebrow">План и факт</span><h2>Два сценария для проверки</h2><p>Одна и та же дата начала свай, два демонстрационных графика. Разница считается по датам плана, а не по технике.</p></div>
    <button class:active={project.id === 'scenario'} onclick={() => site.load(fetch, 'scenario')}><span>01</span><b>Задержка</b><small>+13 дней по исходному плану</small></button>
    <button class:active={project.id === 'scenario-ahead'} onclick={() => site.load(fetch, 'scenario-ahead')}><span>02</span><b>Опережение</b><small>−14 дней по исходному плану</small></button>
  </section>

  {#if site.planComparison}<ScheduleEvidence />{/if}

  <section class="status-strip" aria-label="Статус площадки">
    <div>
      <span class="eyebrow">По графику сейчас</span>
      <b class="clamp" title={planned?.name}>{planned?.name ?? 'Вне графика'}</b>
      <small>
        {#if planned}
          {planned.row ? `строка ${planned.row} · ` : ''}{site.plannedProfile?.name} · {numericDate(
            planned.start,
          )} — {numericDate(planned.end)}
        {:else}Этап на эту дату не запланирован{/if}
      </small>
    </div>
    <div>
      <span class="eyebrow">Техника в срезе камер</span>
      <b>{Object.values(analysis.snapshot.counts).reduce((sum, count) => sum + count, 0)} объектов</b>
      <small>Этап работ по технике не определяется</small>
    </div>
    <button onclick={() => (site.designDialog = true)}>
      <span class="eyebrow">Проектный вид</span>
      <b>{site.designView ? 'Открыть' : 'Загрузить'}</b>
      <small>Визуальное сопоставление без процента готовности</small>
    </button>
    <div>
      <span class="eyebrow">Относительно плана</span>
      <b>{site.planComparison
        ? site.planComparison.days > 0
          ? `Задержка ${days(site.planComparison.days)}`
          : site.planComparison.days < 0
            ? `Опережение ${days(-site.planComparison.days)}`
            : 'По плану'
        : 'Не оценено'}</b>
      <small>{site.planComparison ? 'По дате факта из демосценария' : 'Нет подтверждённой даты факта'}</small>
    </div>
  </section>

  <div class="control-grid">
    <section class="panel camera-panel" aria-label="Кадр камеры">
      <div class="panel-head">
        <div>
          <span class="eyebrow">{site.camera?.name}</span>
          <h2>{clock(frame.timestamp)} · {numericDate(frame.timestamp)}</h2>
        </div>
        <span class="tone"
          >{project.provenance.boxes === 'synthetic' ? 'синтетические кадры' : 'архивный кадр'}</span
        >
      </div>
      <div class="panel-body">
        <FrameView
          {frame}
          tones={frame.boxes.map(() => ({ tone: 'neutral' as const, messages: [] }))}
          zones={site.zones[frame.cameraId] ?? []}
          alt="{site.camera?.name}, {numericDate(frame.timestamp)} {clock(frame.timestamp)}"
        />
        <div class="frame-nav">
          <div class="stamp">
            <b>{clock(frame.timestamp)}</b><span>{numericDate(frame.timestamp)}</span>
          </div>
          <div class="arrows">
            <button
              onclick={() => site.step(-1)}
              disabled={site.frameIndex <= 0}
              aria-label="Предыдущий кадр"
            >
              <ArrowLeftIcon size={18} />
            </button>
            <span>{site.frameIndex + 1} / {site.frames.length}</span>
            <button
              onclick={() => site.step(1)}
              disabled={site.frameIndex >= site.frames.length - 1}
              aria-label="Следующий кадр"
            >
              <ArrowRightIcon size={18} />
            </button>
          </div>
          <div class="position">
            <b>{site.camera?.name}</b><span>кадр {site.frameIndex + 1} из {site.frames.length}</span
            >
          </div>
        </div>
        <div class="members">
          <span class="eyebrow">Срез площадки на {clock(frame.timestamp)}</span>
          <ul>
            {#each analysis.snapshot.members as member (member.camera.id)}
              <li class:current={member.camera.id === frame.cameraId}>
                <button onclick={() => site.selectFrame(member.frame.id)}
                  >{member.camera.name}</button
                >
                <span
                  >{member.ageMs < 60_000 ? 'этот кадр' : `${duration(member.ageMs)} назад`}</span
                >
              </li>
            {/each}
            {#each project.cameras.filter((c) => !analysis.snapshot.members.some((m) => m.camera.id === c.id)) as camera (camera.id)}
              <li class="absent"><span>{camera.name}</span><span>ещё нет кадров</span></li>
            {/each}
          </ul>
        </div>
      </div>
    </section>

    <aside class="panel" aria-label="Техника и сигналы для проверки">
      <div class="panel-head">
        <div>
          <span class="eyebrow">Анализ площадки</span>
          <h2>Техника и контекст</h2>
        </div>
        <span
          class="tone {reviewSignals.length ? 'yellow' : ''}"
        >
          {reviewSignals.length ? `${reviewSignals.length} к проверке` : 'Сигналов нет'}
        </span>
      </div>
      <div class="panel-body">
        {#if conclusion}
          <div class="conclusion">
            <span class="eyebrow">Контекст наблюдения{frame.vlm ? ' · описание сцены' : ''}</span>
            <p>{conclusion}</p>
            {#if frame.vlm}
              <small>
                Описание сцены ({frame.vlm.model.split('/').at(-1)}, рассчитано заранее): {frame.vlm.scene}.
                Модель описания не создаёт сигналов.
              </small>
            {/if}
          </div>
        {/if}

        <div class="table equipment">
          <div class="row head">
            <span>Техника</span><span>Кадр</span><span>Площадка</span><span>Нужно</span>
          </div>
          {#each analysis.rows as row (row.slug + row.role)}
            {@const Icon = equipmentIcon(row.slug)}
            <div class="row">
              <span class="machine">
                <Icon size={18} />
                <span
                  ><b>{row.label}</b><small
                    >{ROLE[row.role]} · {cameras(row.cameras.length)}</small
                  ></span
                >
              </span>
              <strong>{row.frame}</strong>
              <strong>{row.site}</strong>
              <em>{row.need ?? '—'}</em>
            </div>
          {:else}
            <p class="hint">
              Для этапа по графику не задана техника, и на площадке нет машин вне профиля.
            </p>
          {/each}
        </div>

        <div class="alerts" aria-label="Сигналы для проверки">
          {#each reviewSignals as alert, index (`${alert.code}:${alert.message}:${index}`)}
            <div class="alert">
              <i class="dot {alert.tone}"></i>
              <span><b>{alert.title}</b><small>{alert.message}</small></span>
              {#if alert.code === 'zone'}<a href="/app/site/zones">Зоны →</a
                >{:else if alert.code === 'stage'}<a href="/app/site/plan">План →</a>{:else}<span
                ></span>{/if}
            </div>
          {:else}
            <div class="quiet-state">
              <b>Нет сигналов для проверки</b><span>По одному срезу нельзя оценить отсутствие техники или выполнение этапа.</span>
            </div>
          {/each}
        </div>
      </div>
    </aside>
  </div>

  <div class="section">
    <div class="section-head">
      <div>
        <h2>Кадры смены</h2>
        <p>Выберите кадр любой камеры — срез площадки и все выводы пересчитаются на его время.</p>
      </div>
    </div>
    <ShiftTimeline />
  </div>
{/if}

<style>
  .control-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.55fr) minmax(320px, 1fr);
    gap: 16px;
    margin-top: 16px;
    align-items: start;
  }
  @media (max-width: 1100px) {
    .control-grid {
      grid-template-columns: 1fr;
    }
  }
  .members ul {
    list-style: none;
    margin: 6px 0 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .members li {
    display: inline-flex;
    gap: 8px;
    align-items: center;
    padding: 5px 10px;
    border: 1px solid var(--line);
    border-radius: 999px;
    font-size: 12px;
  }
  .members li.current {
    border-color: var(--accent);
  }
  .members li span {
    color: var(--muted);
  }
  .members li button {
    font-weight: 700;
  }
  .members li.absent {
    opacity: 0.55;
    border-style: dashed;
  }
  .conclusion {
    display: grid;
    gap: 6px;
    padding: 12px 14px;
    border-left: 3px solid var(--accent);
    background: var(--raised);
    border-radius: var(--radius);
  }
  .conclusion p {
    margin: 0;
    font-size: 13px;
    line-height: 1.6;
  }
  .conclusion small {
    color: var(--muted);
    font-size: 11px;
    line-height: 1.5;
  }
  .equipment .row {
    grid-template-columns: minmax(0, 1fr) 48px 70px 70px;
  }
  .equipment .row strong,
  .equipment .row em {
    font-style: normal;
    text-align: center;
  }
</style>
