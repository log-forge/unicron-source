// Centralized date/time formatting utilities

export type DateTimeFormatOptions = Intl.DateTimeFormatOptions & {
  fallback?: string;
};

// Parse various timestamp inputs to a Date safely
export function toDate(input: string | number | Date): Date | null {
  try {
    if (input instanceof Date) return input;
    if (typeof input === 'number') return new Date(input);
    if (typeof input === 'string') return new Date(input);
    return null;
  } catch {
    return null;
  }
}

// Format a timestamp using the user's browser locale/timezone
export function formatLocalDateTime(
  input: string | number | Date,
  options: DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' }
): string {
  const d = toDate(input);
  if (!d || isNaN(d.getTime())) return options.fallback ?? 'Invalid date';
  return d.toLocaleString(undefined, options);
}

export function formatLocalDate(
  input: string | number | Date,
  options: DateTimeFormatOptions = { dateStyle: 'medium' }
): string {
  const d = toDate(input);
  if (!d || isNaN(d.getTime())) return options.fallback ?? 'Invalid date';
  return d.toLocaleDateString(undefined, options);
}

export function formatLocalTime(
  input: string | number | Date,
  options: DateTimeFormatOptions = { timeStyle: 'short' }
): string {
  const d = toDate(input);
  if (!d || isNaN(d.getTime())) return options.fallback ?? 'Invalid time';
  return d.toLocaleTimeString(undefined, options);
}
