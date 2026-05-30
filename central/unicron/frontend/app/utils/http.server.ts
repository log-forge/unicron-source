import https from "node:https";
import type { AxiosInstance } from "axios";
import type { Logger } from "pino";
import { env } from "./env.server";
import { createHttpClient as createBaseHttpClient, resolveEndpoint, type HttpBase } from "./http.shared";
import { log as serverLog } from "./logging/logger.server";

// Skip TLS verification for auth requests when SKIP_AUTH_TLS_VERIFY is set
// This is needed when the configured auth service uses a dev certificate not trusted by the container.
const authHttpsAgent = process.env.SKIP_AUTH_TLS_VERIFY === "true" ? new https.Agent({ rejectUnauthorized: false }) : undefined;

const FORWARDED_HEADERS = ["cookie", "authorization", "x-request-id", "referer"];

function attachForwardedHeaders(client: AxiosInstance, request?: Request, headers: string[] = FORWARDED_HEADERS) {
  if (!request) return;

  for (const headerName of headers) {
    const value = request.headers.get(headerName);
    if (value) {
      client.defaults.headers.common[headerName] = value;
    }
  }
}

export function createServerHttpClient({
  log = serverLog,
  base = "app",
  request,
  forwardedHeaders = FORWARDED_HEADERS,
  includeCookies = true,
}: {
  log?: Logger;
  base?: HttpBase | string | URL;
  request?: Request;
  forwardedHeaders?: string[];
  includeCookies?: boolean;
} = {}): AxiosInstance {
  const baseURL = resolveEndpoint(base, { app: env.APP_BASE_URL, auth: env.AUTH_BASE_URL });
  const client = createBaseHttpClient({ baseURL, log });

  // Use custom https agent for auth requests to skip TLS verification if configured
  if (base === "auth" && authHttpsAgent) {
    client.defaults.httpsAgent = authHttpsAgent;
  }

  const headersToForward = includeCookies ? forwardedHeaders : forwardedHeaders.filter((header) => header.toLowerCase() !== "cookie");
  attachForwardedHeaders(client, request, headersToForward);

  return client;
}
