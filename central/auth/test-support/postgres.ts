import { env } from '../src/config/env';
import { connectPostgres, disconnectPostgres, getPostgresPool } from '../src/db/postgres';

const DEFAULT_TEST_SCHEMA = 'central_auth_test';

export async function startTestPostgres() {
  env.POSTGRES_HOST = process.env.CENTRAL_AUTH_TEST_POSTGRES_HOST || '127.0.0.1';
  env.POSTGRES_PORT = Number(process.env.CENTRAL_AUTH_TEST_POSTGRES_PORT || '5433');
  env.POSTGRES_USER = process.env.CENTRAL_AUTH_TEST_POSTGRES_USER || 'postgres';
  env.POSTGRES_PASSWORD = process.env.CENTRAL_AUTH_TEST_POSTGRES_PASSWORD || 'password';
  env.POSTGRES_DB = process.env.CENTRAL_AUTH_TEST_POSTGRES_DB || 'central_auth_test';
  env.CENTRAL_AUTH_POSTGRES_SCHEMA = process.env.CENTRAL_AUTH_TEST_POSTGRES_SCHEMA || DEFAULT_TEST_SCHEMA;
  env.POSTGRES_SSL = false;

  if (!env.CENTRAL_AUTH_POSTGRES_SCHEMA.endsWith('_test')) {
    throw new Error(`Refusing to use PostgreSQL schema "${env.CENTRAL_AUTH_POSTGRES_SCHEMA}"; test schemas must end in _test.`);
  }

  await connectPostgres();
}

export async function dropTestDatabase() {
  const schema = env.CENTRAL_AUTH_POSTGRES_SCHEMA;
  if (!schema.endsWith('_test')) {
    throw new Error(`Refusing to clear PostgreSQL schema "${schema}"; test schemas must end in _test.`);
  }
  const pool = getPostgresPool();
  await pool.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`);
  await pool.query(`CREATE SCHEMA "${schema}"`);
}

export async function stopTestPostgres() {
  await disconnectPostgres();
}
