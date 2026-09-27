import mongoose from 'mongoose';
import { env } from '../config/env';
import { logger } from '../logging/logger';

export interface ConnectMongooseOptions {
  uri?: string;
  dbName?: string;
  memory?: boolean;
  retryWrites?: boolean;
  tls?: boolean;
  minPoolSize?: number;
  maxPoolSize?: number;
}

export async function connectMongoose(options: ConnectMongooseOptions = {}) {
  const effectiveUri = options.uri ?? String(env.MONGODB_URI);
  const uri = new URL(effectiveUri);
  const params = uri.searchParams;

  if (options.memory) {
    if (!params.has('retryWrites')) params.set('retryWrites', String(options.retryWrites ?? false));
    if (params.has('tls')) params.set('tls', 'false');
  } else {
    if (!params.has('retryWrites')) params.set('retryWrites', String(options.retryWrites ?? env.MONGODB_RETRY_WRITES));
    if (!params.has('tls') && uri.protocol === 'mongodb+srv:') params.set('tls', String(options.tls ?? env.MONGODB_TLS));
  }

  uri.search = params.toString();

  await mongoose.connect(uri.toString(), {
    dbName: options.dbName ?? env.MONGODB_DB_NAME,
    minPoolSize: options.minPoolSize ?? env.MONGODB_MIN_POOL_SIZE,
    maxPoolSize: options.maxPoolSize ?? env.MONGODB_MAX_POOL_SIZE,
    serverSelectionTimeoutMS: 8_000,
  });

  logger.info({ host: mongoose.connection.host, db: mongoose.connection.name, memory: Boolean(options.memory) }, 'Mongoose connected');
}

export async function getMongoDBClient() {
  if (mongoose.connection.readyState !== 1 || !mongoose.connection.db) {
    throw new Error('Mongoose is not connected. Call connectMongoose() first.');
  }
  return mongoose.connection.db;
}

export async function disconnectMongoose() {
  try {
    await mongoose.disconnect();
    logger.info('Mongoose disconnected');
  } catch (err) {
    logger.warn({ err }, 'Error while disconnecting Mongoose');
  }
}

export async function mongoosePing(): Promise<boolean> {
  try {
    const db = mongoose.connection.db;
    if (!db) return false;
    await db.admin().ping();
    return true;
  } catch {
    return false;
  }
}
