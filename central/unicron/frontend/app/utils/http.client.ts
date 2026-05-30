import type { AxiosInstance, InternalAxiosRequestConfig } from "axios";
import type { Logger } from "pino";
import { clientEnv } from "./env.client";
import { createHttpClient as createBaseHttpClient, resolveEndpoint, type HttpBase } from "./http.shared";
import { clientLog } from "./logging/logger.client";
import { CSRF_FORM_DATA_KEY, CSRF_META_NAME } from "./csrf/constants";

function attachCsrfToken(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  // Attach CSRF token for mutating requests (Epic-style)
  if (typeof document === "undefined") return config;
  if (!config.method || config.method.toLowerCase() === "get" || !config.data) return config;

  const csrfToken = document.querySelector(`meta[name="${CSRF_META_NAME}"]`)?.getAttribute("content");

  if (!csrfToken) {
    console.warn("CSRF token not found. This request may fail validation.");
    return config;
  }

  if (config.data instanceof FormData) {
    // For FormData, append the token
    config.data.append(CSRF_FORM_DATA_KEY, csrfToken);
  } else if (typeof config.data === "string") {
    // For URL-encoded data
    const searchParams = new URLSearchParams(config.data as string);
    searchParams.append(CSRF_FORM_DATA_KEY, csrfToken);
    config.data = searchParams.toString();
  } else {
    // For JSON data
    config.data = {
      ...(config.data as Record<string, unknown>),
      [CSRF_FORM_DATA_KEY]: csrfToken,
    };
  }

  return config;
}

function attachAuthAndCsrf(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  return attachCsrfToken(config);
}

export function createHttpClient(log: Logger, base: HttpBase | string | URL = "app"): AxiosInstance {
  const baseURL = resolveEndpoint(base, {
    app: clientEnv.VITE_APP_BASE_URL,
    auth: clientEnv.VITE_AUTH_BASE_URL,
  });

  return createBaseHttpClient({
    baseURL,
    log,
    onRequest: attachAuthAndCsrf,
  });
}

// Default instances using the browser logger
export const httpApp = createHttpClient(clientLog, "app");
export const httpAuth = createHttpClient(clientLog, "auth");
