import { clientEnv } from "../utils/env.client";
import { normalizeBase, resolveEndpoint } from "../utils/env.shared";

const SOCKET_IO_PATH = "/socket.io";

function isAbsoluteUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function joinPaths(a: string, b: string) {
  const left = a.endsWith("/") ? a.slice(0, -1) : a;
  const right = b.startsWith("/") ? b.slice(1) : b;
  if (!left) return `/${right}`;
  return `${left}/${right}`;
}

export function resolveSocketEndpoint(): { url: string; path: string } {
  const base = resolveEndpoint<"app" | "auth">("app", {
    app: clientEnv?.VITE_APP_BASE_URL,
    auth: clientEnv?.VITE_AUTH_BASE_URL,
  });
  const normalizedBase = normalizeBase(base);

  if (isAbsoluteUrl(normalizedBase)) {
    const u = new URL(normalizedBase);
    const origin = `${u.protocol}//${u.host}`;
    const basePath = u.pathname && u.pathname !== "/" ? u.pathname : "";
    const path = joinPaths(basePath || "/", SOCKET_IO_PATH);
    return { url: origin, path };
  }

  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const basePath = normalizedBase && normalizedBase !== "/" ? normalizedBase : "";
  const path = joinPaths(basePath || "/", SOCKET_IO_PATH);
  return { url: origin, path };
}
