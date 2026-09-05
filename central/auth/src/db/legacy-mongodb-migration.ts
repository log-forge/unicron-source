import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { MongoClient, type Document } from 'mongodb';
import { env } from '../config/env';
import { getAuthStore, type AuthStore, type AuthUser, type ImportedCredential } from './auth-store';
import { logger } from '../logging/logger';

function asDate(value: unknown, fallback: Date): Date {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (typeof value === 'string' || typeof value === 'number') {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  return fallback;
}

function mapLegacyUser(document: Document): AuthUser {
  const now = new Date();
  return {
    id: String(document._id),
    email: String(document.email),
    emailVerified: document.emailVerified !== false,
    name: typeof document.name === 'string' ? document.name : null,
    username: typeof document.username === 'string' ? document.username : null,
    displayUsername: typeof document.displayUsername === 'string' ? document.displayUsername : null,
    image: typeof document.image === 'string' ? document.image : null,
    requiresPasswordChange: document.requiresPasswordChange === true,
    createdAt: asDate(document.createdAt, now),
    updatedAt: asDate(document.updatedAt, now),
  };
}

function mapLegacyCredential(document: Document | null): ImportedCredential | undefined {
  if (!document) return undefined;
  return {
    id: String(document._id),
    ...(typeof document.accountId === 'string' ? { accountId: document.accountId } : {}),
    ...(typeof document.password === 'string' ? { password: document.password } : {}),
    createdAt: asDate(document.createdAt, new Date()),
    updatedAt: asDate(document.updatedAt, new Date()),
  };
}

export async function importLegacyMongoDocuments(store: AuthStore, users: Document[], credential: Document | null): Promise<string | null> {
  if (users.length > 1) {
    throw new Error(`central/auth migration found ${users.length} MongoDB users; local appliance auth supports exactly one administrator.`);
  }
  if (users.length === 0) return null;
  if (typeof credential?.password !== 'string' || !credential.password.trim()) {
    throw new Error('Legacy MongoDB administrator has no password credential; refusing to replace it with a bootstrap password.');
  }

  const user = mapLegacyUser(users[0]);
  await store.importLegacyAdmin(user, mapLegacyCredential(credential));
  return user.id;
}

async function writeMigrationMarker(path?: string): Promise<void> {
  if (!path) return;
  await mkdir(dirname(path), { recursive: true });
  const temporaryPath = `${path}.tmp-${process.pid}`;
  await writeFile(temporaryPath, `completed=${new Date().toISOString()}\n`, { mode: 0o600 });
  await rename(temporaryPath, path);
}

export async function migrateLegacyMongoAuth(store: AuthStore = getAuthStore()): Promise<void> {
  let sourceRequiresMigration = false;
  if (env.LEGACY_MONGODB_SOURCE_STATE_FILE) {
    const state = (await readFile(env.LEGACY_MONGODB_SOURCE_STATE_FILE, 'utf8')).trim();
    if (state === 'empty') return;
    if (state !== 'required' && state !== 'completed') throw new Error('Unknown legacy MongoDB source state; refusing to bootstrap.');
    sourceRequiresMigration = true;
  }
  if (!env.LEGACY_MONGODB_URI && !env.LEGACY_MONGODB_MIGRATION_MARKER && !sourceRequiresMigration) return;

  const existingUsers = await store.listUsers();
  if (existingUsers.length > 1) {
    throw new Error(`central/auth migration found ${existingUsers.length} PostgreSQL users; local appliance auth supports exactly one administrator.`);
  }
  if (env.LEGACY_MONGODB_MIGRATION_MARKER) {
    const marker = await readFile(env.LEGACY_MONGODB_MIGRATION_MARKER, 'utf8').catch((err: NodeJS.ErrnoException) => {
      if (err.code === 'ENOENT') return '';
      throw err;
    });
    if (marker.trim()) {
      if (existingUsers.length !== 1) throw new Error('Legacy migration is marked complete but the PostgreSQL administrator is missing; restore PostgreSQL before starting auth.');
      if (!(await store.readCredentialPassword(existingUsers[0].id))?.trim()) throw new Error('Migrated PostgreSQL administrator has no password credential; restore it before starting auth.');
      return;
    }
  }

  if (!env.LEGACY_MONGODB_URI) {
    if (sourceRequiresMigration) throw new Error('Legacy MongoDB migration is required but its connection URI is missing.');
    return;
  }

  const client = new MongoClient(String(env.LEGACY_MONGODB_URI), { serverSelectionTimeoutMS: 8_000 });
  try {
    await client.connect();
    const database = client.db(env.LEGACY_MONGODB_DB_NAME);
    const users = await database.collection('user').find({}).sort({ createdAt: 1 }).limit(2).toArray();
    if (users.length === 1) {
      const legacyUser = users[0];
      const credential = await database.collection('account').findOne({ userId: legacyUser._id, providerId: 'credential' });
      if (typeof credential?.password !== 'string' || !credential.password.trim()) throw new Error('Legacy MongoDB administrator has no password credential; refusing to bootstrap.');
      if (existingUsers.length === 1) {
        // An import can commit before its filesystem marker is written. Only the same identity is a safe retry.
        if (existingUsers[0].id !== String(legacyUser._id)) throw new Error('PostgreSQL and legacy MongoDB contain different administrators; refusing to replace either account.');
        if ((await store.readCredentialPassword(existingUsers[0].id)) !== credential.password) throw new Error('PostgreSQL and legacy MongoDB credentials differ without a completed migration; refusing to bootstrap.');
      } else {
        await importLegacyMongoDocuments(store, users, credential);
      }
      logger.warn({ userId: String(legacyUser._id), sessionsMigrated: false }, 'Migrated local administrator from MongoDB to PostgreSQL; existing sessions were revoked');
      await writeMigrationMarker(env.LEGACY_MONGODB_MIGRATION_MARKER);
    } else {
      throw new Error(`Legacy MongoDB migration expected exactly one administrator but found ${users.length}; check the database name and restore missing auth data before starting auth.`);
    }
  } finally {
    await client.close().catch(() => undefined);
  }
}
