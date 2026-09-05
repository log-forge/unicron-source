import { describe, expect, it } from 'vitest';
import { parseEnv } from '../../src/config/env';

describe('environment parsing', () => {
  it('defaults CENTRAL_ADMIN_RECOVERY_OVERRIDE to false when missing', () => {
    expect(parseEnv({}).CENTRAL_ADMIN_RECOVERY_OVERRIDE).toBe(false);
  });

  it('parses CENTRAL_ADMIN_RECOVERY_OVERRIDE="false" as false', () => {
    expect(parseEnv({ CENTRAL_ADMIN_RECOVERY_OVERRIDE: 'false' }).CENTRAL_ADMIN_RECOVERY_OVERRIDE).toBe(false);
  });

  it('treats empty CENTRAL_ADMIN_RECOVERY_OVERRIDE as the default false value', () => {
    expect(parseEnv({ CENTRAL_ADMIN_RECOVERY_OVERRIDE: '' }).CENTRAL_ADMIN_RECOVERY_OVERRIDE).toBe(false);
  });

  it('parses CENTRAL_ADMIN_RECOVERY_OVERRIDE="true" as true', () => {
    expect(parseEnv({ CENTRAL_ADMIN_RECOVERY_OVERRIDE: 'true' }).CENTRAL_ADMIN_RECOVERY_OVERRIDE).toBe(true);
  });

  it('treats blank CENTRAL_ADMIN_PASSWORD as unset', () => {
    expect(parseEnv({ CENTRAL_ADMIN_PASSWORD: '' }).CENTRAL_ADMIN_PASSWORD).toBeUndefined();
  });

  it('rejects invalid boolean values', () => {
    expect(() => parseEnv({ CENTRAL_ADMIN_RECOVERY_OVERRIDE: 'sure' })).toThrow(/Expected boolean environment value/);
  });

  it('defaults Central Auth to its own PostgreSQL schema', () => {
    expect(parseEnv({}).CENTRAL_AUTH_POSTGRES_SCHEMA).toBe('central_auth');
  });

  it('rejects unsafe PostgreSQL schema names', () => {
    expect(() => parseEnv({ CENTRAL_AUTH_POSTGRES_SCHEMA: 'central-auth; DROP SCHEMA public' })).toThrow();
  });
});
