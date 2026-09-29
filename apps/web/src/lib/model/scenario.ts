import type { ModelPrediction } from '$lib/model';

/** Rule classes the deviations service accepts (EquipmentClass in crates/domain). */
export type EquipmentCode =
  | 'dump_truck'
  | 'excavator'
  | 'road_roller'
  | 'loader_crane'
  | 'concrete_mixer'
  | 'bulldozer'
  | 'truck'
  | 'mobile_crane'
  | 'tower_crane'
  | 'piling_rig'
  | 'concrete_pump'
  | 'bucket_loader';

/** A ready plan check attached to a demo scene: stage, zone, camera and sourced rules. */
export interface PlanScenario {
  stage: string;
  zone: string;
  camera: string;
  /** `datetime-local` values, local time. */
  plannedStart: string;
  plannedEnd: string;
  observable: boolean;
  coverage: { percent: number; source: string } | null;
  rules: Array<{
    equipment_class: EquipmentCode;
    expectation: 'required' | 'optional' | 'unexpected';
    min_count: number;
    max_count: number | null;
    min_confidence: number;
    persistence_frames: number;
    source: string;
  }>;
  /** Where frame times come from; goes into every frame of the window. */
  timeSource: string;
}

export interface ScenarioFrame {
  name: string;
  file: File | null;
  prediction: ModelPrediction | null;
  capturedAt?: string;
}

/** Neighbouring frames of a window must be 1–60 minutes apart (deviations service). */
export const MIN_FRAME_GAP_MS = 60_000;
export const MAX_FRAME_GAP_MS = 60 * 60_000;

/**
 * Recognised frames with a capture time, in time order, keeping only those at least a minute
 * after the previous kept frame; the window ends at the first gap over an hour.
 */
export function framesForWindow<T extends ScenarioFrame>(frames: T[], limit = 20) {
  const timed = frames
    .filter((frame) => frame.prediction && frame.file && frame.capturedAt)
    .map((frame) => ({ frame, at: Date.parse(frame.capturedAt!) }))
    .filter(({ at }) => Number.isFinite(at))
    .sort((a, b) => a.at - b.at);
  const kept: T[] = [];
  let tooClose = 0;
  let last = -Infinity;
  for (const { frame, at } of timed) {
    if (kept.length && (kept.length >= limit || at - last > MAX_FRAME_GAP_MS)) break;
    if (at - last < MIN_FRAME_GAP_MS) {
      tooClose++;
      continue;
    }
    kept.push(frame);
    last = at;
  }
  /** `tooClose` — under a minute after the previous kept frame; the rest fell outside the window. */
  return { kept, tooClose, outside: timed.length - kept.length - tooClose };
}
