import "dotenv/config";
import process from "node:process";
import https from "node:https";
import express, { type Request, type Response, type NextFunction } from "express";
import type { ServerBuild } from "react-router";
import http, { type IncomingMessage, type ServerResponse } from "node:http";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { createRequestHandler } from "@react-router/express";
import pinoHttp from "pino-http";
import { randomUUID } from "node:crypto";
import { log } from "../app/utils/logging/logger.server";
import { env } from "../app/utils/env.server";
import axios from "axios";

const appRoot = resolve(process.cwd());

const isDev = env.VITE_NODE_ENV !== "production" && env.VITE_NODE_ENV !== "test";
const port = env.PORT;
const AUTH_PROXY_PREFIXES = ["/auth", "/unicron/auth"];
const SENSITIVE_QUERY_KEY = /(?:password|passwd|pwd|token|secret|credential|authorization|api[-_]?key|session|code)/iu;
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);
const authHttpsAgent = process.env.SKIP_AUTH_TLS_VERIFY === "true" ? new https.Agent({ rejectUnauthorized: false }) : undefined;

function sanitizeQueryValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => sanitizeQueryValue(item));
  if (!value || typeof value !== "object") return value;

  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, SENSITIVE_QUERY_KEY.test(key) ? "[REDACTED]" : sanitizeQueryValue(item)]),
  );
}

function sanitizeUrlForLog(rawUrl?: string | null): string {
  if (!rawUrl) return "";

  try {
    const parsed = new URL(rawUrl, "http://local.invalid");
    for (const key of Array.from(parsed.searchParams.keys())) {
      if (SENSITIVE_QUERY_KEY.test(key)) parsed.searchParams.set(key, "[REDACTED]");
    }

    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch (_err) {
    return rawUrl.replace(/([?&][^=&]*(?:password|passwd|pwd|token|secret|credential|authorization|api[-_]?key|session|code)[^=]*=)[^&]*/giu, "$1[REDACTED]");
  }
}

function getAuthBaseUrl(): string {
  return env.AUTH_BASE_URL.replace(/\/+$/u, "");
}

function getProxyTarget(originalUrl: string): string {
  const prefix = AUTH_PROXY_PREFIXES.find((candidate) => originalUrl === candidate || originalUrl.startsWith(`${candidate}/`));
  const upstreamPath = prefix ? originalUrl.slice(prefix.length) || "/" : originalUrl;
  return `${getAuthBaseUrl()}${upstreamPath.startsWith("/") ? upstreamPath : `/${upstreamPath}`}`;
}

function getForwardedHeaders(req: Request): Record<string, string | string[]> {
  const forwarded: Record<string, string | string[]> = {};

  for (const [key, value] of Object.entries(req.headers)) {
    const lower = key.toLowerCase();
    if (!value || lower === "host" || HOP_BY_HOP_HEADERS.has(lower)) continue;
    forwarded[key] = value;
  }

  const requestId = req.headers["x-request-id"];
  if (typeof requestId === "string") {
    forwarded["x-request-id"] = requestId;
  }

  return forwarded;
}

function rewriteAuthLocation(value: string, proxyPrefix: string): string {
  const authBase = getAuthBaseUrl();
  if (value === authBase) return proxyPrefix;
  if (value.startsWith(`${authBase}/`)) return `${proxyPrefix}${value.slice(authBase.length)}`;
  return value;
}

function setProxyResponseHeaders(res: Response, headers: Record<string, unknown>, proxyPrefix: string) {
  for (const [key, value] of Object.entries(headers)) {
    const lower = key.toLowerCase();
    if (HOP_BY_HOP_HEADERS.has(lower)) continue;
    if (typeof value === "undefined") continue;

    if (lower === "location" && typeof value === "string") {
      res.setHeader(key, rewriteAuthLocation(value, proxyPrefix));
      continue;
    }

    res.setHeader(key, value as number | string | readonly string[]);
  }
}

(async () => {
  const app = express();
  const server = http.createServer(app);

  app.disable("x-powered-by");
  if (env.TRUST_PROXY) app.set("trust proxy", true);

  // Access logs + level mapping
  app.use(
    pinoHttp({
      logger: log,
      serializers: {
        req(req: IncomingMessage) {
          const r = req as IncomingMessage & {
            id?: string | number;
            ip?: string;
            originalUrl?: string;
            query?: unknown;
            route?: { path?: string };
            socket?: IncomingMessage["socket"] & { remotePort?: number };
          };

          return {
            id: r.id,
            method: r.method,
            url: sanitizeUrlForLog(r.originalUrl ?? r.url),
            query: sanitizeQueryValue(r.query ?? {}),
            remoteAddress: r.ip || r.socket?.remoteAddress,
            remotePort: r.socket?.remotePort,
            userAgent: r.headers?.["user-agent"],
          };
        },
        res(res: ServerResponse) {
          return { statusCode: res.statusCode };
        },
      },
      customLogLevel: (_req: any, res: any, err: any) => {
        const status = typeof res?.statusCode === "number" ? res.statusCode : 0;
        if (status >= 500) return "error";
        if (status >= 400) return "warn";

        if (err instanceof Error) return "warn"; // could choose 'error' if desired

        return "info";
      },
      customSuccessMessage: (req, res) => `${req.method} ${sanitizeUrlForLog(req.url)} -> ${res.statusCode}`,
      customProps: (req) => ({ route: (req as any).route?.path }),
    }),
  );

  // Correlation ID
  app.use((req: Request, res: Response, next: NextFunction) => {
    const id = (req.headers["x-request-id"] as string) || randomUUID();
    res.setHeader("x-request-id", id);
    req.log = req.log.child({ request_id: id });
    next();
  });

  // Health
  app.get("/healthz", (_req, res) => res.json({ ok: true }));

  // Verify connectivity to the auth service by calling its /readyz endpoint.
  app.get("/readyz", async (req, res) => {
    const baseUrl = getAuthBaseUrl();
    const target = `${baseUrl}/readyz`;

    try {
      const { status = 0, data } = (await axios.get(target, { timeout: 2000, validateStatus: () => true, httpsAgent: authHttpsAgent })) as {
        status: number;
        data: any;
      };

      const ok = status >= 200 && status < 300 && (typeof data?.ok === "boolean" ? data.ok : true);
      req.log?.info({ auth: { target, status, ok } }, "auth /readyz check complete");

      return res.status(200).json({ ok, target, status, details: data });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      req.log?.error({ err: error, auth: { target } }, "auth /readyz check failed");

      return res.status(200).json({ ok: false, target, error: message });
    }
  });

  app.use(AUTH_PROXY_PREFIXES, async (req, res) => {
    const target = getProxyTarget(req.originalUrl);
    const method = req.method.toUpperCase();
    const proxyPrefix = req.baseUrl || AUTH_PROXY_PREFIXES[0];

    try {
      const upstream = await axios.request({
        method,
        url: target,
        headers: getForwardedHeaders(req),
        data: method === "GET" || method === "HEAD" ? undefined : req,
        responseType: "stream",
        validateStatus: () => true,
        maxRedirects: 0,
        httpsAgent: authHttpsAgent,
        decompress: false,
      });

      setProxyResponseHeaders(res, upstream.headers as Record<string, unknown>, proxyPrefix);
      res.status(upstream.status);

      if (method === "HEAD") {
        upstream.data.destroy?.();
        return res.end();
      }

      upstream.data.pipe(res);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      req.log?.error({ err: error, auth: { target } }, "auth proxy request failed");
      res.status(502).json({ ok: false, code: "auth_unreachable", error: message });
    }
  });

  if (isDev) {
    // Dev: Vite in middleware mode, React Router dev build
    const { createServer: createViteServer } = await import("vite");
    const vite = await createViteServer({
      // Use the project root (parent of server) so Vite picks up `vite.config.ts`
      // and plugins (notably @react-router/dev) which provide the virtual module
      // `virtual:react-router/server-build` used for SSR in dev mode.
      root: appRoot,
      server: { middlewareMode: true },
      appType: "custom",
    });

    app.use(vite.middlewares);

    app.all(
      "{*splat}",
      createRequestHandler({
        build: () => vite.ssrLoadModule("virtual:react-router/server-build") as Promise<ServerBuild>,
        getLoadContext(req, _res) {
          return { log: req.log };
        },
      }),
    );
  } else {
    // Prod: serve built client + use built server bundle
    const buildPath = resolve(appRoot, "build/server/index.js");
    const buildUrl = pathToFileURL(buildPath).href;
    const imported = (await import(buildUrl)) as unknown;
    const build =
      (imported as ServerBuild) ??
      (() => {
        throw new Error("Server build not found");
      });
    const publicPathValue = (build as { publicPath?: string })?.publicPath;
    const normalizePublicPath = (value?: string) => {
      if (!value) return "/";
      const trimmed = value.trim();
      if (!trimmed) return "/";
      const pathOnly = /^https?:\/\//iu.test(trimmed) ? new URL(trimmed).pathname : trimmed;
      const normalized = pathOnly.replace(/\/+$/u, "");
      return normalized ? (normalized.startsWith("/") ? normalized : `/${normalized}`) : "/";
    };
    const publicPath = normalizePublicPath(publicPathValue);
    const assetMountPath = publicPath === "/" ? "/assets" : `${publicPath}/assets`;
    const staticMountPath = publicPath === "/" ? "/" : publicPath;

    app.use(
      assetMountPath,
      express.static(resolve(appRoot, "build/client/assets"), {
        immutable: true,
        maxAge: "1y",
      }),
    );

    app.use(
      staticMountPath,
      express.static(resolve(appRoot, "build/client"), {
        maxAge: "1h",
      }),
    );

    app.all(
      "{*splat}",
      createRequestHandler({
        build,
        getLoadContext(req, _res) {
          return { log: req.log };
        },
      }),
    );
  }

  // Last-chance error logger
  app.use((err: any, req: Request, res: Response, next: NextFunction) => {
    // Attach the real error to the response so pino-http's onResFinished
    // will pick it up and log the original error (stack/message) instead
    // of creating a synthetic Error like 'failed with status code 500'.
    try {
      (res as any).err = err;
    } catch (e) {
      // ignore if we can't attach
    }

    req.log?.error({ err }, "unhandled");
    if (res.headersSent) return next(err);

    // If the error provides a status, use it; otherwise default to 500.
    const status = typeof err?.status === "number" ? err.status : 500;
    res.status(status).send("Internal Server Error");
  });

  server.listen(port, () => log.info({ port }, `listening on port ${port}`));
})().catch((err) => {
  log.fatal({ err }, "server startup failed");
  process.exit(1);
});
