import createClient from 'openapi-fetch';
import { env } from '$env/dynamic/public';

import type { paths } from './schema';

const baseUrl = env.PUBLIC_API_BASE_URL || 'http://localhost:8080';

export const api = createClient<paths>({ baseUrl });
