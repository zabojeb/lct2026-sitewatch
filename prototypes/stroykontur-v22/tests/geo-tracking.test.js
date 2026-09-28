import '../dist/geo-tracking.js';

const { calibrateCamera, projectPoint, bboxFootpoint, projectDetection, fuseObservations, fuseCameraDetections, MultiCameraTracker } = globalThis.GeoTracking;
const close = (actual, expected, tolerance = 1e-6) => {
  if (Math.abs(actual - expected) > tolerance) throw new Error(`${actual} != ${expected}`);
};

Deno.test('гомография восстанавливает координаты площадки', () => {
  const calibration = calibrateCamera([
    { image: [0, 0], site: [10, 20] }, { image: [1, 0], site: [90, 20] },
    { image: [1, 1], site: [80, 90] }, { image: [0, 1], site: [20, 90] }
  ]);
  const p = projectPoint(calibration.homography, [0, 0]);
  close(p[0], 10); close(p[1], 20); close(calibration.reprojectionRmse, 0);
});

Deno.test('координата техники берётся по нижнему центру bbox', () => {
  const calibration = calibrateCamera([
    { image: [0, 0], site: [0, 0] }, { image: [1, 0], site: [100, 0] },
    { image: [1, 1], site: [100, 100] }, { image: [0, 1], site: [0, 100] }
  ]);
  const detection = { bbox: [.2, .1, .4, .5], className: 'экскаватор', cameraId: '1', confidence: .9 };
  const projected = projectDetection(detection, calibration);
  close(bboxFootpoint(detection.bbox)[0], .2); close(projected.site[0], 20); close(projected.site[1], 35);
});

Deno.test('наблюдения разных камер объединяются, одной камеры — нет', () => {
  const fused = fuseObservations([
    { className: 'буровая', cameraId: '1', confidence: .9, site: [30, 40] },
    { className: 'буровая', cameraId: '2', confidence: .8, site: [32, 41] },
    { className: 'буровая', cameraId: '1', confidence: .7, site: [31, 40] }
  ], { defaultThreshold: 5 });
  if (fused.length !== 2 || fused[0].sourceCount !== 2) throw new Error('Неверное объединение камер');
});

Deno.test('состав площадки объединяется по камерам без двойного счёта', () => {
  const uncalibrated = fuseCameraDetections([
    { camera: 'Камера 1', boxes: [{ classSlug: 'excavator' }, { classSlug: 'excavator' }] },
    { camera: 'Камера 2', boxes: [{ classSlug: 'excavator' }, { classSlug: 'excavator' }, { classSlug: 'excavator' }] }
  ]);
  if (uncalibrated.counts.excavator !== 3 || uncalibrated.modeByClass.excavator !== 'camera-max') throw new Error('Некалиброванные камеры нужно объединять максимумом');

  const calibrated = fuseCameraDetections([
    { camera: 'Камера 1', boxes: [{ classSlug: 'excavator', mapPoint: [10, 10] }] },
    { camera: 'Камера 2', boxes: [{ classSlug: 'excavator', mapPoint: [10.5, 10.2] }] }
  ], { defaultThreshold: 2 });
  if (calibrated.counts.excavator !== 1 || calibrated.modeByClass.excavator !== 'geometry') throw new Error('Калиброванные наблюдения одной машины не объединились');
});

Deno.test('трекер сохраняет id и оценивает движение', () => {
  const tracker = new MultiCameraTracker({ baseGate: 10, maxSpeed: .2 });
  const t0 = Date.parse('2026-09-25T09:00:00Z');
  const first = tracker.update([{ className: 'самосвал', site: [10, 20], confidence: .9, cameraIds: ['1'], sourceCount: 1 }], t0);
  const second = tracker.update([{ className: 'самосвал', site: [16, 20], confidence: .9, cameraIds: ['2'], sourceCount: 1 }], t0 + 60_000);
  if (first[0].id !== second[0].id || second[0].velocity[0] <= 0) throw new Error('Идентичность или скорость трека потеряна');
});
