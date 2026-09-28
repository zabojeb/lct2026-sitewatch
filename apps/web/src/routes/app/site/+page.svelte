<script lang="ts">
  import ArrowLeftIcon from 'phosphor-svelte/lib/ArrowLeftIcon';
  import ArrowRightIcon from 'phosphor-svelte/lib/ArrowRightIcon';
  import DownloadSimpleIcon from 'phosphor-svelte/lib/DownloadSimpleIcon';
  import FrameView from '$lib/components/site/FrameView.svelte';
  import ShiftTimeline from '$lib/components/site/ShiftTimeline.svelte';
  import { isControllable } from '$lib/site/analysis';
  import { equipmentIcon } from '$lib/site/icons';
  import { cameras, clock, days, duration, numericDate, percent, time } from '$lib/site/format';
  import { assessReadiness } from '$lib/site/readiness';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();
  const project = $derived(site.project!);
  const frame = $derived(site.frame);
  const analysis = $derived(site.analysis);
  const planned = $derived(site.plannedWindow);
  const observed = $derived(analysis?.observed ?? null);

  const ROLE = {
    required: 'Обязательная',
    any: 'Одна из группы',
    optional: 'Допустимая',
    outside: 'Вне профиля',
  };

  const variance = $derived.by(() => {
    const v = site.variance;
    if (v.reason === 'unplanned')
      return {
        tone: 'yellow',
        text: 'Наблюдаемого этапа нет в графике',
        detail: 'Добавьте его в план или проверьте профиль',
      };
    if (v.reason === 'none' && v.segment)
      return {
        tone: 'green',
        text: 'По графику',
        detail: `«${v.segment.profile.name}» в плановых датах`,
      };
    if (v.reason === 'lead')
      return {
        tone: 'green',
        text: `Опережение ${days(-v.days)}`,
        detail: 'Этап начался раньше плана',
      };
    if (v.reason === 'start' || v.reason === 'end')
      return {
        tone: 'red',
        text: `Отставание ${days(v.days)}`,
        detail:
          v.reason === 'end'
            ? `Плановое окончание ${numericDate(v.planned!.end)}, камеры видят этап ${numericDate(v.segment!.end)}`
            : `Плановый старт ${numericDate(v.planned!.start)}, по камерам ${numericDate(v.segment!.start)}`,
      };
    return { tone: '', text: 'Нет наблюдений', detail: '' };
  });

  const conclusion = $derived.by(() => {
    if (!analysis || !frame) return null;
    const parts: string[] = [];
    if (planned && observed) {
      const differs = observed.profile.id !== planned.profileId;
      parts.push(
        differs
          ? `По графику должен идти этап «${planned.name}», а техника всех камер соответствует профилю «${observed.profile.name}» (${percent(observed.score)}).`
          : `Техника всех камер соответствует этапу по графику «${planned.name}» (${percent(observed.score)}).`,
      );
    } else if (!planned) parts.push(`На ${numericDate(frame.timestamp)} в графике нет этапа.`);
    const by = (code: string) =>
      analysis.alerts.filter((a) => a.code === code).map((a) => a.message);
    const missing = [...by('required'), ...by('shortage')];
    if (missing.length) parts.push(`Не выполнены требования этапа: ${missing.join('; ')}.`);
    if (by('idle').length) parts.push(`Возможная потеря темпа: ${by('idle').join('; ')}.`);
    if (by('zone').length) parts.push(`Нарушение размещения: ${by('zone').join('; ')}.`);
    if (by('extra').length) parts.push(`Вне профиля планового этапа: ${by('extra').join('; ')}.`);
    const v = site.variance;
    if (v.reason === 'end' && v.overrunDays > 0)
      parts.push(
        `Этап «${v.segment!.profile.name}» идёт минимум на ${days(v.overrunDays)} дольше плана.`,
      );
    if (site.readiness)
      parts.push(
        `Визуальная готовность по проектному виду — ${site.readiness.score}% (уверенность ${site.readiness.confidence}).`,
      );
    if (!analysis.alerts.length) parts.push('Отклонений на этом срезе нет.');
    return parts.join(' ');
  });

  // Readiness is recomputed for the frame on screen once a design view is loaded.
  $effect(() => {
    const view = site.designView;
    const current = frame;
    if (!view || !current) return;
    const profileId = site.acceptedProfile?.id ?? planned?.profileId;
    const index = site.windows.findIndex((w) => w.profileId === profileId);
    const key = `${current.image}|${view.image.length}|${index}`;
    if (site.readiness?.key === key) return;
    assessReadiness(current.image, view.image, index, site.windows.length, current.vlm?.code)
      .then((result) => (site.readiness = result))
      .catch(() => (site.readiness = null));
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
    URL.revokeObjectURL(url);
  }
</script>

{#if frame && analysis}
  <div class="page-heading">
    <div>
      <h1>Контроль площадки</h1>
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
        Подтверждённый этап
        <select
          aria-label="Подтверждённый этап"
          value={site.stageMode === 'auto' ? '__auto__' : site.acceptedProfileId}
          onchange={(e) => {
            const value = e.currentTarget.value;
            site.stageMode = value === '__auto__' ? 'auto' : 'manual';
            if (value !== '__auto__') site.acceptedProfileId = value;
          }}
        >
          <option value="__auto__">Авто · {observed?.profile.name ?? 'нет данных'}</option>
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
      <span class="eyebrow">Наблюдается по камерам</span>
      <b>{observed ? `${observed.profile.name} · ${percent(observed.score)}` : 'Нет техники'}</b>
      <small>
        {site.stageMode === 'manual'
          ? `Принят вручную: ${site.acceptedProfile?.name}`
          : 'Этап принят автоматически'}
      </small>
    </div>
    <button onclick={() => (site.designDialog = true)}>
      <span class="eyebrow">Готовность по проекту</span>
      <b
        >{site.designView
          ? site.readiness
            ? `${site.readiness.score}%`
            : 'Расчёт…'
          : 'Настроить'}</b
      >
      <small
        >{site.designView
          ? `уверенность ${site.readiness?.confidence ?? '—'}`
          : 'Загрузите проектный вид'}</small
      >
    </button>
    <div>
      <span class="eyebrow">Относительно плана</span>
      <b class="tone {variance.tone}">{variance.text}</b>
      <small>{variance.detail}</small>
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
          >{project.provenance.boxes === 'synthetic' ? 'синтетика' : 'архивный кадр'}</span
        >
      </div>
      <div class="panel-body">
        <FrameView
          {frame}
          tones={analysis.boxTones}
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

    <aside class="panel" aria-label="Техника и отклонения">
      <div class="panel-head">
        <div>
          <span class="eyebrow">Анализ площадки</span>
          <h2>Техника и отклонения</h2>
        </div>
        <span
          class="tone {analysis.alerts.some((a) => a.tone === 'red')
            ? 'red'
            : analysis.alerts.length
              ? 'yellow'
              : 'green'}"
        >
          {analysis.alerts.length ? `${analysis.alerts.length} отклон.` : 'норма'}
        </span>
      </div>
      <div class="panel-body">
        {#if conclusion}
          <div class="conclusion">
            <span class="eyebrow">Заключение{frame.vlm ? ' · аналитика + VLM' : ''}</span>
            <p>{conclusion}</p>
            {#if frame.vlm}
              <small>
                Контекст сцены ({frame.vlm.model.split('/').at(-1)}): {frame.vlm.scene}. VLM только
                описывает сцену и не создаёт предупреждений.
              </small>
            {/if}
          </div>
        {/if}

        {#if site.ranked.length}
          <div class="ranking">
            <span class="eyebrow">Этапы по составу техники</span>
            {#each site.ranked.slice(0, 3) as match, i (match.profile.id)}
              <div class="rank" class:top={i === 0}>
                <span>{match.profile.name}</span>
                <i><b style="width:{Math.round(match.score * 100)}%"></b></i>
                <em>{percent(match.score)}</em>
              </div>
            {/each}
          </div>
        {/if}

        <div class="table equipment">
          <div class="row head">
            <span>Техника</span><span>Кадр</span><span>Площадка</span><span>Нужно</span>
          </div>
          {#each analysis.rows as row (row.slug + row.role)}
            {@const Icon = equipmentIcon(row.slug)}
            <div class="row {row.status}">
              <span class="machine">
                <Icon size={18} />
                <span
                  ><b>{row.label}</b><small
                    >{ROLE[row.role]} · {row.cameras.length}
                    {row.cameras.length === 1 ? 'камера' : 'камеры'}</small
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

        <div class="alerts" aria-label="Отклонения на срезе">
          {#each analysis.alerts as alert (alert.code + alert.message)}
            <div class="alert">
              <i class="dot {alert.tone}"></i>
              <span><b>{alert.title}</b><small>{alert.message}</small></span>
              {#if alert.code === 'zone'}<a href="/app/site/zones">Зоны →</a
                >{:else if alert.code === 'stage'}<a href="/app/site/plan">План →</a>{:else}<span
                ></span>{/if}
            </div>
          {:else}
            <div class="quiet-state">
              <b>Отклонений нет</b><span>Требования этапа по графику выполнены на этом срезе.</span>
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
  .ranking {
    display: grid;
    gap: 6px;
  }
  .rank {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 90px 40px;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    color: var(--muted);
  }
  .rank.top {
    color: var(--text);
    font-weight: 700;
  }
  .rank i {
    height: 6px;
    border-radius: 3px;
    background: var(--raised);
    overflow: hidden;
  }
  .rank i b {
    display: block;
    height: 100%;
    background: var(--accent);
  }
  .rank em {
    font-style: normal;
    text-align: right;
  }
  .equipment .row {
    grid-template-columns: minmax(0, 1fr) 48px 70px 70px;
  }
  .equipment .row strong,
  .equipment .row em {
    font-style: normal;
    text-align: center;
  }
  .equipment .row.bad em,
  .equipment .row.bad strong:nth-of-type(2) {
    color: var(--danger);
  }
  .equipment .row.warning strong:nth-of-type(2) {
    color: var(--warning);
  }
  .equipment .row.ok strong:nth-of-type(2) {
    color: var(--accent);
  }
</style>
