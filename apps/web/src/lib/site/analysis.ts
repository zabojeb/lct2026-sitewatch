import { equipmentName, isEquipment, isMachine } from './catalog';
import { MINUTE, time } from './format';
import { zoneFor } from './zones';
import type { SiteBox, SiteCamera, SiteFrame, SiteProject, StageProfile, Zone } from './types';

/* ---------- multi-camera snapshot ---------- */

export interface SnapshotMember {
  camera: SiteCamera;
  frame: SiteFrame;
  ageMs: number;
}

export interface Snapshot {
  at: number;
  members: SnapshotMember[];
  /** Site-level count per class. */
  counts: Record<string, number>;
  camerasByClass: Record<string, string[]>;
  cameraCountsByClass: Record<string, Record<string, number>>;
}

export function cameraFrames(project: SiteProject, cameraId: string) {
  return project.frames
    .filter((frame) => frame.cameraId === cameraId)
    .sort((a, b) => time(a.timestamp) - time(b.timestamp));
}

export const classCounts = (boxes: SiteBox[]) =>
  boxes.reduce<Record<string, number>>((acc, box) => {
    if (isMachine(box.slug)) acc[box.slug] = (acc[box.slug] ?? 0) + 1;
    return acc;
  }, {});

/** What the site looks like at `at`: the latest frame of every camera within the fusion window.
 *
 * Cameras of a real site rarely shoot at the same second, so boxes are not matched between
 * views. A class is counted as the maximum seen by a single camera — a conservative lower
 * bound: one machine seen from two sides is not counted twice. */
export function snapshotAt(project: SiteProject, at: number): Snapshot {
  const windowMs = project.shiftHours * 3_600_000;
  const members: SnapshotMember[] = [];
  for (const camera of project.cameras) {
    const latest = cameraFrames(project, camera.id)
      .filter((frame) => time(frame.timestamp) <= at && at - time(frame.timestamp) <= windowMs)
      .at(-1);
    if (latest) members.push({ camera, frame: latest, ageMs: at - time(latest.timestamp) });
  }
  const counts: Record<string, number> = {};
  const camerasByClass: Record<string, string[]> = {};
  const cameraCountsByClass: Record<string, Record<string, number>> = {};
  for (const { camera, frame } of members) {
    for (const [slug, n] of Object.entries(classCounts(frame.boxes))) {
      counts[slug] = Math.max(counts[slug] ?? 0, n);
      (camerasByClass[slug] ??= []).push(camera.id);
      (cameraCountsByClass[slug] ??= {})[camera.id] = n;
    }
  }
  return { at, members, counts, camerasByClass, cameraCountsByClass };
}

/* ---------- stage profiles ---------- */

/** Profiles that can actually be confirmed by cameras: they demand some equipment. */
export const isControllable = (profile: StageProfile) =>
  Object.keys(profile.required).length > 0 || profile.anyOf.length > 0;

export const profileClasses = (profile: StageProfile) =>
  new Set([...Object.keys(profile.required), ...profile.anyOf.flat(), ...profile.optional]);

/** How well the observed equipment matches a stage profile, 0..1.
 *
 * Coverage of the demands (each required class up to its minimum, each "one of" group as a
 * whole) dominates. Next comes how much of the observed machinery the demands themselves
 * explain — so that "excavator + dump truck" reads as excavation (both demanded) rather than
 * debris loading (dump truck merely allowed). Allowed equipment adds a little; machinery the
 * profile does not expect is penalised, so one specific machine cannot outweigh the rest of
 * the site. Class shares are counted per class, not per machine. Profiles without demands
 * cannot be confirmed by cameras and are capped below confirmable ones. */
export function stageScore(counts: Record<string, number>, profile: StageProfile) {
  const observed = Object.entries(counts).filter(([slug, n]) => n > 0 && isEquipment(slug));
  if (!observed.length) return 0;
  const expected = profileClasses(profile);
  const demanded = new Set([...Object.keys(profile.required), ...profile.anyOf.flat()]);
  const total = observed.reduce((sum, [, n]) => sum + n, 0);
  const unexpected =
    observed.filter(([slug]) => !expected.has(slug)).reduce((sum, [, n]) => sum + n, 0) / total;
  const precision = observed.filter(([slug]) => expected.has(slug)).length / observed.length;
  const explained = observed.filter(([slug]) => demanded.has(slug)).length / observed.length;
  const optional = profile.optional.length
    ? profile.optional.filter((slug) => (counts[slug] ?? 0) > 0).length / profile.optional.length
    : 0;
  const demands = [
    ...Object.entries(profile.required).map(([slug, need]) =>
      Math.min(1, (counts[slug] ?? 0) / Math.max(1, need)),
    ),
    ...profile.anyOf.map((group) => (group.some((slug) => (counts[slug] ?? 0) > 0) ? 1 : 0)),
  ];
  if (!demands.length)
    return Math.max(0, Math.min(0.35, 0.25 * optional + 0.1 * precision - 0.45 * unexpected));
  const coverage = demands.reduce((a, b) => a + b, 0) / demands.length;
  // a named required class is a stronger demand than a "one of" group
  const specificity = Math.min(
    1,
    (2 * Object.keys(profile.required).length + profile.anyOf.length) / 3,
  );
  return Math.max(
    0,
    Math.min(
      1,
      0.6 * coverage +
        0.15 * explained +
        0.08 * optional +
        0.07 * precision -
        0.35 * unexpected +
        0.05 * specificity * coverage,
    ),
  );
}

export interface StageMatch {
  profile: StageProfile;
  score: number;
}

export function rankStages(counts: Record<string, number>, profiles: StageProfile[]): StageMatch[] {
  return profiles
    .filter((p) => p.id !== 'needs_review' && p.id !== 'no_camera_equipment')
    .map((profile) => ({ profile, score: stageScore(counts, profile) }))
    .sort((a, b) => b.score - a.score);
}

/* ---------- standstill ---------- */

const shift = (a: SiteBox, b: SiteBox) => Math.hypot(a.bbox[0] - b.bbox[0], a.bbox[1] - b.bbox[1]);

/** How long the machine has not moved: walk back through this camera's earlier frames while
 * the nearest box of the same class stays within `maxShift` of the frame size. Real capture
 * times are used, and a gap longer than `maxGapMs` breaks the evidence. */
export function standstillMs(
  project: SiteProject,
  frame: SiteFrame,
  box: SiteBox,
  { maxShift = 0.018, maxGapMs = 10 * MINUTE } = {},
) {
  const earlier = cameraFrames(project, frame.cameraId).filter(
    (f) => time(f.timestamp) < time(frame.timestamp),
  );
  let since = time(frame.timestamp);
  for (const previous of earlier.reverse()) {
    if (since - time(previous.timestamp) > maxGapMs) break;
    const match = previous.boxes
      .filter((b) => b.slug === box.slug)
      .sort((a, b) => shift(a, box) - shift(b, box))[0];
    if (!match || shift(match, box) >= maxShift) break;
    since = time(previous.timestamp);
  }
  return time(frame.timestamp) - since;
}

/* ---------- analysis of the selected frame ---------- */

export type AlertCode = 'required' | 'shortage' | 'extra' | 'zone' | 'idle' | 'stage';
export type Tone = 'red' | 'yellow' | 'green' | 'neutral';

export interface Alert {
  code: AlertCode;
  tone: Exclude<Tone, 'green'>;
  title: string;
  message: string;
  slug?: string;
  slugs?: string[];
  zoneId?: string;
  durationMs?: number;
  boxes: number[];
}

export interface EquipmentRow {
  slug: string;
  label: string;
  role: 'required' | 'any' | 'optional' | 'outside';
  need: string | null;
  frame: number;
  site: number;
  cameras: string[];
  status: 'ok' | 'bad' | 'warning' | 'neutral';
}

export interface FrameAnalysis {
  snapshot: Snapshot;
  observed: StageMatch | null;
  alerts: Alert[];
  boxTones: { tone: Tone; messages: string[] }[];
  rows: EquipmentRow[];
}

export const IDLE_MIN_MS = 2 * MINUTE;

export function analyzeFrame(
  project: SiteProject,
  frame: SiteFrame,
  planned: StageProfile | null,
  profiles: StageProfile[],
  zones: Zone[],
): FrameAnalysis {
  const snapshot = snapshotAt(project, time(frame.timestamp));
  const camera = project.cameras.find((c) => c.id === frame.cameraId);
  const rules = camera?.rules ?? { checkExtra: true, checkZones: true, trackIdle: [] };
  const counts = snapshot.counts;
  const frameCounts = classCounts(frame.boxes);
  const alerts: Alert[] = [];
  const boxTones = frame.boxes.map(() => ({ tone: 'green' as Tone, messages: [] as string[] }));
  const indexesOf = (slug: string) =>
    frame.boxes.flatMap((box, index) => (box.slug === slug ? [index] : []));
  const mark = (indexes: number[], tone: Exclude<Tone, 'green'>, message: string) => {
    for (const index of indexes) {
      const target = boxTones[index];
      if (tone === 'red' || target.tone === 'green') target.tone = tone;
      target.messages.push(message);
    }
  };
  const ranked = rankStages(counts, profiles);
  const observed = ranked[0] && ranked[0].score > 0 ? ranked[0] : null;

  if (planned) {
    for (const [slug, need] of Object.entries(planned.required)) {
      const actual = counts[slug] ?? 0;
      if (actual >= need) continue;
      const code = actual === 0 ? 'required' : 'shortage';
      const title = actual === 0 ? 'Нет обязательной техники' : 'Недобор техники';
      const message = `${equipmentName(slug)}: ${actual} из ${need}`;
      alerts.push({ code, tone: 'red', title, message, slug, boxes: indexesOf(slug) });
      mark(indexesOf(slug), 'red', `${title} · ${message}`);
    }
    for (const group of planned.anyOf) {
      if (group.some((slug) => (counts[slug] ?? 0) > 0)) continue;
      alerts.push({
        code: 'required',
        tone: 'red',
        title: 'Нет обязательной техники',
        message: `Нужна хотя бы одна: ${group.map(equipmentName).join(', ')}`,
        boxes: [],
      });
    }
    if (rules.checkExtra) {
      const allowed = profileClasses(planned);
      const extra = Object.keys(counts).filter((slug) => isEquipment(slug) && !allowed.has(slug));
      if (extra.length) {
        const boxes = extra.flatMap(indexesOf);
        alerts.push({
          code: 'extra',
          tone: 'yellow',
          title: 'Техника вне профиля этапа',
          message: extra.map((slug) => `${equipmentName(slug)} ×${counts[slug]}`).join(', '),
          slugs: extra,
          boxes,
        });
        for (const slug of extra)
          mark(indexesOf(slug), 'yellow', `Вне профиля этапа «${planned.name}»`);
      }
    }
    if (observed && isControllable(planned) && observed.profile.id !== planned.id) {
      alerts.push({
        code: 'stage',
        tone: 'yellow',
        title: 'Наблюдается другой этап',
        message: `По камерам: ${observed.profile.name}; по графику: ${planned.name}`,
        boxes: [],
      });
    }
  }

  if (rules.checkZones) {
    frame.boxes.forEach((box, index) => {
      if (!isMachine(box.slug)) return;
      const zone = zoneFor(box, zones);
      if (!zone) return;
      alerts.push({
        code: 'zone',
        tone: 'yellow',
        title: 'Въезд в запретную зону',
        message: `${equipmentName(box.slug)} · ${zone.name}`,
        slug: box.slug,
        zoneId: zone.id,
        boxes: [index],
      });
      mark([index], 'yellow', `Запретная зона · ${zone.name}`);
    });
  }

  for (const slug of rules.trackIdle) {
    const still = frame.boxes
      .map((box, index) => ({
        index,
        ms: box.slug === slug ? standstillMs(project, frame, box) : 0,
      }))
      .filter((item) => item.ms >= IDLE_MIN_MS);
    if (!still.length) continue;
    const longest = Math.max(...still.map((item) => item.ms));
    const minutes = Math.round(longest / MINUTE);
    const count = still.length > 1 ? ` ×${still.length}` : '';
    alerts.push({
      code: 'idle',
      tone: 'yellow',
      title: 'Вероятный простой',
      message: `${equipmentName(slug)}${count}: рамка не смещается ${minutes} мин`,
      slug,
      durationMs: longest,
      boxes: still.map((item) => item.index),
    });
    mark(
      still.map((item) => item.index),
      'yellow',
      `Вероятный простой · ${minutes} мин`,
    );
  }

  return {
    snapshot,
    observed,
    alerts,
    boxTones,
    rows: equipmentRows(planned, snapshot, frameCounts, rules.checkExtra),
  };
}

function equipmentRows(
  planned: StageProfile | null,
  snapshot: Snapshot,
  frameCounts: Record<string, number>,
  checkExtra: boolean,
): EquipmentRow[] {
  const counts = snapshot.counts;
  const row = (
    slug: string,
    role: EquipmentRow['role'],
    need: string | null,
    status: EquipmentRow['status'],
  ) => ({
    slug,
    label: equipmentName(slug),
    role,
    need,
    frame: frameCounts[slug] ?? 0,
    site: counts[slug] ?? 0,
    cameras: snapshot.camerasByClass[slug] ?? [],
    status,
  });
  const rows: EquipmentRow[] = [];
  const allowed = planned ? profileClasses(planned) : new Set<string>();
  if (planned) {
    for (const [slug, need] of Object.entries(planned.required))
      rows.push(row(slug, 'required', String(need), (counts[slug] ?? 0) >= need ? 'ok' : 'bad'));
    for (const group of planned.anyOf) {
      const ok = group.some((slug) => (counts[slug] ?? 0) > 0);
      for (const slug of group) rows.push(row(slug, 'any', '≥1', ok ? 'ok' : 'bad'));
    }
    for (const slug of planned.optional)
      if (counts[slug]) rows.push(row(slug, 'optional', null, 'ok'));
  }
  for (const slug of Object.keys(counts).filter((s) => isEquipment(s) && !allowed.has(s)))
    rows.push(row(slug, 'outside', null, checkExtra && planned ? 'warning' : 'neutral'));
  return rows;
}

/* ---------- project-wide alert journal ---------- */

/** Findings about the whole site rather than one view. */
export const SITE = 'site';
const SITE_LEVEL = new Set<AlertCode>(['required', 'shortage', 'extra', 'stage']);

/** One journal entry per kind of finding: off-profile machinery of the site, a stage pair,
 * a missing class, a zone intrusion or a standstill of a class on one camera. */
function journalKey(scope: string, alert: Alert) {
  switch (alert.code) {
    case 'extra':
      return `${scope}|extra`;
    case 'stage':
      return `${scope}|stage|${alert.message}`;
    case 'zone':
      return `${scope}|zone|${alert.zoneId}|${alert.slug}`;
    default:
      return `${scope}|${alert.code}|${alert.slug ?? alert.message}`;
  }
}

export interface JournalEntry {
  key: string;
  alert: Alert;
  cameraId: string;
  frameIds: string[];
  start: number;
  end: number;
}

/** Runs the frame analysis over every frame and merges repeats of the same finding on the same
 * camera into one entry spanning its first and last evidence frame. */
export function alertJournal(
  project: SiteProject,
  plannedAt: (at: number) => StageProfile | null,
  profiles: StageProfile[],
  zonesByCamera: Record<string, Zone[]>,
): JournalEntry[] {
  const open = new Map<string, JournalEntry>();
  const out: JournalEntry[] = [];
  const frames = [...project.frames].sort((a, b) => time(a.timestamp) - time(b.timestamp));
  for (const frame of frames) {
    const at = time(frame.timestamp);
    const analysis = analyzeFrame(
      project,
      frame,
      plannedAt(at),
      profiles,
      zonesByCamera[frame.cameraId] ?? [],
    );
    for (const alert of analysis.alerts) {
      const scope = SITE_LEVEL.has(alert.code) ? SITE : frame.cameraId;
      const key = journalKey(scope, alert);
      const entry = open.get(key);
      if (entry && entry.frameIds.length && at - entry.end <= project.shiftHours * 3_600_000) {
        entry.end = at;
        entry.frameIds.push(frame.id);
        // keep the widest finding: a site's list of off-profile classes grows as cameras report
        if ((alert.slugs?.length ?? 0) >= (entry.alert.slugs?.length ?? 0)) entry.alert = alert;
      } else {
        const created = { key, alert, cameraId: scope, frameIds: [frame.id], start: at, end: at };
        open.set(key, created);
        out.push(created);
      }
    }
  }
  return out.sort((a, b) => b.end - a.end);
}
