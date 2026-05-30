import http, { type Server } from 'node:http';
import { env } from './config/env';
import { connectMongoose, disconnectMongoose, getMongoDBClient, mongoosePing } from './db/mongoose';
import { createApp } from './app';
import { createAuth } from './lib/auth';
import { bootstrapLocalAdmin } from './lib/bootstrap-admin';
import { logger } from './logging/logger';
import { registerCheck, setDraining } from './utils/readiness';

async function main() {
  await connectMongoose();
  registerCheck('mongodb', mongoosePing);

  const auth = await createAuth({ mongoDb: await getMongoDBClient() });
  await bootstrapLocalAdmin();

  const app = createApp(auth);
  const server = http.createServer(app as unknown as (req: any, res: any) => void) as Server;

  server.requestTimeout = env.REQUEST_TIMEOUT_MS;
  server.headersTimeout = env.HEADERS_TIMEOUT_MS;
  server.keepAliveTimeout = env.KEEPALIVE_TIMEOUT_MS;

  server.listen(env.PORT, () => logger.info({ port: env.PORT }, 'Central auth listening'));

  const shutdown = (signal: NodeJS.Signals) => {
    logger.warn({ signal }, 'Shutdown signal');
    setDraining(true);

    setTimeout(() => {
      logger.info({ drainMs: env.SHUTDOWN_DRAIN_MS }, 'Drain window complete, closing server');
      server.close(async (err) => {
        if (err) logger.error({ err }, 'Error closing server');
        await disconnectMongoose();
        logger.info('HTTP server closed');
        process.exit(err ? 1 : 0);
      });
    }, env.SHUTDOWN_DRAIN_MS).unref();

    setTimeout(() => {
      logger.error('Forcing shutdown after drain window + 10s');
      process.exit(1);
    }, env.SHUTDOWN_DRAIN_MS + 10_000).unref();
  };

  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((err) => {
  logger.fatal({ err }, 'Fatal boot error');
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  const err = reason instanceof Error ? reason : new Error(typeof reason === 'string' ? reason : JSON.stringify(reason));
  logger.error({ err }, 'UnhandledRejection');
});

process.on('uncaughtException', (err) => {
  logger.fatal({ err }, 'UncaughtException');
  process.exit(1);
});
