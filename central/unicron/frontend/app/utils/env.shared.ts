export function normalizeBase(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const noTrailingSlash = trimmed.replace(/\/+$/u, "");
  if (!noTrailingSlash) return "";
  if (noTrailingSlash.startsWith("/")) return noTrailingSlash;
  if (!/^https?:\/\//iu.test(noTrailingSlash)) return `http://${noTrailingSlash}`;
  return noTrailingSlash;
}

export function ensureLeadingSlash(value: string | undefined | null): string {
  if (!value) return "";
  return value.startsWith("/") ? value : `/${value}`;
}

export function joinBaseAndPath(base: string, path: string): string {
  const normalizedBase = normalizeBase(base);
  const normalizedPath = ensureLeadingSlash(path);
  if (!normalizedBase) return normalizedPath || "/";
  if (!normalizedPath || normalizedPath === "/") return normalizedBase;
  if (normalizedBase.endsWith(normalizedPath)) return normalizedBase;
  return `${normalizedBase}${normalizedPath}`;
}

export function resolveEndpoint<T extends string>(base: T | string | URL, endpoints?: Record<T, string>): string {
  if (typeof base === "string" && endpoints && Object.prototype.hasOwnProperty.call(endpoints, base)) {
    return endpoints[base as T];
  }
  return typeof base === "string" ? base : base.toString();
}
