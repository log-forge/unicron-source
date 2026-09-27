import { getMongoDBClient } from '../../src/db/mongoose';
import { createApp } from '../../src/app';
import { bootstrapLocalAdmin } from '../../src/lib/bootstrap-admin';
import { createAuth } from '../../src/lib/auth';
import { env } from '../../src/config/env';

export const TEST_PASSWORD = 'Start-Password1!';
export const TEST_SECRET = 'test-central-auth-secret-minimum-32-characters';

export function resetAuthEnv(overrides: Partial<typeof env> = {}) {
  env.NODE_ENV = 'test';
  env.CENTRAL_AUTH_SECRET = TEST_SECRET;
  env.CENTRAL_AUTH_BASE_URL = 'http://localhost:3020';
  env.CENTRAL_AUTH_COOKIE_NAME = 'test.central_auth.session';
  env.CENTRAL_ADMIN_USERNAME = 'admin';
  env.CENTRAL_ADMIN_PASSWORD = TEST_PASSWORD;
  env.CENTRAL_ADMIN_RECOVERY_OVERRIDE = false;
  env.CORS_ORIGINS = 'http://localhost:3000';
  Object.assign(env, overrides);
}

export async function buildBootstrappedApp() {
  const auth = await createAuth({ mongoDb: await getMongoDBClient() });
  await bootstrapLocalAdmin();
  return createApp(auth);
}
