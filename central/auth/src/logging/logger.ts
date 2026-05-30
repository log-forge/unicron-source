import pino from 'pino';
import { prettyFactory } from 'pino-pretty';
import { env } from '../config/env';

let hooks: pino.LoggerOptions['hooks'] | undefined;
const isVitest = Boolean(process.env.VITEST);
const isTestEnv = env.NODE_ENV === 'test' || process.env.NODE_ENV === 'test';

if (isVitest && isTestEnv) {
  const prettify = prettyFactory({ sync: true, colorize: true });
  hooks = {
    streamWrite: (s: string) => {
      console.log(prettify(s));
      return s;
    },
  };
}

const shouldPretty = env.LOG_PRETTY === true || env.NODE_ENV !== 'production';
const redactPaths = ['req.headers.authorization', 'req.headers.cookie', 'res.headers["set-cookie"]', '*.password', '*.token', '*.secret', '*.apiKey'];

let transport: pino.LoggerOptions['transport'] | undefined;
if (shouldPretty) {
  transport = {
    target: 'pino-pretty',
    options: {
      singleLine: true,
      translateTime: 'SYS:standard',
    },
  };
}

const loggerOptions: Record<string, any> = {
  level: env.LOG_LEVEL,
  base: { pid: process.pid, service: env.SERVICE_NAME, env: env.NODE_ENV, version: env.APP_VERSION },
  redact: { paths: redactPaths, remove: true },
  serializers: { err: pino.stdSerializers.err },
};

if (transport) loggerOptions.transport = transport;
if (hooks) loggerOptions.hooks = hooks;

export const logger = pino(loggerOptions);
