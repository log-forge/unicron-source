import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import type { Logger } from "pino";

export type HttpBase = "app" | "auth";

type RequestHook = (config: InternalAxiosRequestConfig) => void | InternalAxiosRequestConfig | Promise<void | InternalAxiosRequestConfig>;
export { resolveEndpoint } from "./env.shared";

export function createHttpClient({ baseURL, log, onRequest }: { baseURL: string; log: Logger; onRequest?: RequestHook }): AxiosInstance {
  const client = axios.create({
    baseURL,
    withCredentials: true,
  });

  client.interceptors.request.use(
    async (config) => {
      if (onRequest) {
        const next = await onRequest(config);
        if (next) config = next;
      }

      log.debug({ method: config.method, url: config.url, baseURL: config.baseURL ?? baseURL }, "http:request");
      return config;
    },
    (error) => {
      log.error({ err: error }, "http:request_error");
      return Promise.reject(error);
    },
  );

  client.interceptors.response.use(
    (response) => {
      log.debug({ status: response.status, url: response.config.url }, "http:response");
      return response;
    },
    (error: AxiosError) => {
      const status = error.response?.status;
      const level = status && status >= 500 ? "error" : "warn";
      log[level]({ err: error, status, url: error.config?.url }, "http:response_error");
      return Promise.reject(error);
    },
  );

  return client;
}
