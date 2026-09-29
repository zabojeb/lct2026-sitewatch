/** Data model of the site console (`/app/site`).
 *
 * A project is a set of camera frames with detections. Every box carries its provenance
 * (`annotation` — reference labels of a public dataset, `model` — our detector, `synthetic` —
 * machinery composited onto a real background), and frame timestamps are the real capture times.
 */

export type BoxSource = 'annotation' | 'model' | 'synthetic';

/** Normalised centre-format box: [cx, cy, w, h] in 0..1 of the frame. */
export type Bbox = [number, number, number, number];

export interface SiteBox {
  slug: string;
  label: string;
  bbox: Bbox;
  confidence: number;
  source: BoxSource;
}

export interface SiteFrame {
  id: string;
  cameraId: string;
  timestamp: string;
  image: string;
  preview: string | null;
  boxes: SiteBox[];
  vlm?: { model: string; code: string; scene: string };
}

export interface CameraRules {
  checkExtra: boolean;
  checkZones: boolean;
  /** Classes whose standstill is tracked on this camera. */
  trackIdle: string[];
}

export interface SiteCamera {
  id: string;
  name: string;
  rules: CameraRules;
}

export interface PlanStage {
  id: string;
  /** Stage name as in the works list (XLSX row name or an operator's own title). */
  name: string;
  days: number;
  profileId: string;
  /** Source row of the organisers' works list, if the stage came from it. */
  row?: number;
}

export interface SitePlan {
  start: string;
  stages: PlanStage[];
  example?: boolean;
}

/** Explicitly assigned milestone for a demo scenario, not inferred from equipment. */
export interface StageObservation {
  stageId: string;
  at: string;
  frameId: string;
  note: string;
  source: 'scripted-demo';
}

/** Polygon in percent of the camera frame (0..100). */
export type Point = [number, number];

export interface Zone {
  id: string;
  name: string;
  equipment: string[];
  points: Point[];
  example?: boolean;
}

export interface GeometryStat {
  cameraId?: string;
  from?: string;
  to?: string;
  kind?: 'epipolar' | 'homography';
  keypoints: number[];
  matches: number;
  inliers: number;
  inlierRatio: number;
  rmse: number | null;
  spanSec?: number;
  matrix?: number[][];
}

export interface SiteProject {
  id: string;
  name: string;
  subtitle: string;
  kind: 'dataset' | 'synthetic' | 'live';
  provenance: { boxes: BoxSource; text: string; sources: { name: string; url: string }[] };
  /** Fusion window: the latest frame of each camera within this many hours counts as "now". */
  shiftHours: number;
  cameras: SiteCamera[];
  frames: SiteFrame[];
  plan: SitePlan;
  stageObservations?: StageObservation[];
  zones: Record<string, Zone[]>;
  geometry: { note: string; cameras: GeometryStat[]; pairs: GeometryStat[] } | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  subtitle: string;
  kind: SiteProject['kind'];
  frames: number;
  cameras: number;
}

/** Equipment profile of a work stage: what must, may and should not be seen. */
export interface StageProfile {
  id: string;
  name: string;
  /** Class → minimum count within the observation window. */
  required: Record<string, number>;
  /** Each group needs at least one of its classes. */
  anyOf: string[][];
  /** Allowed, strengthens the match; absence is not a deviation. */
  optional: string[];
  /** GESN tables the profile generalises. */
  gesn: string[];
  note: string;
  windowMinutes: number;
  sourceRefs: string[];
}

/** A row of the organisers' works list mapped to a profile. */
export interface WorksRow {
  row: number;
  code: string;
  name: string;
  l1: string;
  l2: string;
  profileId: string;
  confidence: string;
}

export interface Methodology {
  method: string;
  sources: Record<string, { title: string; authority: string; url: string }>;
  profiles: StageProfile[];
  stages: WorksRow[];
}
