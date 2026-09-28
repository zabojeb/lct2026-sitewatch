export const DAY = 86_400_000;
export const MINUTE = 60_000;

export const time = (value: string | number) => new Date(value).getTime();

const fmt = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('ru-RU', options);
const shortFmt = fmt({ day: 'numeric', month: 'short' });
const dateFmt = fmt({ day: '2-digit', month: '2-digit', year: 'numeric' });
const clockFmt = fmt({ hour: '2-digit', minute: '2-digit' });
const clockSecFmt = fmt({ hour: '2-digit', minute: '2-digit', second: '2-digit' });
const fullFmt = fmt({
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

export const shortDate = (value: string | number) => shortFmt.format(new Date(value));
export const numericDate = (value: string | number) => dateFmt.format(new Date(value));
export const clock = (value: string | number) => clockFmt.format(new Date(value));
export const clockSec = (value: string | number) => clockSecFmt.format(new Date(value));
export const fullDateTime = (value: string | number) => fullFmt.format(new Date(value));
export const isoDate = (value: number) => new Date(value).toISOString().slice(0, 10);

/** Russian plural: plural(5, ['день', 'дня', 'дней']). */
export function plural(value: number, forms: [string, string, string]) {
  const n = Math.abs(Math.round(value)) % 100;
  const m = n % 10;
  if (n > 10 && n < 20) return forms[2];
  if (m === 1) return forms[0];
  if (m >= 2 && m <= 4) return forms[1];
  return forms[2];
}

export const days = (n: number) => `${n} ${plural(n, ['день', 'дня', 'дней'])}`;
export const cameras = (n: number) => `${n} ${plural(n, ['камера', 'камеры', 'камер'])}`;
export const frames = (n: number) => `${n} ${plural(n, ['кадр', 'кадра', 'кадров'])}`;
export const objects = (n: number) => `${n} ${plural(n, ['объект', 'объекта', 'объектов'])}`;

/** Human duration between two instants. */
export function duration(ms: number) {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} с`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return s ? `${m} мин ${s} с` : `${m} мин`;
  }
  const hours = seconds / 3600;
  if (hours < 48) return `${Math.round(hours * 10) / 10} ч`;
  return days(Math.round(hours / 24));
}

export const percent = (value: number) => `${Math.round(value * 100)}%`;
