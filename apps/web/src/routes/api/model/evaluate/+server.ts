import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, url }) => {
  if (env.INFERENCE_DEMO_ENABLED !== 'true') {
    return json({ error: 'Проверка по плану отключена в этой сборке.' }, { status: 503 });
  }
  if (request.headers.get('origin') !== url.origin) {
    return json({ error: 'Недопустимый источник запроса.' }, { status: 403 });
  }
  if (Number(request.headers.get('content-length') ?? 0) > 512 * 1024) {
    return json({ error: 'Слишком большой пакет наблюдений.' }, { status: 413 });
  }
  const token = env.DEVIATIONS_INTERNAL_TOKEN ?? env.SITEWATCH_INTERNAL_TOKEN ?? '';
  if (token.length < 32) {
    return json({ error: 'Не настроен внутренний токен.' }, { status: 503 });
  }
  let body: string;
  try {
    body = await request.text();
    if (body.length > 512 * 1024 || !JSON.parse(body)) throw new Error('invalid');
  } catch {
    return json({ error: 'Некорректный пакет наблюдений.' }, { status: 400 });
  }
  try {
    const response = await fetch(
      `${env.DEVIATIONS_URL ?? 'http://127.0.0.1:8084'}/api/v1/evaluations:preview`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body,
        signal: AbortSignal.timeout(10_000),
      },
    );
    // A body the service could not parse is rejected as plain text, not JSON.
    const text = await response.text();
    let result: Record<string, unknown> = {};
    try {
      result = JSON.parse(text) as Record<string, unknown>;
    } catch {
      // keep the empty object: the status below still tells what happened
    }
    if (!response.ok) {
      return json(
        {
          error:
            typeof result.detail === 'string'
              ? result.detail
              : 'Сервис правил отклонил данные: проверьте числа в правилах (целые, не меньше нуля).',
        },
        { status: response.status },
      );
    }
    return json(result, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return json({ error: 'Сервис правил недоступен.' }, { status: 503 });
  }
};
