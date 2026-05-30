export type ThemeTone = "success" | "warning" | "error" | "neutral" | "info";

const SUCCESS_STATUSES = [
  "healthy",
  "ok",
  "running",
  "sent",
  "allowed",
  "success",
] as const;

const WARNING_STATUSES = [
  "warning",
  "degraded",
  "pending",
  "retrying",
  "starting",
  "restarting",
  "paused",
  "acknowledged",
] as const;

const ERROR_STATUSES = [
  "critical",
  "error",
  "failed",
  "unhealthy",
  "firing",
  "triggered",
  "blocked",
  "stopped",
  "exited",
] as const;

const NEUTRAL_STATUSES = [
  "unknown",
  "disabled",
  "silenced",
  "resolved",
  "created",
  "group",
] as const;

const STATUS_TONES = {
  ...Object.fromEntries(SUCCESS_STATUSES.map((status) => [status, "success"])),
  ...Object.fromEntries(WARNING_STATUSES.map((status) => [status, "warning"])),
  ...Object.fromEntries(ERROR_STATUSES.map((status) => [status, "error"])),
  ...Object.fromEntries(NEUTRAL_STATUSES.map((status) => [status, "neutral"])),
} as Record<string, ThemeTone>;

const SEVERITY_TONES: Record<string, ThemeTone> = {
  critical: "error",
  warning: "warning",
  info: "info",
};

const TONE_BADGE_CLASSES: Record<ThemeTone, string> = {
  success: "bg-success/15 text-success-700 dark:text-success-300 border-success/30",
  warning: "bg-warning/15 text-warning-800 dark:text-warning-300 border-warning/30",
  error: "bg-error/15 text-error-700 dark:text-error-300 border-error/30",
  neutral: "bg-neutral/10 text-neutral-700 dark:text-neutral-300 border-neutral/30",
  info: "bg-info/15 text-info-700 dark:text-info-300 border-info/30",
};

const TONE_DOT_CLASSES: Record<ThemeTone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
  neutral: "bg-neutral/40",
  info: "bg-info",
};

const TONE_ICON_CLASSES: Record<ThemeTone, string> = {
  success: "text-success-700 dark:text-success-300",
  warning: "text-warning-800 dark:text-warning-300",
  error: "text-error-700 dark:text-error-300",
  neutral: "text-neutral-700 dark:text-neutral-300",
  info: "text-info-700 dark:text-info-300",
};

const TONE_SOFT_SURFACE_CLASSES: Record<ThemeTone, string> = {
  success: "bg-success/15 text-success-700 dark:text-success-300 border-success/30",
  warning: "bg-warning/15 text-warning-800 dark:text-warning-300 border-warning/30",
  error: "bg-error/15 text-error-700 dark:text-error-300 border-error/30",
  neutral: "bg-neutral/10 text-neutral-700 dark:text-neutral-300 border-neutral/30",
  info: "bg-info/15 text-info-700 dark:text-info-300 border-info/30",
};

function normalizeVocabularyValue(value?: string | null): string {
  return value?.trim().toLowerCase() ?? "";
}

export function getSeverityTone(value?: string): ThemeTone {
  const normalized = normalizeVocabularyValue(value);
  return SEVERITY_TONES[normalized] ?? "neutral";
}

export function getStatusTone(value?: string): ThemeTone {
  const normalized = normalizeVocabularyValue(value);
  return STATUS_TONES[normalized] ?? "neutral";
}

export function getToneBadgeClasses(tone: ThemeTone): string {
  return TONE_BADGE_CLASSES[tone];
}

export function getToneDotClasses(tone: ThemeTone): string {
  return TONE_DOT_CLASSES[tone];
}

export function getToneIconClasses(tone: ThemeTone): string {
  return TONE_ICON_CLASSES[tone];
}

export function getToneSoftSurfaceClasses(tone: ThemeTone): string {
  return TONE_SOFT_SURFACE_CLASSES[tone];
}

export function getSeverityBadgeClasses(value?: string): string {
  return getToneBadgeClasses(getSeverityTone(value));
}

export function getStatusBadgeClasses(value?: string): string {
  return getToneBadgeClasses(getStatusTone(value));
}

export function getStatusIconClasses(value?: string): string {
  return getToneIconClasses(getStatusTone(value));
}

export function getStatusSoftSurfaceClasses(value?: string): string {
  return getToneSoftSurfaceClasses(getStatusTone(value));
}
