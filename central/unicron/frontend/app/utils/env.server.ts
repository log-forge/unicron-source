import { z } from "zod";
import { joinBaseAndPath } from "./env.shared";

const ServerEnvSchema = z.object({
  VITE_NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  VITE_API_BASE_URL: z.string().default("/api"),
  VITE_EXTERNAL_API_BASE_URL: z.string().optional(),
  VITE_SHOW_RQ_DEVTOOLS: z.coerce.boolean().default(false),
  VITE_BETTER_AUTH_URL: z.string().optional().default("http://localhost:3020"),
  INTERNAL_API_BASE_URL: z.string().optional(),
  UNICRON_CENTRAL_FQDN: z.string().optional(),
  NODE_EXTRA_CA_CERTS: z.string().optional(),
  APP_BASE_URL: z.string().optional(),
  AUTH_BASE_URL: z.string().optional(),
  VITE_APP_BASE_URL: z.string().optional(),
  VITE_AUTH_BASE_URL: z.string().optional(),
  VITE_AUTH_MODE: z.literal("cookie").default("cookie"),
  PORT: z.coerce.number().int().positive().default(5173),
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace", "silent"]).default("info"),
  APP_RELEASE: z.string().optional(),
  TRUST_PROXY: z.coerce.boolean().default(true),
  CSRF_COOKIE_SECRET: z.string().min(32),
  CSRF_SECRET: z.string().min(32),
});

type RawServerEnv = z.infer<typeof ServerEnvSchema>;

const parsed = ServerEnvSchema.parse(process.env as any);

const apiPath = parsed.VITE_API_BASE_URL ?? "/api";
const internal = parsed.INTERNAL_API_BASE_URL?.trim();
const fqdn = parsed.UNICRON_CENTRAL_FQDN?.trim();
const external = parsed.VITE_EXTERNAL_API_BASE_URL?.trim();

const computedAppBase =
  parsed.APP_BASE_URL ??
  parsed.VITE_APP_BASE_URL ??
  (internal
    ? joinBaseAndPath(internal, apiPath)
    : fqdn
      ? joinBaseAndPath(fqdn, apiPath)
      : external
        ? joinBaseAndPath(external, apiPath)
        : apiPath);

const computedAuthBase =
  parsed.AUTH_BASE_URL ??
  parsed.VITE_AUTH_BASE_URL ??
  parsed.VITE_BETTER_AUTH_URL ??
  computedAppBase;

export type ServerEnv = RawServerEnv & { APP_BASE_URL: string; AUTH_BASE_URL: string };
export const env: ServerEnv = {
  ...parsed,
  APP_BASE_URL: computedAppBase,
  AUTH_BASE_URL: computedAuthBase,
};
