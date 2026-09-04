import { Pool, type PoolConfig } from 'pg';
import { env } from '../config/env';
import { logger } from '../logging/logger';

let pool: Pool | null = null;

function quoteIdentifier(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

function poolConfig(overrides: Partial<PoolConfig> = {}): PoolConfig {
  const schema = env.CENTRAL_AUTH_POSTGRES_SCHEMA;
  return {
    host: env.POSTGRES_HOST,
    port: env.POSTGRES_PORT,
    user: env.POSTGRES_USER,
    password: env.POSTGRES_PASSWORD,
    database: env.POSTGRES_DB,
    max: env.POSTGRES_MAX_POOL_SIZE,
    ssl: env.POSTGRES_SSL ? { rejectUnauthorized: env.POSTGRES_SSL_REJECT_UNAUTHORIZED } : false,
    application_name: env.SERVICE_NAME,
    options: `-c search_path=${schema},public`,
    ...overrides,
  };
}

export async function connectPostgres(overrides: Partial<PoolConfig> = {}): Promise<Pool> {
  if (pool) return pool;

  const candidate = new Pool(poolConfig(overrides));
  candidate.on('error', (err) => logger.error({ err }, 'Unexpected PostgreSQL pool error'));

  try {
    await candidate.query(`CREATE SCHEMA IF NOT EXISTS ${quoteIdentifier(env.CENTRAL_AUTH_POSTGRES_SCHEMA)}`);
    await candidate.query('SELECT 1');
  } catch (err) {
    await candidate.end().catch(() => undefined);
    throw err;
  }

  pool = candidate;
  logger.info({ host: env.POSTGRES_HOST, database: env.POSTGRES_DB, schema: env.CENTRAL_AUTH_POSTGRES_SCHEMA }, 'PostgreSQL connected');
  return pool;
}

export function getPostgresPool(): Pool {
  if (!pool) throw new Error('PostgreSQL is not connected. Call connectPostgres() first.');
  return pool;
}

export async function disconnectPostgres(): Promise<void> {
  const current = pool;
  pool = null;
  if (!current) return;

  try {
    await current.end();
    logger.info('PostgreSQL disconnected');
  } catch (err) {
    logger.warn({ err }, 'Error while disconnecting PostgreSQL');
  }
}

export async function postgresPing(): Promise<boolean> {
  try {
    await getPostgresPool().query('SELECT 1');
    return true;
  } catch {
    return false;
  }
}
