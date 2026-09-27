import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_CENTRAL_ADMIN_PASSWORD } from '../../src/constants';
import { AccountModel } from '../../src/models/account.model';
import { SessionModel } from '../../src/models/session.model';
import { UserModel } from '../../src/models/user.model';
import { bootstrapLocalAdmin } from '../../src/lib/bootstrap-admin';
import { env, parseEnv } from '../../src/config/env';
import { logger } from '../../src/logging/logger';
import { buildBootstrappedApp, resetAuthEnv, TEST_PASSWORD, TEST_SECRET } from '../setup/app';
import { dropTestDatabase, startTestMongo, stopTestMongo } from '../setup/mongoose';

async function signIn(agent: any, username = env.CENTRAL_ADMIN_USERNAME, password = env.CENTRAL_ADMIN_PASSWORD ?? TEST_PASSWORD) {
  return agent.post('/api/auth/sign-in/username').send({ username, password }).expect(200);
}

function applyParsedAuthEnv(overrides: NodeJS.ProcessEnv = {}) {
  Object.assign(
    env,
    parseEnv({
      NODE_ENV: 'test',
      CENTRAL_AUTH_SECRET: TEST_SECRET,
      CENTRAL_AUTH_BASE_URL: 'http://localhost:3020',
      CENTRAL_AUTH_COOKIE_NAME: 'test.central_auth.session',
      CENTRAL_ADMIN_USERNAME: 'admin',
      CENTRAL_ADMIN_PASSWORD: TEST_PASSWORD,
      CENTRAL_ADMIN_RECOVERY_OVERRIDE: 'false',
      CORS_ORIGINS: 'http://localhost:3000',
      MONGODB_URI: env.MONGODB_URI,
      MONGODB_DB_NAME: env.MONGODB_DB_NAME,
      MONGODB_TLS: 'false',
      MONGODB_RETRY_WRITES: 'false',
      ...overrides,
    }),
  );
}

beforeAll(async () => {
  await startTestMongo();
});

beforeEach(async () => {
  vi.restoreAllMocks();
  resetAuthEnv();
  await dropTestDatabase();
});

afterAll(async () => {
  await stopTestMongo();
});

describe('local admin bootstrap', () => {
  it('creates the configured admin and credential on a fresh database', async () => {
    await buildBootstrappedApp();

    const users = await UserModel.find().lean();
    const accounts = await AccountModel.find().lean();

    expect(users).toHaveLength(1);
    expect(users[0]).toMatchObject({
      username: 'admin',
      displayUsername: 'admin',
      email: 'admin@local.unicron.invalid',
      emailVerified: true,
      requiresPasswordChange: false,
    });
    expect(accounts).toHaveLength(1);
    expect(accounts[0]).toMatchObject({ providerId: 'credential' });
  });

  it('auto-generates a first-boot admin credential only when no password is provided', async () => {
    resetAuthEnv({ CENTRAL_ADMIN_PASSWORD: undefined });
    const warnSpy = vi.spyOn(logger, 'warn');

    const app = await buildBootstrappedApp();
    const generatedCall = warnSpy.mock.calls.find(([meta]) => typeof meta === 'object' && meta !== null && 'generatedPassword' in meta);
    const generatedPassword = (generatedCall?.[0] as { generatedPassword?: string } | undefined)?.generatedPassword;

    expect(generatedPassword).toEqual(expect.stringMatching(/^Unicron-.+-A1!$/));

    const user = await UserModel.findOne().lean();
    expect(user).toMatchObject({
      username: 'admin',
      requiresPasswordChange: true,
    });

    await request(app).post('/api/auth/sign-in/username').send({ username: 'admin', password: generatedPassword }).expect(200);
  });

  it('reuses a matching user on restart without overwriting the password', async () => {
    const app = await buildBootstrappedApp();
    const agent = request.agent(app);
    await signIn(agent);
    await agent.get('/api/v1/profile').expect(200);
    const sessionCount = await SessionModel.countDocuments();

    env.CENTRAL_ADMIN_PASSWORD = undefined;
    await bootstrapLocalAdmin();

    expect(await SessionModel.countDocuments()).toBe(sessionCount);
    await agent.get('/api/v1/profile').expect(200);

    env.CENTRAL_ADMIN_PASSWORD = 'Replacement-Password1!';
    const warnSpy = vi.spyOn(logger, 'warn');
    await bootstrapLocalAdmin();

    const ignoredPasswordWarning = warnSpy.mock.calls.find(
      ([, message]) =>
        message ===
        'Configured CENTRAL_ADMIN_PASSWORD is intentionally ignored on normal restart; use CENTRAL_ADMIN_RECOVERY_OVERRIDE=true for credential recovery.',
    );
    expect(ignoredPasswordWarning).toBeDefined();
    expect(ignoredPasswordWarning?.[0]).toMatchObject({
      userId: expect.any(String),
      username: 'admin',
      recoveryOverride: false,
      sessionsRevoked: false,
    });
    expect(JSON.stringify(ignoredPasswordWarning)).not.toContain('Replacement-Password1!');
    expect(await SessionModel.countDocuments()).toBe(sessionCount);
    await agent.get('/api/v1/profile').expect(200);
    await request(app).post('/api/auth/sign-in/username').send({ username: 'admin', password: 'Replacement-Password1!' }).expect(401);
    await request(app).post('/api/auth/sign-in/username').send({ username: 'admin', password: TEST_PASSWORD }).expect(200);
  });

  it('treats CENTRAL_ADMIN_RECOVERY_OVERRIDE="false" as normal restart and preserves a changed password', async () => {
    const app = await buildBootstrappedApp();
    const agent = request.agent(app);
    await signIn(agent);
    await agent.post('/api/auth/change-password').send({ currentPassword: TEST_PASSWORD, newPassword: 'Rotated-Password1!' }).expect(200);

    applyParsedAuthEnv({
      CENTRAL_ADMIN_PASSWORD: TEST_PASSWORD,
      CENTRAL_ADMIN_RECOVERY_OVERRIDE: 'false',
    });
    await bootstrapLocalAdmin();

    await agent.get('/api/v1/profile').expect(200);
    await request(app).post('/api/auth/sign-in/username').send({ username: 'admin', password: TEST_PASSWORD }).expect(401);
    await request(app).post('/api/auth/sign-in/username').send({ username: 'admin', password: 'Rotated-Password1!' }).expect(200);
  });

  it('does not regenerate or reprint an admin credential on restart with an existing administrator', async () => {
    resetAuthEnv({ CENTRAL_ADMIN_PASSWORD: undefined });
    await buildBootstrappedApp();

    const warnSpy = vi.spyOn(logger, 'warn');
    await bootstrapLocalAdmin();

    expect(warnSpy.mock.calls.some(([meta]) => typeof meta === 'object' && meta !== null && 'generatedPassword' in meta)).toBe(false);
  });

  it('fails startup when one existing user does not match the configured username', async () => {
    await buildBootstrappedApp();

    env.CENTRAL_ADMIN_USERNAME = 'operator';
    env.CENTRAL_ADMIN_RECOVERY_OVERRIDE = false;

    await expect(bootstrapLocalAdmin()).rejects.toThrow(/CENTRAL_ADMIN_USERNAME is "operator"/);
  });

  it('rotates the sole user during recovery without creating a second user and revokes sessions', async () => {
    const app = await buildBootstrappedApp();
    const oldAgent = request.agent(app);
    await signIn(oldAgent);
    await oldAgent.get('/api/v1/profile').expect(200);

    applyParsedAuthEnv({
      CENTRAL_ADMIN_USERNAME: 'operator',
      CENTRAL_ADMIN_PASSWORD: 'Recovered-Password1!',
      CENTRAL_ADMIN_RECOVERY_OVERRIDE: 'true',
    });
    await bootstrapLocalAdmin();

    expect(await UserModel.countDocuments()).toBe(1);
    expect(await SessionModel.countDocuments()).toBe(0);
    const user = await UserModel.findOne().lean();
    expect(user).toMatchObject({
      username: 'operator',
      email: 'operator@local.unicron.invalid',
      requiresPasswordChange: true,
    });

    await oldAgent.get('/api/v1/profile').expect(401);

    const newAgent = request.agent(app);
    await newAgent.post('/api/auth/sign-in/username').send({ username: 'operator', password: 'Recovered-Password1!' }).expect(200);
    await request(app).post('/api/auth/sign-in/username').send({ username: 'admin', password: TEST_PASSWORD }).expect(401);
  });

  it('requires an explicit recovery password when recovery override is enabled', async () => {
    await buildBootstrappedApp();

    env.CENTRAL_ADMIN_RECOVERY_OVERRIDE = true;
    env.CENTRAL_ADMIN_PASSWORD = undefined;

    await expect(bootstrapLocalAdmin()).rejects.toThrow(/requires CENTRAL_ADMIN_PASSWORD/);
  });

  it('fails bootstrap when more than one user exists even during recovery', async () => {
    await buildBootstrappedApp();
    await UserModel.create({
      email: 'second@local.unicron.invalid',
      emailVerified: true,
      username: 'second',
      displayUsername: 'second',
      name: 'second',
    });

    env.CENTRAL_ADMIN_RECOVERY_OVERRIDE = true;
    await expect(bootstrapLocalAdmin()).rejects.toThrow(/supports exactly one administrator/);
  });
});

describe('username session flow', () => {
  it('signs in with username and signs out', async () => {
    const app = await buildBootstrappedApp();
    const agent = request.agent(app);

    await signIn(agent, 'ADMIN', TEST_PASSWORD);
    await agent.get('/api/v1/profile').expect(200);
    await agent.post('/api/auth/sign-out').expect(200);
    await agent.get('/api/v1/profile').expect(401);
  });

  it('returns the local appliance profile shape without exposing the synthetic email', async () => {
    const app = await buildBootstrappedApp();
    const agent = request.agent(app);
    await signIn(agent);

    const res = await agent.get('/api/v1/profile').expect(200);

    expect(res.body).toMatchObject({
      status: 'ok',
      data: {
        user: {
          username: 'admin',
          displayUsername: 'admin',
          name: 'admin',
        },
        session: {
          userId: expect.any(String),
        },
        isAdmin: true,
        deploymentId: 'local',
        requiresPasswordChange: false,
      },
    });
    expect(res.body.data.user).not.toHaveProperty('email');
  });

  it('rejects unauthenticated profile requests', async () => {
    const app = await buildBootstrappedApp();
    await request(app).get('/api/v1/profile').expect(401);
  });

  it('clears requiresPasswordChange after a signed-in password change', async () => {
    resetAuthEnv({ CENTRAL_ADMIN_PASSWORD: DEFAULT_CENTRAL_ADMIN_PASSWORD });
    const app = await buildBootstrappedApp();
    const agent = request.agent(app);
    await signIn(agent, 'admin', DEFAULT_CENTRAL_ADMIN_PASSWORD);

    const before = await agent.get('/api/v1/profile').expect(200);
    expect(before.body.data.requiresPasswordChange).toBe(true);

    await agent.post('/api/auth/change-password').send({ currentPassword: DEFAULT_CENTRAL_ADMIN_PASSWORD, newPassword: 'Rotated-Password1!' }).expect(200);

    const after = await agent.get('/api/v1/profile').expect(200);
    expect(after.body.data.requiresPasswordChange).toBe(false);
    await request(app).post('/api/auth/sign-in/username').send({ username: 'admin', password: DEFAULT_CENTRAL_ADMIN_PASSWORD }).expect(401);
    await request(app).post('/api/auth/sign-in/username').send({ username: 'admin', password: 'Rotated-Password1!' }).expect(200);
  });

  it('does not accept bearer-only auth for the profile endpoint', async () => {
    const app = await buildBootstrappedApp();
    const agent = request.agent(app);
    const login = await signIn(agent);

    await request(app).get('/api/v1/profile').set('authorization', `Bearer ${login.body.token}`).expect(401);
  });
});

describe('disabled auth surfaces', () => {
  it('returns 404 for non-allowlisted Better Auth routes', async () => {
    const app = await buildBootstrappedApp();
    const cases: Array<{ method: 'get' | 'post'; path: string; body?: unknown }> = [
      { method: 'post', path: '/api/auth/sign-up/email', body: { email: 'new@example.com', password: TEST_PASSWORD, name: 'new' } },
      { method: 'post', path: '/api/auth/sign-in/email', body: { email: 'admin@local.unicron.invalid', password: TEST_PASSWORD } },
      { method: 'post', path: '/api/auth/request-password-reset', body: { email: 'admin@local.unicron.invalid' } },
      { method: 'post', path: '/api/auth/reset-password', body: { token: 'token', newPassword: 'Rotated-Password1!' } },
      { method: 'get', path: '/api/auth/verify-email?token=token' },
      { method: 'post', path: '/api/auth/send-verification-email', body: { email: 'admin@local.unicron.invalid' } },
      { method: 'post', path: '/api/auth/sign-in/social', body: { provider: 'github' } },
      { method: 'get', path: '/api/auth/callback/github?code=code' },
      { method: 'post', path: '/api/auth/organization/create', body: { name: 'Org', slug: 'org' } },
      { method: 'post', path: '/api/auth/organization/create-team', body: { name: 'Team' } },
      { method: 'get', path: '/api/auth/organization/list' },
      { method: 'post', path: '/api/auth/organization/create-role', body: { role: 'admin' } },
      { method: 'post', path: '/api/auth/stripe/create-checkout-session', body: {} },
      { method: 'post', path: '/api/auth/is-username-available', body: { username: 'admin' } },
    ];

    for (const testCase of cases) {
      const res = await request(app)[testCase.method](testCase.path).send(testCase.body ?? {});
      expect(res.status, `${testCase.method.toUpperCase()} ${testCase.path}`).toBe(404);
      expect(res.body).toMatchObject({ code: 'NOT_FOUND' });
    }
  });
});
