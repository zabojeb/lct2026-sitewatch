import { loadImage } from './zones';

/** 8×5 grid of mean brightness and edge density of a downscaled image. */
function descriptor(image: HTMLImageElement) {
  const width = 144;
  const height = 81;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return [];
  context.drawImage(image, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height).data;
  const gray = new Float32Array(width * height);
  for (let i = 0; i < gray.length; i++)
    gray[i] = 0.299 * pixels[i * 4] + 0.587 * pixels[i * 4 + 1] + 0.114 * pixels[i * 4 + 2];
  const cols = 8;
  const rows = 5;
  const cells: [number, number][] = [];
  for (let gy = 0; gy < rows; gy++)
    for (let gx = 0; gx < cols; gx++) {
      let light = 0;
      let edge = 0;
      let count = 0;
      for (
        let y = Math.floor((gy * height) / rows);
        y < Math.floor(((gy + 1) * height) / rows);
        y += 2
      )
        for (
          let x = Math.floor((gx * width) / cols);
          x < Math.floor(((gx + 1) * width) / cols);
          x += 2
        ) {
          const at = y * width + x;
          light += gray[at] / 255;
          if (x + 1 < width && y + 1 < height)
            edge += Math.min(
              1,
              (Math.abs(gray[at] - gray[at + 1]) + Math.abs(gray[at] - gray[at + width])) / 90,
            );
          count++;
        }
      cells.push([light / count, edge / count]);
    }
  return cells;
}

function similarity(a: [number, number][], b: [number, number][]) {
  const n = Math.min(a.length, b.length);
  if (!n) return 0;
  let difference = 0;
  for (let i = 0; i < n; i++)
    difference += 0.35 * Math.abs(a[i][0] - b[i][0]) + 0.65 * Math.abs(a[i][1] - b[i][1]);
  return Math.max(0, Math.min(1, 1 - difference / n));
}

export interface Readiness {
  key: string;
  score: number;
  similarity: number;
  confidence: 'высокая' | 'средняя' | 'низкая';
  stagePosition: number;
}

/** Preliminary visual readiness against an uploaded design view of the finished building.
 *
 * 55% structural similarity of the current frame to the design view, 30% position of the
 * accepted stage in the plan, 15% scene context. This is an indication for the operator, not
 * an acceptance of volumes: that needs BIM elements and element-wise comparison. */
export async function assessReadiness(
  frameImage: string,
  designView: string,
  stageIndex: number,
  stageCount: number,
  sceneCode: string | undefined,
): Promise<Readiness> {
  const [current, target] = await Promise.all([loadImage(frameImage), loadImage(designView)]);
  const sim = similarity(descriptor(current), descriptor(target));
  const stagePosition = Math.max(
    0.05,
    Math.min(0.95, (Math.max(0, stageIndex) + 0.55) / Math.max(1, stageCount)),
  );
  const context = sceneCode === 'WORK_FRONT' ? 0.72 : sceneCode === 'CRANE_SECTOR' ? 0.9 : 0.55;
  const score = Math.round(
    100 * Math.max(0, Math.min(1, 0.55 * sim + 0.3 * stagePosition + 0.15 * context)),
  );
  return {
    key: `${frameImage}|${designView.length}|${stageIndex}`,
    score,
    similarity: Math.round(sim * 100),
    confidence: sim > 0.72 ? 'высокая' : sim > 0.5 ? 'средняя' : 'низкая',
    stagePosition: Math.round(stagePosition * 100),
  };
}
