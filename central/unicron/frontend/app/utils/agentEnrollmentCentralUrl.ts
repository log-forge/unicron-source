const DEFAULT_CENTRAL_URL_FALLBACK = "https://unicron.central/unicron";
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

type LocationLike = Pick<Location, "hostname" | "origin" | "port">;

function currentLocation(): LocationLike | undefined {
  return typeof window === "undefined" ? undefined : window.location;
}

export function deriveDefaultCentralUrl(location: LocationLike | undefined = currentLocation()): string {
  if (!location) return DEFAULT_CENTRAL_URL_FALLBACK;
  if (!LOOPBACK_HOSTS.has(location.hostname)) return `${location.origin}/unicron`;

  const port = location.port ? `:${location.port}` : "";
  return `https://unicron.central${port}/unicron`;
}

export function normalizeCentralUrlInput(raw: string): string {
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  const withScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmed) ? trimmed : `https://${trimmed}`;
  const parsed = new URL(withScheme);
  const normalizedPath = parsed.pathname === "/" ? "/unicron" : parsed.pathname.replace(/\/+$/, "");
  return `${parsed.protocol}//${parsed.host}${normalizedPath}${parsed.search}${parsed.hash}`;
}
