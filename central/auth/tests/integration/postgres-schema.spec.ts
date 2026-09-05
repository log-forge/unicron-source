import { afterAll, beforeAll, expect, it } from 'vitest';
import { env } from '../../src/config/env';
import { connectPostgres, disconnectPostgres, getPostgresPool } from '../../src/db/postgres';
import { migrateAuthSchema } from '../../src/lib/auth';
import { dropTestDatabase, startTestPostgres, stopTestPostgres } from '../../test-support/postgres';

beforeAll(async () => {
  await startTestPostgres();
  await disconnectPostgres();
  env.CENTRAL_AUTH_POSTGRES_SCHEMA = 'CentralAuth_restart_test';
  await connectPostgres();
  await dropTestDatabase();
});

afterAll(async () => {
  await getPostgresPool().query('DROP SCHEMA IF EXISTS "CentralAuth_restart_test" CASCADE');
  await stopTestPostgres();
});

it('keeps mixed-case schemas isolated and migrates again after reconnecting', async () => {
  for (let boot = 0; boot < 2; boot++) {
    const pool = await connectPostgres();
    expect((await pool.query('SELECT current_schema() AS schema')).rows[0].schema).toBe('CentralAuth_restart_test');
    await migrateAuthSchema({ postgresPool: pool });
    const tables = await pool.query("SELECT tablename FROM pg_tables WHERE schemaname = $1 ORDER BY tablename", [env.CENTRAL_AUTH_POSTGRES_SCHEMA]);
    expect(tables.rows.map((row) => row.tablename)).toEqual(['account', 'session', 'user', 'verification']);
    await disconnectPostgres();
  }
  await connectPostgres();
});
