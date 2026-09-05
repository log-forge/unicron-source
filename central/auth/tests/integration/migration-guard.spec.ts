import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, beforeEach, expect, it } from 'vitest';
import { env } from '../../src/config/env';
import { getAuthStore } from '../../src/db/auth-store';
import { getPostgresPool } from '../../src/db/postgres';
import { importLegacyMongoDocuments, migrateLegacyMongoAuth } from '../../src/db/legacy-mongodb-migration';
import { migrateAuthSchema } from '../../src/lib/auth';
import { dropTestDatabase, startTestPostgres, stopTestPostgres } from '../../test-support/postgres';
import { buildBootstrappedApp, resetAuthEnv } from '../setup/app';

let directory: string;
beforeAll(async () => {
  directory = await mkdtemp(join(tmpdir(), 'auth-migration-test-'));
  await startTestPostgres();
});
beforeEach(async () => {
  resetAuthEnv();
  await dropTestDatabase();
  await migrateAuthSchema();
  env.LEGACY_MONGODB_SOURCE_STATE_FILE = join(directory, 'source-state');
  env.LEGACY_MONGODB_MIGRATION_MARKER = join(directory, 'completed');
  env.LEGACY_MONGODB_URI = 'mongodb://127.0.0.1:1';
  await rm(env.LEGACY_MONGODB_SOURCE_STATE_FILE, { force: true });
  await rm(env.LEGACY_MONGODB_MIGRATION_MARKER, { force: true });
});
afterAll(async () => {
  await stopTestPostgres();
  await rm(directory, { recursive: true, force: true });
});

it('skips MongoDB for a confirmed empty volume', async () => {
  await writeFile(env.LEGACY_MONGODB_SOURCE_STATE_FILE!, 'empty\n');
  await expect(migrateLegacyMongoAuth()).resolves.toBeUndefined();
  await buildBootstrappedApp();
});

it('fails closed when the volume inspection is missing or invalid', async () => {
  await expect(migrateLegacyMongoAuth()).rejects.toThrow('ENOENT');
  await writeFile(env.LEGACY_MONGODB_SOURCE_STATE_FILE!, 'unexpected\n');
  await expect(migrateLegacyMongoAuth()).rejects.toThrow('refusing to bootstrap');
});

it('requires a connection for legacy data', async () => {
  await writeFile(env.LEGACY_MONGODB_SOURCE_STATE_FILE!, 'required\n');
  env.LEGACY_MONGODB_URI = undefined;
  await expect(migrateLegacyMongoAuth()).rejects.toThrow('connection URI is missing');
});

it.each([true, false])('does not contact MongoDB after a completed migration (URI configured: %s)', async (uriConfigured) => {
  await buildBootstrappedApp();
  await writeFile(env.LEGACY_MONGODB_SOURCE_STATE_FILE!, 'completed\n');
  await writeFile(env.LEGACY_MONGODB_MIGRATION_MARKER!, 'completed=test\n');
  if (!uriConfigured) {
    env.LEGACY_MONGODB_SOURCE_STATE_FILE = undefined;
    env.LEGACY_MONGODB_URI = undefined;
  }
  await expect(migrateLegacyMongoAuth()).resolves.toBeUndefined();
});

it.each([true, false])('does not recreate a lost migrated administrator (URI configured: %s)', async (uriConfigured) => {
  await writeFile(env.LEGACY_MONGODB_SOURCE_STATE_FILE!, 'completed\n');
  await writeFile(env.LEGACY_MONGODB_MIGRATION_MARKER!, 'completed=test\n');
  if (!uriConfigured) {
    env.LEGACY_MONGODB_SOURCE_STATE_FILE = undefined;
    env.LEGACY_MONGODB_URI = undefined;
  }
  await expect(migrateLegacyMongoAuth()).rejects.toThrow('administrator is missing');
});

it.each([true, false])('does not repair a missing migrated password (URI configured: %s)', async (uriConfigured) => {
  await buildBootstrappedApp();
  await getPostgresPool().query('UPDATE account SET password = NULL');
  await writeFile(env.LEGACY_MONGODB_SOURCE_STATE_FILE!, 'completed\n');
  await writeFile(env.LEGACY_MONGODB_MIGRATION_MARKER!, 'completed=test\n');
  if (!uriConfigured) {
    env.LEGACY_MONGODB_SOURCE_STATE_FILE = undefined;
    env.LEGACY_MONGODB_URI = undefined;
  }
  await expect(migrateLegacyMongoAuth()).rejects.toThrow('no password credential');
});

it('allows fresh appliance bootstrap when no migration marker exists', async () => {
  env.LEGACY_MONGODB_SOURCE_STATE_FILE = undefined;
  env.LEGACY_MONGODB_URI = undefined;
  await expect(migrateLegacyMongoAuth()).resolves.toBeUndefined();
  await buildBootstrappedApp();
});

it('refuses to import an administrator without their legacy password', async () => {
  await expect(importLegacyMongoDocuments(getAuthStore(), [{ _id: 'legacy-admin' }], null)).rejects.toThrow('no password credential');
  expect(await getAuthStore().listUsers()).toHaveLength(0);
});
