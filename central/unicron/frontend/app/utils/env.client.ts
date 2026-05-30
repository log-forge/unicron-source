import { z } from "zod";
import { joinBaseAndPath } from "./env.shared";

const ClientEnvSchema = z.object({
  VITE_NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  VITE_API_BASE_URL: z.string().default("/api"),
  VITE_EXTERNAL_API_BASE_URL: z.string().optional(),
  VITE_SHOW_RQ_DEVTOOLS: z.coerce.boolean().default(false),
  VITE_BETTER_AUTH_URL: z.string().optional().default("http://localhost:3020"),
  VITE_AUTH_MODE: z.literal("cookie").default("cookie"),
  VITE_APP_BASE_URL: z.string().optional(),
  VITE_AUTH_BASE_URL: z.string().optional(),
  VITE_ALERT_ENGINE_API_BASE: z.string().optional(),
  VITE_NOTIFIER_API_BASE: z.string().optional(),
});

type RawClientEnv = z.infer<typeof ClientEnvSchema>;

const metaEnv = (import.meta as { env?: Record<string, unknown> }).env;
const rawEnv = (metaEnv as { env?: Record<string, unknown> } | undefined)?.env ?? metaEnv ?? {};
const parsed = ClientEnvSchema.parse(rawEnv);

const apiPath = parsed.VITE_API_BASE_URL ?? "/api";
const external = parsed.VITE_EXTERNAL_API_BASE_URL?.trim();
const computedAppBase = parsed.VITE_APP_BASE_URL ?? (external ? joinBaseAndPath(external, apiPath) : apiPath);
const computedAuthBase = parsed.VITE_AUTH_BASE_URL ?? parsed.VITE_BETTER_AUTH_URL ?? computedAppBase;

export type ClientEnv = RawClientEnv & { VITE_APP_BASE_URL: string; VITE_AUTH_BASE_URL: string };
export const clientEnv: ClientEnv = {
  ...parsed,
  VITE_APP_BASE_URL: computedAppBase,
  VITE_AUTH_BASE_URL: computedAuthBase,
};
