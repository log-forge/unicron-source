import compression from 'compression';
import cors from 'cors';
import express from 'express';
import helmet from 'helmet';
import type { Auth } from 'better-auth';
import { toNodeHandler } from 'better-auth/node';
import { env } from './config/env';
import { requestIdHeader, requestLogger } from './logging/request-logger';
import { authRouteAllowlist } from './middleware/auth-route-allowlist';
import { errorHandler, notFoundHandler } from './middleware/error-handler';
import health, { readinessRouter } from './routes/health';
import v1 from './routes/v1';
import { isOriginAllowed } from './utils/cors/origin-allowlist';

export function createApp(auth: Auth<any>) {
  const app = express();

  app.enable('trust proxy');
  app.disable('x-powered-by');
  app.use(helmet({ crossOriginResourcePolicy: { policy: 'cross-origin' } }));

  app.use(
    cors(async (req, callback) => {
      const origin = req.header('origin');
      const allowed = origin ? await isOriginAllowed(origin) : true;
      callback(null, {
        origin: allowed,
        credentials: true,
        methods: ['GET', 'POST', 'OPTIONS'],
      });
    }),
  );

  app.use(requestLogger);
  app.use(requestIdHeader);

  app.all('/api/auth/{*splat}', authRouteAllowlist, toNodeHandler(auth as any));

  app.use('/api/v1', express.json({ limit: env.BODY_PARSER_JSON_LIMIT }));
  app.use('/api/v1', express.urlencoded({ extended: true, limit: env.BODY_PARSER_JSON_LIMIT }));
  if (env.COMPRESSION_ENABLED) app.use(compression());

  app.use('/healthz', health);
  app.use('/readyz', readinessRouter);
  app.use('/api/v1', v1);

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
