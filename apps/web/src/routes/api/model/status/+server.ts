import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
  if (env.INFERENCE_DEMO_ENABLED !== 'true') {
    return json(
      { status: 'disabled', rules_status: 'disabled' },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  }
  const modelConfigured = (env.SITEWATCH_INTERNAL_TOKEN ?? '').length >= 32;
  const rulesConfigured =
    (env.DEVIATIONS_INTERNAL_TOKEN ?? env.SITEWATCH_INTERNAL_TOKEN ?? '').length >= 32;
  const [inference, deviations] = await Promise.allSettled([
    modelConfigured
      ? fetch(`${env.INFERENCE_URL ?? 'http://127.0.0.1:8083'}/health/ready`, {
          signal: AbortSignal.timeout(3000),
        })
      : Promise.reject(new Error('Model token not configured')),
    rulesConfigured
      ? fetch(`${env.DEVIATIONS_URL ?? 'http://127.0.0.1:8084'}/health/ready`, {
          signal: AbortSignal.timeout(3000),
        })
      : Promise.reject(new Error('Rules token not configured')),
  ]);
  let status = 'unavailable';
  let modelVersion = '';
  if (inference.status === 'fulfilled' && inference.value.ok) {
    try {
      const ready = (await inference.value.json()) as {
        model_version?: string;
        recognition_modes?: string[];
      };
      if (ready.model_version && ready.recognition_modes?.includes('640') && ready.recognition_modes?.includes('960')) {
        status = 'ready';
        modelVersion = ready.model_version;
      }
    } catch {
      // An invalid readiness payload is not a ready model.
    }
  }
  return json(
    {
      status,
      rules_status:
        deviations.status === 'fulfilled' && deviations.value.ok ? 'ready' : 'unavailable',
      vlm_status: env.OPENROUTER_API_KEY ? 'ready' : 'disabled',
      ...(modelVersion ? { model_version: modelVersion } : {}),
      recognition_modes: status === 'ready' ? ['640', '960'] : [],
    },
    { headers: { 'Cache-Control': 'no-store' } },
  );
};
