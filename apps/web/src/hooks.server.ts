import { createHash, timingSafeEqual } from 'node:crypto';
import { env } from '$env/dynamic/private';
import type { Handle } from '@sveltejs/kit';

const cookieName = 'sitewatch_demo_access';

function matches(candidate: string | null | undefined, expected: string): boolean {
  if (!candidate || candidate.length > 128) return false;
  const candidateHash = createHash('sha256').update(candidate).digest();
  const expectedHash = createHash('sha256').update(expected).digest();
  return timingSafeEqual(candidateHash, expectedHash);
}

export const handle: Handle = async ({ event, resolve }) => {
  const token = env.SITEWATCH_SHARE_TOKEN;
  if (!token) return resolve(event);
  if (token.length < 48) {
    return new Response('SiteWatch share token is misconfigured.', { status: 503 });
  }

  const supplied = event.url.searchParams.get('access');
  if (
    event.request.method === 'GET' &&
    event.url.pathname === '/app/model' &&
    matches(supplied, token)
  ) {
    const cookie = event.cookies.serialize(cookieName, token, {
      path: '/',
      httpOnly: true,
      secure: event.url.protocol === 'https:',
      sameSite: 'lax',
      maxAge: 8 * 60 * 60,
    });
    const cleanUrl = new URL(event.url);
    cleanUrl.searchParams.delete('access');
    return new Response(null, {
      status: 303,
      headers: {
        Location: `${cleanUrl.pathname}${cleanUrl.search}`,
        'Set-Cookie': cookie,
        'Cache-Control': 'no-store',
        'Referrer-Policy': 'no-referrer',
      },
    });
  }

  if (!matches(event.cookies.get(cookieName), token)) {
    return new Response('Нужна действующая секретная ссылка SiteWatch.', {
      status: 403,
      headers: { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' },
    });
  }

  const response = await resolve(event);
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('Referrer-Policy', 'no-referrer');
  return response;
};
