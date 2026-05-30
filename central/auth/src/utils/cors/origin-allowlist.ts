import { env } from '../../config/env';

export function normalizeOrigin(value: string): string | null {
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

function parseConfiguredOrigins(): Set<string> {
  const configured = new Set<string>();
  configured.add(new URL(env.CENTRAL_AUTH_BASE_URL).origin);

  for (const raw of (env.CORS_ORIGINS ?? '').split(',')) {
    const value = raw.trim();
    if (!value) continue;
    if (value === '*') {
      configured.add('*');
      continue;
    }
    const normalized = normalizeOrigin(value);
    if (normalized) configured.add(normalized);
  }

  return configured;
}

export const baseAllowedOrigins = parseConfiguredOrigins();

export async function isOriginAllowed(origin: string): Promise<boolean> {
  if (baseAllowedOrigins.has('*')) return true;
  const normalized = normalizeOrigin(origin);
  return Boolean(normalized && baseAllowedOrigins.has(normalized));
}
