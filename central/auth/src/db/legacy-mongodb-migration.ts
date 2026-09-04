import { mkdir, rename, writeFile } from 'node:fs/promises';
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
  if (!env.LEGACY_MONGODB_URI) return;

  const existingUsers = await store.listUsers();
  if (existingUsers.length > 1) {
    throw new Error(`central/auth migration found ${existingUsers.length} PostgreSQL users; local appliance auth supports exactly one administrator.`);
  }
  if (existingUsers.length === 1) {
    await writeMigrationMarker(env.LEGACY_MONGODB_MIGRATION_MARKER);
    logger.info({ userId: existingUsers[0].id }, 'Legacy MongoDB auth migration was already applied');
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
      await importLegacyMongoDocuments(store, users, credential);
      logger.warn({ userId: String(legacyUser._id), sessionsMigrated: false }, 'Migrated local administrator from MongoDB to PostgreSQL; existing sessions were revoked');
    } else {
      await importLegacyMongoDocuments(store, users, null);
      logger.info('Legacy MongoDB auth database was empty; PostgreSQL bootstrap will create the administrator');
    }

    await writeMigrationMarker(env.LEGACY_MONGODB_MIGRATION_MARKER);
  } finally {
    await client.close().catch(() => undefined);
  }
}
