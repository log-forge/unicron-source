import dotenv from 'dotenv';
import { z } from 'zod';
import { DEFAULT_CENTRAL_ADMIN_USERNAME } from '../constants';

dotenv.config();

const ENV_BOOLEAN_VALUES = {
  true: new Set(['true', '1', 'yes', 'on']),
  false: new Set(['false', '0', 'no', 'off']),
};

const booleanEnvValue = z.boolean({
  error: 'Expected boolean environment value: true/false, 1/0, yes/no, or on/off',
});

function envBoolean<T extends z.ZodTypeAny>(schema: T) {
  return z.preprocess((value) => {
    if (value === undefined || value === null) return undefined;
    if (typeof value === 'boolean') return value;

    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      if (normalized.length === 0) return undefined;
      if (ENV_BOOLEAN_VALUES.true.has(normalized)) return true;
      if (ENV_BOOLEAN_VALUES.false.has(normalized)) return false;
    }

    return value;
  }, schema);
}

export const EnvSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().positive().default(3020),
  SERVICE_NAME: z.string().min(1).default('central-auth'),
  APP_VERSION: z.string().default('0.0.0'),
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
  LOG_PRETTY: envBoolean(booleanEnvValue.optional()),

  CORS_ORIGINS: z.string().optional(),
  COMPRESSION_ENABLED: envBoolean(booleanEnvValue.default(false)),
  BODY_PARSER_JSON_LIMIT: z.string().default('1mb'),
  REQUEST_TIMEOUT_MS: z.coerce.number().int().min(1000).default(30000),
  HEADERS_TIMEOUT_MS: z.coerce.number().int().min(1000).default(35000),
  KEEPALIVE_TIMEOUT_MS: z.coerce.number().int().min(0).default(5000),
  SHUTDOWN_DRAIN_MS: z.coerce.number().int().min(0).default(5000),

  POSTGRES_HOST: z.string().min(1).default('localhost'),
  POSTGRES_PORT: z.coerce.number().int().positive().default(5432),
  POSTGRES_USER: z.string().min(1).default('postgres'),
  POSTGRES_PASSWORD: z.string().default('postgres'),
  POSTGRES_DB: z.string().min(1).default('unicron'),
  CENTRAL_AUTH_POSTGRES_SCHEMA: z
    .string()
    .regex(/^[A-Za-z_][A-Za-z0-9_]*$/)
    .default('central_auth'),
  POSTGRES_MAX_POOL_SIZE: z.coerce.number().int().min(1).default(10),
  POSTGRES_SSL: envBoolean(booleanEnvValue.default(false)),
  POSTGRES_SSL_REJECT_UNAUTHORIZED: envBoolean(booleanEnvValue.default(true)),

  LEGACY_MONGODB_URI: z.preprocess((value) => (value === '' ? undefined : value), z.url().optional()),
  LEGACY_MONGODB_DB_NAME: z.string().min(1).default('unicron_central_auth'),
  LEGACY_MONGODB_MIGRATION_MARKER: z.preprocess((value) => (value === '' ? undefined : value), z.string().optional()),
  LEGACY_MONGODB_SOURCE_STATE_FILE: z.preprocess((value) => (value === '' ? undefined : value), z.string().optional()),

  CENTRAL_AUTH_SECRET: z.string().min(32).default('changeme-central-auth-secret-please-override-123456'),
  CENTRAL_AUTH_BASE_URL: z.url().default('http://localhost:3020'),
  CENTRAL_AUTH_COOKIE_NAME: z.string().min(1).default('unicron.central_auth.session'),

  CENTRAL_ADMIN_USERNAME: z.string().min(1).default(DEFAULT_CENTRAL_ADMIN_USERNAME),
  CENTRAL_ADMIN_PASSWORD: z.preprocess((value) => (value === '' ? undefined : value), z.string().optional()),
  CENTRAL_ADMIN_RECOVERY_OVERRIDE: envBoolean(booleanEnvValue.default(false)),
});

export type Env = z.infer<typeof EnvSchema>;

export function parseEnv(source: NodeJS.ProcessEnv): Env {
  return EnvSchema.parse(source);
}

const parsed = EnvSchema.safeParse(process.env);
if (!parsed.success) {
  console.error('Invalid environment variables');
  console.error(z.treeifyError(parsed.error));
  process.exit(1);
}

export const env = parsed.data;
