import pino from "pino";
import { env } from "../env.server";

const isProd = env.VITE_NODE_ENV === "production";

export const log = pino({
  level: env.LOG_LEVEL,
  base: { service: "unicron", env: env.VITE_NODE_ENV, release: env.APP_RELEASE },
  redact: {
    paths: [
      "req.headers.authorization",
      "req.headers.cookie",
      "req.headers.referer",
      "res.headers.set-cookie",
      "*.password",
      "*.passwd",
      "*.pwd",
      "*.token",
      "*.secret",
      "*.apiKey",
      "*.credential",
    ],
    censor: "[REDACTED]",
  },
  transport: isProd
    ? undefined
    : {
        target: "pino-pretty",
        options: { translateTime: "SYS:standard", singleLine: true, colorize: true },
      },
});

export type AppLogger = typeof log;
