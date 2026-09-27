import { betterAuth, type Auth, type BetterAuthOptions } from 'better-auth';
import { APIError, createAuthMiddleware } from 'better-auth/api';
import { mongodbAdapter } from 'better-auth/adapters/mongodb';
import { username } from 'better-auth/plugins/username';
import type { Db } from 'mongodb';
import { env } from '../config/env';
import { getMongoDBClient } from '../db/mongoose';
import { logger } from '../logging/logger';
import { UserModel } from '../models/user.model';
import { USERNAME_MAX, USERNAME_MIN, USERNAME_REGEX } from '../constants';
import { NewPasswordInput } from '../schemas/password.schemas';
import { normalizeUsername } from '../schemas/username.schemas';
import { baseAllowedOrigins, isOriginAllowed, normalizeOrigin } from '../utils/cors/origin-allowlist';
import { parseOrApiError } from '../utils/validation';

const betterAuthLogger: BetterAuthOptions['logger'] = {
  log: (maybeLevel: any, maybeMessage?: any, ...args: any[]) => {
    try {
      if (typeof maybeLevel === 'object' && maybeLevel !== null && 'level' in maybeLevel) {
        const { level, message, ...meta } = maybeLevel as { level?: string; message?: string; [key: string]: unknown };
        const pinoLevel = level === 'error' || level === 'warn' || level === 'info' || level === 'debug' ? level : 'info';
        const pinoMethod = ((logger as any)[pinoLevel] ?? logger.info).bind(logger);
        pinoMethod(meta, message);
        return;
      }

      const level = typeof maybeLevel === 'string' ? maybeLevel : 'info';
      const pinoLevel = level === 'error' || level === 'warn' || level === 'info' || level === 'debug' ? level : 'info';
      const meta = args.length > 0 && typeof args[0] === 'object' && args[0] !== null ? (args[0] as Record<string, unknown>) : {};
      const pinoMethod = ((logger as any)[pinoLevel] ?? logger.info).bind(logger);
      pinoMethod(meta, maybeMessage as string | undefined);
    } catch (err) {
      logger.error({ err }, 'Failed to forward Better Auth log');
    }
  },
};

let auth: Auth<any> | null = null;

export function getAuth() {
  if (!auth) throw new Error('Auth not initialized. Call createAuth() first.');
  return auth;
}

export interface CreateAuthOptions {
  mongoDb?: Db;
}

export async function createAuth(options: CreateAuthOptions = {}): Promise<Auth<any>> {
  const authDb = options.mongoDb ?? (await getMongoDBClient());

  const trustedOrigins: BetterAuthOptions['trustedOrigins'] = async (request) => {
    if (!request) return Array.from(baseAllowedOrigins).filter((origin) => origin !== '*');

    const candidate = request.headers.get('origin') ?? request.headers.get('referer');
    const normalized = candidate ? normalizeOrigin(candidate) : null;
    if (!normalized) return Array.from(baseAllowedOrigins).filter((origin) => origin !== '*');

    const allowed = await isOriginAllowed(normalized);
    if (!allowed) return Array.from(baseAllowedOrigins).filter((origin) => origin !== '*');

    return Array.from(new Set([normalized, ...Array.from(baseAllowedOrigins).filter((origin) => origin !== '*')]));
  };

  const config = {
    appName: 'Unicron Central Auth',
    baseURL: env.CENTRAL_AUTH_BASE_URL,
    basePath: '/api/auth',
    secret: env.CENTRAL_AUTH_SECRET,
    database: mongodbAdapter(authDb, { client: authDb.client }),
    logger: betterAuthLogger,
    onAPIError: {
      async onError(error) {
        if (!(error instanceof APIError)) return;

        const apiError = error as any;
        const currentBody = (apiError.body ?? {}) as any;
        const code = typeof currentBody.code === 'string' ? currentBody.code : 'INTERNAL_ERROR';
        const message =
          typeof currentBody.message === 'string' && currentBody.message.length > 0
            ? currentBody.message
            : typeof error.message === 'string' && error.message.length > 0
              ? error.message
              : 'Unexpected error';
        const issues = Array.isArray(currentBody.issues) ? currentBody.issues : undefined;
        const details = currentBody.details !== undefined ? currentBody.details : currentBody.cause !== undefined ? currentBody.cause : undefined;

        apiError.body = { code, message, ...(issues ? { issues } : {}), ...(details !== undefined ? { details } : {}) };
      },
    },
    user: {
      additionalFields: {
        requiresPasswordChange: { type: 'boolean', required: false, input: false },
      },
      changeEmail: {
        enabled: false,
      },
      deleteUser: {
        enabled: false,
      },
    },
    emailAndPassword: {
      enabled: true,
      autoSignIn: true,
      disableSignUp: true,
      minPasswordLength: 8,
      maxPasswordLength: 128,
      requireEmailVerification: false,
    },
    emailVerification: {
      sendOnSignUp: false,
    },
    session: {
      expiresIn: 60 * 60 * 24 * 14,
      updateAge: 60 * 60 * 24,
      freshAge: 60 * 5,
    },
    trustedOrigins,
    advanced: {
      useSecureCookies: env.NODE_ENV === 'production',
      defaultCookieAttributes: {
        sameSite: 'lax',
        secure: env.NODE_ENV === 'production',
        path: '/',
      },
      cookies: {
        session_token: {
          name: env.CENTRAL_AUTH_COOKIE_NAME,
        },
      },
    },
    hooks: {
      before: createAuthMiddleware(async (ctx) => {
        logger.debug({ path: ctx.path }, 'Auth request incoming');

        if (ctx.path === '/change-password') {
          parseOrApiError(NewPasswordInput, ctx.body, { message: 'Invalid password change input', code: 'INVALID_PASSWORD_CHANGE' });
        }
      }),
      after: createAuthMiddleware(async (ctx) => {
        if (ctx.path === '/change-password') {
          const userId = (ctx.context.session as any)?.user?.id ?? (ctx.context.session as any)?.session?.userId;
          if (userId) {
            await UserModel.updateOne({ _id: userId }, { $set: { requiresPasswordChange: false } });
          }
        }
      }),
    },
    plugins: [
      username({
        minUsernameLength: USERNAME_MIN,
        maxUsernameLength: USERNAME_MAX,
        usernameValidator: (value) => USERNAME_REGEX.test(value),
        usernameNormalization: normalizeUsername,
        validationOrder: { username: 'pre-normalization' },
      }),
    ],
  } satisfies BetterAuthOptions;

  auth = betterAuth(config) as Auth<any>;
  return auth;
}

export type CentralAuth = ReturnType<typeof getAuth>;
