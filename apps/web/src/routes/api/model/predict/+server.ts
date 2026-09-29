import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const maxBytes = 12 * 1024 * 1024;
const imageTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);

export const POST: RequestHandler = async ({ request, url }) => {
  if (env.INFERENCE_DEMO_ENABLED !== 'true') {
    return json({ error: 'Живая проверка модели отключена.' }, { status: 503 });
  }
  if (request.headers.get('origin') !== url.origin) {
    return json({ error: 'Недопустимый источник запроса.' }, { status: 403 });
  }
  const contentLength = Number(request.headers.get('content-length') ?? 0);
  if (contentLength > maxBytes + 4096) {
    return json({ error: 'Файл должен быть не больше 12 МБ.' }, { status: 413 });
  }
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return json({ error: 'Некорректная форма загрузки.' }, { status: 400 });
  }
  const image = form.get('image');
  const recognitionMode = form.get('recognition_mode') ?? '640';
  if (recognitionMode !== '640' && recognitionMode !== '960') {
    return json({ error: 'Неизвестный режим распознавания.' }, { status: 400 });
  }
  if (!(image instanceof File) || !imageTypes.has(image.type)) {
    return json({ error: 'Выберите JPEG, PNG или WebP.' }, { status: 415 });
  }
  if (!image.size || image.size > maxBytes) {
    return json({ error: 'Файл должен быть не больше 12 МБ.' }, { status: 413 });
  }
  const internalToken = env.SITEWATCH_INTERNAL_TOKEN ?? '';
  if (internalToken.length < 32) {
    return json({ error: 'Не настроен внутренний токен модели.' }, { status: 503 });
  }
  const body = new FormData();
  body.set('image', image);
  body.set('recognition_mode', recognitionMode);
  try {
    const response = await fetch(`${env.INFERENCE_URL ?? 'http://127.0.0.1:8083'}/v1/predict`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${internalToken}` },
      body,
      signal: AbortSignal.timeout(120_000),
    });
    const result = await response.json();
    if (!response.ok) {
      return json(
        { error: typeof result.detail === 'string' ? result.detail : 'Модель отклонила кадр.' },
        { status: response.status },
      );
    }
    return json(result, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return json({ error: 'Сервис модели недоступен или не ответил вовремя.' }, { status: 503 });
  }
};
