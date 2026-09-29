import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { alertJournal, analyzeFrame, rankStages, snapshotAt, SITE } from '../src/lib/site/analysis';
import { time } from '../src/lib/site/format';
import { compareStageObservation, observedSegments, planWindows, scheduleVariance, windowAt } from '../src/lib/site/plan';
import type { Methodology, SiteFrame, SiteProject } from '../src/lib/site/types';

const read = <T>(name: string) => JSON.parse(readFileSync(`static/demo/site/${name}`, 'utf8')) as T;
const methodology = read<Methodology>('methodology.json');
const profile = (id: string) => methodology.profiles.find((p) => p.id === id)!;

test('the task example: an excavator alone at a pit stage asks for dump trucks', () => {
  const pit = profile('earth_excavation');
  expect(pit.required).toEqual({ excavator: 1 });
  expect(pit.anyOf).toEqual([['dump-truck', 'loader']]);
  const frame: SiteFrame = {
    id: 'f1',
    cameraId: 'c1',
    timestamp: '2026-09-28T10:00:00',
    image: '',
    preview: null,
    boxes: [
      {
        slug: 'excavator',
        label: 'Экскаватор',
        bbox: [0.5, 0.5, 0.2, 0.2],
        confidence: 1,
        source: 'annotation',
      },
    ],
  };
  const project: SiteProject = {
    id: 'p',
    name: 'p',
    subtitle: '',
    kind: 'dataset',
    provenance: { boxes: 'annotation', text: '', sources: [] },
    shiftHours: 12,
    cameras: [
      { id: 'c1', name: 'Камера 1', rules: { checkExtra: true, checkZones: true, trackIdle: [] } },
    ],
    frames: [frame],
    plan: { start: '2026-09-01', stages: [] },
    zones: {},
    geometry: null,
  };
  const analysis = analyzeFrame(project, frame, pit, methodology.profiles, []);
  const missing = analysis.alerts.find((a) => a.code === 'required');
  expect(missing?.message).toBe('Нужна хотя бы одна: Самосвал, Погрузчик');
  expect(missing?.tone).toBe('red');
  // with a dump truck the same frame reads as excavation, not as debris loading
  frame.boxes.push({
    slug: 'dump-truck',
    label: 'Самосвал',
    bbox: [0.2, 0.6, 0.2, 0.2],
    confidence: 1,
    source: 'annotation',
  });
  expect(
    rankStages(snapshotAt(project, time(frame.timestamp)).counts, methodology.profiles)[0].profile
      .id,
  ).toBe('earth_excavation');
  expect(analyzeFrame(project, frame, pit, methodology.profiles, []).alerts).toEqual([]);
});

test('a multi-camera site keeps real capture times and fuses cameras by day', () => {
  const site = read<SiteProject>('site-8.json');
  const cams = new Set(site.frames.map((f) => f.timestamp.slice(11, 13)));
  expect(cams.size).toBeGreaterThan(3); // cameras shot at different hours, nothing was re-timed
  const first = snapshotAt(site, time('2024-07-25T16:45:21'));
  expect(first.members.map((m) => m.camera.id)).toEqual(['cam-4']);
  const last = snapshotAt(site, time('2024-07-25T21:47:19'));
  expect(last.members).toHaveLength(5);
  // one machine seen by two cameras is not counted twice
  expect(last.counts.excavator).toBe(
    Math.max(...Object.values(last.cameraCountsByClass.excavator)),
  );
  const segments = observedSegments(site, methodology.profiles);
  expect(segments).toHaveLength(1);
  expect(segments[0].profile.id).toBe('bored_piles');
});

test('the schedule variance never invents a start delay it did not observe', () => {
  const site = read<SiteProject>('site-8.json');
  const variance = scheduleVariance(
    planWindows(site.plan),
    observedSegments(site, methodology.profiles),
  );
  expect(variance.startShiftDays).toBeNull();
  expect(variance.reason).toBe('end');
  expect(variance.overrunDays).toBeGreaterThan(0);

  const scenario = read<SiteProject>('scenario.json');
  const segments = observedSegments(scenario, methodology.profiles);
  expect(segments.map((s) => s.profile.id)).toEqual(['earth_excavation', 'bored_piles']);
  const late = scheduleVariance(planWindows(scenario.plan), segments);
  expect(late.startShiftDays).toBeGreaterThan(0);
  expect(late.days).toBeGreaterThan(0);
});

test('plan windows follow calendar days across a daylight-saving switch', () => {
  const windows = planWindows({
    start: '2020-10-12',
    stages: [{ id: 'a', name: 'a', days: 28, profileId: 'bored_piles' }],
  });
  expect(new Date(windows[0].end).getDate()).toBe(9);
  expect(new Date(windows[0].end).getHours()).toBe(0);
});

test('demo milestone compares explicit dates and updates when the plan changes', () => {
  const delayed = read<SiteProject>('scenario.json');
  const early = read<SiteProject>('scenario-ahead.json');
  const milestone = delayed.stageObservations![0];
  expect(compareStageObservation(planWindows(delayed.plan), milestone)?.days).toBe(13);
  expect(compareStageObservation(planWindows(early.plan), milestone)?.days).toBe(-14);
  delayed.plan.stages[0].days = 34;
  expect(compareStageObservation(planWindows(delayed.plan), milestone)?.days).toBe(0);
  expect(compareStageObservation([], milestone)).toBeNull();
});

test('the journal merges repeats and separates site findings from camera findings', () => {
  const site = read<SiteProject>('site-8.json');
  const windows = planWindows(site.plan);
  const journal = alertJournal(
    site,
    (at) => profile(windowAt(windows, at)?.profileId ?? 'needs_review'),
    methodology.profiles,
    site.zones,
  );
  const extra = journal.filter((e) => e.alert.code === 'extra');
  expect(extra).toHaveLength(1);
  expect(extra[0].cameraId).toBe(SITE);
  const zone = journal.find((e) => e.alert.code === 'zone');
  expect(zone?.cameraId).toBe('cam-9');
  const idle = journal.find((e) => e.alert.code === 'idle');
  expect(idle?.cameraId).toBe('cam-8');
  expect(idle?.alert.durationMs).toBeGreaterThanOrEqual(2 * 60_000);
});
