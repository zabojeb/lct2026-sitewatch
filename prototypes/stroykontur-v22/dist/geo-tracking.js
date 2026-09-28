(function (root) {
  'use strict';

  const EPS = 1e-10;
  const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

  function solveLinear(matrix, vector) {
    const n = vector.length;
    const a = matrix.map((row, i) => [...row, vector[i]]);
    for (let col = 0; col < n; col += 1) {
      let pivot = col;
      for (let row = col + 1; row < n; row += 1) {
        if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row;
      }
      if (Math.abs(a[pivot][col]) < EPS) throw new Error('Калибровочные точки вырождены');
      [a[col], a[pivot]] = [a[pivot], a[col]];
      const scale = a[col][col];
      for (let j = col; j <= n; j += 1) a[col][j] /= scale;
      for (let row = 0; row < n; row += 1) {
        if (row === col) continue;
        const factor = a[row][col];
        for (let j = col; j <= n; j += 1) a[row][j] -= factor * a[col][j];
      }
    }
    return a.map(row => row[n]);
  }

  function leastSquares(rows, values) {
    const cols = rows[0].length;
    const ata = Array.from({ length: cols }, () => Array(cols).fill(0));
    const atb = Array(cols).fill(0);
    rows.forEach((row, i) => {
      for (let c = 0; c < cols; c += 1) {
        atb[c] += row[c] * values[i];
        for (let k = 0; k < cols; k += 1) ata[c][k] += row[c] * row[k];
      }
    });
    return solveLinear(ata, atb);
  }

  function computeHomography(imagePoints, sitePoints) {
    if (imagePoints.length !== sitePoints.length || imagePoints.length < 4) {
      throw new Error('Для калибровки нужны минимум 4 пары точек');
    }
    const rows = [], values = [];
    imagePoints.forEach(([u, v], i) => {
      const [x, y] = sitePoints[i];
      rows.push([u, v, 1, 0, 0, 0, -x * u, -x * v]); values.push(x);
      rows.push([0, 0, 0, u, v, 1, -y * u, -y * v]); values.push(y);
    });
    const h = leastSquares(rows, values);
    return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
  }

  function projectPoint(h, point) {
    const [u, v] = point;
    const z = h[2][0] * u + h[2][1] * v + h[2][2];
    if (Math.abs(z) < EPS) throw new Error('Точка проецируется в бесконечность');
    return [(h[0][0] * u + h[0][1] * v + h[0][2]) / z, (h[1][0] * u + h[1][1] * v + h[1][2]) / z];
  }

  function bboxFootpoint(bbox) {
    const [centerX, centerY, , height] = bbox;
    return [centerX, centerY + height / 2];
  }

  function calibrateCamera(controlPoints) {
    const image = controlPoints.map(p => p.image);
    const site = controlPoints.map(p => p.site);
    const homography = computeHomography(image, site);
    const errors = image.map((p, i) => distance(projectPoint(homography, p), site[i]));
    return {
      homography,
      pointCount: controlPoints.length,
      reprojectionRmse: Math.sqrt(errors.reduce((sum, e) => sum + e * e, 0) / errors.length)
    };
  }

  function projectDetection(detection, calibration) {
    const site = projectPoint(calibration.homography, bboxFootpoint(detection.bbox));
    return { ...detection, site, calibrationRmse: calibration.reprojectionRmse };
  }

  function fuseObservations(observations, options = {}) {
    const thresholdByClass = options.thresholdByClass || {};
    const defaultThreshold = options.defaultThreshold ?? 7;
    const groups = [];
    [...observations].sort((a, b) => (b.confidence || 0) - (a.confidence || 0)).forEach(obs => {
      const threshold = thresholdByClass[obs.className] ?? defaultThreshold;
      let best = null, bestDistance = Infinity;
      groups.forEach(group => {
        if (group.className !== obs.className || group.cameraIds.has(obs.cameraId)) return;
        const d = distance(group.site, obs.site);
        if (d <= threshold && d < bestDistance) { best = group; bestDistance = d; }
      });
      if (!best) {
        groups.push({ className: obs.className, site: [...obs.site], confidence: obs.confidence || 0.5, cameraIds: new Set([obs.cameraId]), observations: [obs], weight: obs.confidence || 0.5 });
        return;
      }
      const weight = obs.confidence || 0.5, total = best.weight + weight;
      best.site = [(best.site[0] * best.weight + obs.site[0] * weight) / total, (best.site[1] * best.weight + obs.site[1] * weight) / total];
      best.weight = total;
      best.confidence = 1 - (1 - best.confidence) * (1 - weight);
      best.cameraIds.add(obs.cameraId); best.observations.push(obs);
    });
    return groups.map(group => ({ ...group, cameraIds: [...group.cameraIds], sourceCount: group.observations.length }));
  }

  function fuseCameraDetections(frames, options = {}) {
    const counts = {}, camerasByClass = {}, modeByClass = {}, cameraCountsByClass = {};
    const classes = new Set();
    frames.forEach(frame => (frame.boxes || []).forEach(box => classes.add(box.classSlug || box.className)));
    classes.forEach(slug => {
      const detections = [];
      const cameraCounts = new Map();
      frames.forEach(frame => {
        const boxes = (frame.boxes || []).filter(box => (box.classSlug || box.className) === slug);
        if (!boxes.length) return;
        cameraCounts.set(frame.camera || frame.cameraId, boxes.length);
        boxes.forEach(box => {
          const site = box.mapPoint || box.site;
          if (Array.isArray(site) && site.length === 2) detections.push({
            className: slug,
            site,
            confidence: box.confidence || 1,
            cameraId: frame.camera || frame.cameraId
          });
        });
      });
      const totalDetections = [...cameraCounts.values()].reduce((sum, value) => sum + value, 0);
      const calibratedCameras = new Set(detections.map(item => item.cameraId));
      if (detections.length === totalDetections && calibratedCameras.size >= 2) {
        counts[slug] = fuseObservations(detections, options).length;
        modeByClass[slug] = 'geometry';
      } else {
        counts[slug] = Math.max(0, ...cameraCounts.values());
        modeByClass[slug] = 'camera-max';
      }
      camerasByClass[slug] = [...cameraCounts.keys()];
      cameraCountsByClass[slug] = Object.fromEntries(cameraCounts);
    });
    return { counts, camerasByClass, cameraCountsByClass, modeByClass, cameraCount: frames.length };
  }

  class MultiCameraTracker {
    constructor(options = {}) {
      this.options = { baseGate: 9, maxSpeed: 0.12, maxMissMs: 30 * 60 * 1000, alpha: 0.68, beta: 0.18, ...options };
      this.tracks = []; this.nextId = 1;
    }

    update(observations, timestamp) {
      const time = typeof timestamp === 'number' ? timestamp : new Date(timestamp).getTime();
      const candidates = [];
      this.tracks.forEach((track, ti) => observations.forEach((obs, oi) => {
        if (track.className !== obs.className) return;
        const dt = Math.max(1, (time - track.lastTimestamp) / 1000);
        const predicted = [track.site[0] + track.velocity[0] * dt, track.site[1] + track.velocity[1] * dt];
        const d = distance(predicted, obs.site), gate = this.options.baseGate + this.options.maxSpeed * dt;
        if (d <= gate) candidates.push({ ti, oi, d, dt, predicted });
      }));
      candidates.sort((a, b) => a.d - b.d);
      const usedTracks = new Set(), usedObs = new Set();
      candidates.forEach(match => {
        if (usedTracks.has(match.ti) || usedObs.has(match.oi)) return;
        const track = this.tracks[match.ti], obs = observations[match.oi];
        const residual = [obs.site[0] - match.predicted[0], obs.site[1] - match.predicted[1]];
        track.site = [match.predicted[0] + this.options.alpha * residual[0], match.predicted[1] + this.options.alpha * residual[1]];
        track.velocity = [track.velocity[0] + this.options.beta * residual[0] / match.dt, track.velocity[1] + this.options.beta * residual[1] / match.dt];
        track.lastTimestamp = time; track.misses = 0; track.confidence = obs.confidence;
        track.cameraIds = obs.cameraIds; track.sourceCount = obs.sourceCount;
        track.history.push({ timestamp: time, site: [...track.site] });
        if (track.history.length > 120) track.history.shift();
        usedTracks.add(match.ti); usedObs.add(match.oi);
      });
      this.tracks.forEach((track, i) => { if (!usedTracks.has(i)) track.misses += 1; });
      observations.forEach((obs, i) => {
        if (usedObs.has(i)) return;
        this.tracks.push({ id: this.nextId++, className: obs.className, site: [...obs.site], velocity: [0, 0], confidence: obs.confidence, cameraIds: obs.cameraIds, sourceCount: obs.sourceCount, firstTimestamp: time, lastTimestamp: time, misses: 0, history: [{ timestamp: time, site: [...obs.site] }] });
      });
      this.tracks = this.tracks.filter(track => time - track.lastTimestamp <= this.options.maxMissMs);
      return this.activeTracks(time);
    }

    activeTracks(timestamp) {
      return this.tracks.filter(track => timestamp - track.lastTimestamp <= this.options.maxMissMs).map(track => ({ ...track, site: [...track.site], velocity: [...track.velocity], cameraIds: [...track.cameraIds], history: track.history.map(x => ({ timestamp: x.timestamp, site: [...x.site] })) }));
    }
  }

  function pointInPolygon(point, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const [xi, yi] = polygon[i], [xj, yj] = polygon[j];
      const intersects = yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi;
      if (intersects) inside = !inside;
    }
    return inside;
  }

  root.GeoTracking = { computeHomography, projectPoint, bboxFootpoint, calibrateCamera, projectDetection, fuseObservations, fuseCameraDetections, MultiCameraTracker, pointInPolygon };
})(globalThis);
