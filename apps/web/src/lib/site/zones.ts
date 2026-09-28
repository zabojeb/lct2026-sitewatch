import type { Bbox, Point, SiteBox, Zone } from './types';

/** Ray casting; polygon and point in percent of the frame. */
export function pointInPolygon([x, y]: Point, polygon: Point[]) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Bottom centre of the box — where the machine touches the ground. */
export const footPoint = ([cx, cy, , h]: Bbox): Point => [cx * 100, (cy + h / 2) * 100];

/** First forbidden zone the box is inside of, if its class is banned there. */
export const zoneFor = (box: SiteBox, zones: Zone[]) =>
  zones.find(
    (zone) => zone.equipment.includes(box.slug) && pointInPolygon(footPoint(box.bbox), zone.points),
  );

export const zoneCenter = (zone: Zone): Point => {
  const n = zone.points.length || 1;
  return zone.points.reduce<Point>((sum, [x, y]) => [sum[0] + x / n, sum[1] + y / n], [0, 0]);
};

/** Splits edge i by inserting its midpoint. */
export function splitEdge(zone: Zone, i: number): Zone {
  const a = zone.points[i];
  const b = zone.points[(i + 1) % zone.points.length];
  const points = [...zone.points];
  points.splice(i + 1, 0, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
  return { ...zone, points };
}

export const clampPoint = ([x, y]: Point): Point => [
  Math.max(0, Math.min(100, x)),
  Math.max(0, Math.min(100, y)),
];

const imageCache = new Map<string, Promise<HTMLImageElement>>();
export function loadImage(src: string) {
  let pending = imageCache.get(src);
  if (!pending) {
    pending = new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = reject;
      image.src = src;
    });
    imageCache.set(src, pending);
  }
  return pending;
}

/** Share of the polygon that is readable on this frame: pixels that are neither blown out
 * nor crushed to black. It says whether the zone can be judged from this view, not whether
 * it is covered in metres — that needs camera calibration against the site plan. */
export async function zoneVisibility(image: string, zone: Zone) {
  const img = await loadImage(image);
  const width = 180;
  const height = Math.max(80, Math.round((width * img.naturalHeight) / img.naturalWidth));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return 0;
  context.drawImage(img, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height).data;
  let total = 0;
  let readable = 0;
  for (let y = 0; y < height; y += 2)
    for (let x = 0; x < width; x += 2) {
      if (!pointInPolygon([((x + 0.5) / width) * 100, ((y + 0.5) / height) * 100], zone.points))
        continue;
      total++;
      const at = (y * width + x) * 4;
      const [r, g, b] = [pixels[at], pixels[at + 1], pixels[at + 2]];
      const light = 0.299 * r + 0.587 * g + 0.114 * b;
      const spread = Math.max(r, g, b) - Math.min(r, g, b);
      if (light > 9 && light < 247 && (spread > 3 || (light > 24 && light < 232))) readable++;
    }
  return total ? Math.round((readable / total) * 100) : 0;
}
