function normalizeBasename(value?: string | null): string {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return "";
  const noTrailingSlash = trimmed.replace(/\/+$/u, "");
  if (!noTrailingSlash || noTrailingSlash === "/") return "";
  return noTrailingSlash.startsWith("/") ? noTrailingSlash : `/${noTrailingSlash}`;
}

function stripBasename(path: string, basename: string): string {
  const normalizedBasename = normalizeBasename(basename);
  if (!normalizedBasename) return path;
  if (path === normalizedBasename) return "/";
  if (path.startsWith(`${normalizedBasename}/`)) return path.slice(normalizedBasename.length) || "/";
  return path;
}

function isAuthInternalPath(pathname: string): boolean {
  const normalizedPath = pathname.replace(/\/+$/u, "") || "/";
  return normalizedPath === "/auth" || normalizedPath.startsWith("/auth/");
}

export function normalizeReturnTo(value?: string | null, basename = import.meta.env.BASE_URL): string {
  const raw = (value ?? "").trim();
  if (!raw) return "/";
  if (/^(?:[a-z][a-z0-9+.-]*:|\/\/)/iu.test(raw)) return "/";

  const withLeadingSlash = raw.startsWith("/") ? raw : `/${raw}`;
  const [pathnameAndSearch, hash = ""] = withLeadingSlash.split("#", 2);
  const normalizedPath = stripBasename(pathnameAndSearch || "/", basename) || "/";
  const next = `${normalizedPath}${hash ? `#${hash}` : ""}`;

  if (!next.startsWith("/")) return "/";
  if (isAuthInternalPath(next.split(/[?#]/u, 1)[0] || "/")) return "/";
  return next;
}
