import { rankStages, snapshotAt, type JournalEntry } from './analysis';
import { DAY, time } from './format';
import type { PlanStage, SitePlan, SiteProject, StageObservation, StageProfile } from './types';

export interface PlanWindow extends PlanStage {
  index: number;
  start: number;
  end: number;
}

/** Adds calendar days, so a daylight-saving switch does not shift the boundary by an hour. */
const addDays = (at: number, n: number) => {
  const date = new Date(at);
  date.setDate(date.getDate() + n);
  return date.getTime();
};

/** Consecutive stages from the plan start date. */
export function planWindows(plan: SitePlan): PlanWindow[] {
  let cursor = time(`${plan.start}T00:00:00`);
  return plan.stages.map((stage, index) => {
    const start = cursor;
    cursor = addDays(start, stage.days);
    return { ...stage, index, start, end: cursor };
  });
}

export const windowAt = (windows: PlanWindow[], at: number) =>
  windows.find((w) => at >= w.start && at < w.end) ?? null;

/** Calendar-day difference between a plan start and an explicitly supplied milestone. */
export function compareStageObservation(windows: PlanWindow[], observation: StageObservation) {
  const stage = windows.find((window) => window.id === observation.stageId);
  if (!stage) return null;
  const calendarDay = (date: string) => Date.parse(`${date.slice(0, 10)}T00:00:00Z`);
  const start = new Date(stage.start);
  const planDate = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
  const days = Math.round((calendarDay(observation.at) - calendarDay(planDate)) / DAY);
  if (!Number.isFinite(days)) return null;
  return { stage, observation, days, status: days > 0 ? 'late' : days < 0 ? 'ahead' : 'on_time' } as const;
}

export interface ObservedSegment {
  profile: StageProfile;
  start: number;
  end: number;
  frameIds: string[];
  score: number;
}

/** Stage of each observed day: the whole-site snapshot at that day's last frame, so every camera
 * that shot during the day contributes. Cameras rarely shoot at the same time, and judging the
 * stage frame by frame would invent "transitions" that only reflect which camera shot next.
 * Consecutive days with the same stage merge into one segment lasting until the next begins. */
export function observedSegments(
  project: SiteProject,
  profiles: StageProfile[],
): ObservedSegment[] {
  const byDay = new Map<string, typeof project.frames>();
  for (const frame of [...project.frames].sort((a, b) => time(a.timestamp) - time(b.timestamp))) {
    const day = frame.timestamp.slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day)!.push(frame);
  }
  const segments: ObservedSegment[] = [];
  const scores: number[][] = [];
  for (const dayFrames of byDay.values()) {
    const first = time(dayFrames[0].timestamp);
    const last = time(dayFrames.at(-1)!.timestamp);
    const best = rankStages(snapshotAt(project, last).counts, profiles)[0];
    if (!best || best.score <= 0) continue;
    const previous = segments.at(-1);
    if (previous && previous.profile.id === best.profile.id) {
      previous.end = last;
      previous.frameIds.push(...dayFrames.map((f) => f.id));
      scores.at(-1)!.push(best.score);
    } else {
      segments.push({
        profile: best.profile,
        start: first,
        end: last,
        frameIds: dayFrames.map((f) => f.id),
        score: best.score,
      });
      scores.push([best.score]);
    }
  }
  segments.forEach((segment, i) => {
    segment.score = scores[i].reduce((a, b) => a + b, 0) / scores[i].length;
    if (i < segments.length - 1) segment.end = segments[i + 1].start;
  });
  return segments;
}

export interface ScheduleVariance {
  segment: ObservedSegment | null;
  /** Planned span of all stages with the observed profile. */
  planned: { start: number; end: number; names: string[] } | null;
  /** Positive: started later than planned, negative: earlier; null when the cameras did not
   * see the stage begin (it was already under way at the first observation). */
  startShiftDays: number | null;
  /** Positive: still going after the planned end — a lower bound, work may go on after the
   * last frame. */
  overrunDays: number;
  /** Headline number: delay > 0, lead < 0, 0 on schedule. */
  days: number;
  reason: 'start' | 'end' | 'lead' | 'none' | 'unplanned';
}

/** Compares the latest observed stage with where the plan puts the same kind of work. */
export function scheduleVariance(
  windows: PlanWindow[],
  segments: ObservedSegment[],
): ScheduleVariance {
  const segment = segments.at(-1) ?? null;
  const empty = { segment, planned: null, startShiftDays: null, overrunDays: 0, days: 0 };
  if (!segment) return { ...empty, reason: 'none' };
  const same = windows.filter((w) => w.profileId === segment.profile.id);
  if (!same.length) return { ...empty, reason: 'unplanned' };
  const planned = { start: same[0].start, end: same.at(-1)!.end, names: same.map((w) => w.name) };
  const startSeen = segments.length > 1;
  const startShiftDays = startSeen ? Math.round((segment.start - planned.start) / DAY) : null;
  const overrunDays = Math.round((segment.end - planned.end) / DAY);
  const delay = Math.max(0, startShiftDays ?? 0, overrunDays);
  const base = { segment, planned, startShiftDays, overrunDays };
  if (delay > 0)
    return { ...base, days: delay, reason: overrunDays >= (startShiftDays ?? 0) ? 'end' : 'start' };
  if (startShiftDays !== null && startShiftDays < 0)
    return { ...base, days: startShiftDays, reason: 'lead' };
  return { ...base, days: 0, reason: 'none' };
}

export const REASON_BANDS = [
  { codes: ['required', 'shortage'], label: 'Нет или не хватает техники', tone: 'red' },
  { codes: ['stage'], label: 'Другой этап по камерам', tone: 'yellow' },
  { codes: ['idle'], label: 'Простой', tone: 'yellow' },
  { codes: ['zone'], label: 'Запретная зона', tone: 'yellow' },
  { codes: ['extra'], label: 'Техника вне профиля', tone: 'yellow' },
] as const;

export interface ReasonInterval {
  start: number;
  end: number;
  entries: JournalEntry[];
}

/** Journal entries of each band merged into intervals on the time axis. */
export function reasonIntervals(journal: JournalEntry[], mergeGapMs: number) {
  return REASON_BANDS.map((band) => {
    const entries = journal
      .filter((e) => (band.codes as readonly string[]).includes(e.alert.code))
      .sort((a, b) => a.start - b.start);
    const intervals: ReasonInterval[] = [];
    for (const entry of entries) {
      const last = intervals.at(-1);
      if (last && entry.start - last.end <= mergeGapMs) {
        last.end = Math.max(last.end, entry.end);
        last.entries.push(entry);
      } else intervals.push({ start: entry.start, end: entry.end, entries: [entry] });
    }
    return { ...band, intervals };
  });
}
