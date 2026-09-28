import { getContext, setContext } from 'svelte';
import { alertJournal, analyzeFrame, cameraFrames, rankStages } from './analysis';
import { time } from './format';
import { observedSegments, planWindows, reasonIntervals, scheduleVariance, windowAt } from './plan';
import type { Readiness } from './readiness';
import type {
  Methodology,
  ProjectSummary,
  SitePlan,
  SiteProject,
  StageProfile,
  Zone,
} from './types';

const PREFIX = 'sitewatch.site.v1';
const BASE = '/demo/site';

interface Saved {
  plan?: SitePlan;
  profileOverrides?: Record<string, StageProfile>;
  zones?: Record<string, Zone[]>;
  stageMode?: 'auto' | 'manual';
  acceptedProfileId?: string;
  cameraId?: string;
}

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));

/** State of the site console shared by all `/app/site` pages. */
export class SiteConsole {
  projects = $state<ProjectSummary[]>([]);
  methodology = $state<Methodology | null>(null);
  project = $state<SiteProject | null>(null);
  status = $state<'loading' | 'ready' | 'error'>('loading');
  error = $state('');
  storageFailed = $state(false);

  cameraId = $state('');
  frameId = $state('');
  stageMode = $state<'auto' | 'manual'>('auto');
  acceptedProfileId = $state('');
  plan = $state<SitePlan>({ start: '2024-01-01', stages: [] });
  profileOverrides = $state<Record<string, StageProfile>>({});
  zones = $state<Record<string, Zone[]>>({});
  designView = $state<{ image: string; name: string } | null>(null);
  readiness = $state<Readiness | null>(null);
  visibility = $state<Record<string, number>>({});

  panel = $state<'tasks' | 'journal' | null>(null);
  evidenceFrameId = $state<string | null>(null);
  designDialog = $state(false);

  /* ---------- derived ---------- */

  profiles = $derived<StageProfile[]>(
    (this.methodology?.profiles ?? []).map((p) => this.profileOverrides[p.id] ?? p),
  );
  camera = $derived(this.project?.cameras.find((c) => c.id === this.cameraId) ?? null);
  frames = $derived(this.project && this.cameraId ? cameraFrames(this.project, this.cameraId) : []);
  frame = $derived(this.frames.find((f) => f.id === this.frameId) ?? this.frames.at(-1) ?? null);
  frameIndex = $derived(this.frame ? this.frames.indexOf(this.frame) : -1);
  at = $derived(this.frame ? time(this.frame.timestamp) : 0);
  windows = $derived(planWindows(this.plan));
  plannedWindow = $derived(windowAt(this.windows, this.at));
  plannedProfile = $derived(this.profile(this.plannedWindow?.profileId));
  analysis = $derived(
    this.project && this.frame
      ? analyzeFrame(
          this.project,
          this.frame,
          this.plannedProfile,
          this.profiles,
          this.zones[this.frame.cameraId] ?? [],
        )
      : null,
  );
  ranked = $derived(this.analysis ? rankStages(this.analysis.snapshot.counts, this.profiles) : []);
  acceptedProfile = $derived(
    this.stageMode === 'manual'
      ? this.profile(this.acceptedProfileId)
      : (this.analysis?.observed?.profile ?? null),
  );
  segments = $derived(this.project ? observedSegments(this.project, this.profiles) : []);
  variance = $derived(scheduleVariance(this.windows, this.segments));
  journal = $derived(
    this.project
      ? alertJournal(
          this.project,
          (at) => this.profile(windowAt(this.windows, at)?.profileId),
          this.profiles,
          this.zones,
        )
      : [],
  );
  reasons = $derived(
    reasonIntervals(this.journal, Math.max(3_600_000, (this.project?.shiftHours ?? 12) * 900_000)),
  );
  /** Cameras still waiting for their first forbidden zone, plus the design view. */
  tasks = $derived([
    ...(this.project?.cameras.filter((c) => !this.zones[c.id]?.length) ?? []).map((c) => ({
      kind: 'zone' as const,
      camera: c,
    })),
    ...(this.designView ? [] : [{ kind: 'design' as const, camera: null }]),
  ]);

  profile(id: string | undefined | null) {
    return id ? (this.profiles.find((p) => p.id === id) ?? null) : null;
  }

  /* ---------- loading and persistence ---------- */

  async load(fetcher: typeof fetch, projectId?: string) {
    this.status = 'loading';
    try {
      const get = async <T>(path: string) => {
        const response = await fetcher(`${BASE}/${path}`);
        if (!response.ok) throw new Error(`Не удалось загрузить ${path}: ${response.status}`);
        return (await response.json()) as T;
      };
      if (!this.projects.length) this.projects = await get<ProjectSummary[]>('index.json');
      if (!this.methodology) this.methodology = await get<Methodology>('methodology.json');
      const id = projectId ?? read<string>(`${PREFIX}.project`) ?? this.projects[0]?.id;
      const project = await get<SiteProject>(
        `${(this.projects.find((p) => p.id === id) ?? this.projects[0]).id}.json`,
      );
      this.apply(project);
      write(`${PREFIX}.project`, project.id);
      this.status = 'ready';
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
      this.status = 'error';
    }
  }

  private apply(project: SiteProject) {
    const saved = read<Saved>(`${PREFIX}.${project.id}`) ?? {};
    this.project = project;
    this.plan = saved.plan ?? clone(project.plan);
    this.profileOverrides = saved.profileOverrides ?? {};
    this.zones = saved.zones ?? clone(project.zones);
    this.stageMode = saved.stageMode ?? 'auto';
    this.acceptedProfileId = saved.acceptedProfileId ?? '';
    this.cameraId =
      saved.cameraId && project.cameras.some((c) => c.id === saved.cameraId)
        ? saved.cameraId
        : project.cameras[0].id;
    this.frameId = '';
    this.designView = read(`${PREFIX}.${project.id}.design`);
    this.readiness = null;
    this.visibility = {};
    this.evidenceFrameId = null;
  }

  save() {
    if (!this.project) return;
    const ok = write(`${PREFIX}.${this.project.id}`, {
      plan: $state.snapshot(this.plan),
      profileOverrides: $state.snapshot(this.profileOverrides),
      zones: $state.snapshot(this.zones),
      stageMode: this.stageMode,
      acceptedProfileId: this.acceptedProfileId,
      cameraId: this.cameraId,
    } satisfies Saved);
    this.storageFailed = !ok;
  }

  setDesignView(view: { image: string; name: string } | null) {
    this.designView = view;
    this.readiness = null;
    if (this.project) this.storageFailed = !write(`${PREFIX}.${this.project.id}.design`, view);
  }

  resetProject() {
    if (!this.project) return;
    write(`${PREFIX}.${this.project.id}`, null);
    write(`${PREFIX}.${this.project.id}.design`, null);
    this.apply(this.project);
  }

  /* ---------- navigation ---------- */

  selectCamera(id: string) {
    if (!this.project?.cameras.some((c) => c.id === id)) return;
    this.cameraId = id;
    this.frameId = '';
  }

  selectFrame(id: string) {
    const frame = this.project?.frames.find((f) => f.id === id);
    if (!frame) return;
    this.cameraId = frame.cameraId;
    this.frameId = frame.id;
  }

  step(delta: number) {
    const next =
      this.frames[Math.max(0, Math.min(this.frames.length - 1, this.frameIndex + delta))];
    if (next) this.frameId = next.id;
  }

  /* ---------- report ---------- */

  report() {
    const a = this.analysis;
    if (!this.project || !this.frame || !a) return null;
    return {
      схема: 'sitewatch.site-report.v1',
      проект: {
        id: this.project.id,
        название: this.project.name,
        происхождение_данных: this.project.provenance,
      },
      кадр: { id: this.frame.id, камера: this.camera?.name, время: this.frame.timestamp },
      этап_по_графику: this.plannedWindow
        ? { название: this.plannedWindow.name, профиль: this.plannedProfile?.name }
        : null,
      наблюдаемый_этап: a.observed
        ? { профиль: a.observed.profile.name, совпадение: Math.round(a.observed.score * 100) }
        : null,
      принятый_этап: this.acceptedProfile?.name ?? null,
      режим_этапа: this.stageMode,
      срез_площадки: {
        камеры: a.snapshot.members.map((m) => ({
          камера: m.camera.name,
          кадр: m.frame.id,
          возраст_мин: Math.round(m.ageMs / 60000),
        })),
        техника: a.snapshot.counts,
        источники_по_камерам: a.snapshot.cameraCountsByClass,
        правило_объединения: 'максимум по одной камере (кадры камер разновременные)',
      },
      техника_на_кадре: a.rows,
      отклонения: a.alerts,
      журнал: this.journal.map((e) => ({
        ...e.alert,
        камера: e.cameraId,
        кадры: e.frameIds,
        с: e.start,
        по: e.end,
      })),
      отклонение_от_графика: this.variance,
      зоны: this.zones[this.frame.cameraId] ?? [],
      готовность_по_проектному_виду: this.readiness,
      календарный_план: this.windows.map((w) => ({
        ...w,
        начало: new Date(w.start).toISOString(),
        конец: new Date(w.end).toISOString(),
      })),
    };
  }
}

const KEY = Symbol('site-console');
export const provideSite = (site: SiteConsole) => setContext(KEY, site);
export const useSite = () => getContext<SiteConsole>(KEY);
