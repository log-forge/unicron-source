/**
 * Helpers for rendering alert stack counts consistently across the UI.
 *
 * Display contract:
 * - hide when count <= 1
 * - show x2..x9
 * - cap at x9+ for any count >= 10
 */

export function normalizeAlertCount(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 1;
  const normalized = Math.trunc(parsed);
  return normalized > 0 ? normalized : 1;
}

export function formatAlertStackLabel(value: unknown): string | null {
  const count = normalizeAlertCount(value);
  if (count <= 1) return null;
  if (count >= 10) return "x9+";
  return `x${count}`;
}

