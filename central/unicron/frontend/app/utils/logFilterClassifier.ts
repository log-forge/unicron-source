/**
 * Log Filter Classifier
 *
 * Classifies a user-supplied filter string into one of three viewer modes:
 *
 *  - fast-lane:  Plain substring → client-side filter on already-streamed rows
 *  - vtail:      LogsQL boolean filter → server-side Victoria /tail streaming
 *  - vquery:     LogsQL with pipes → server-side finite Victoria /query
 */

export type ViewerMode = "fast-lane" | "vtail" | "vquery";

// ---------------------------------------------------------------------------
// Heuristics
// ---------------------------------------------------------------------------

/**
 * Returns true when the text contains a `|` that is NOT inside double quotes.
 * Pipes signal LogsQL pipeline operators (stats, sort, uniq, …) which are
 * only supported by the finite query API, not by /tail.
 */
function hasPipeOutsideQuotes(text: string): boolean {
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"' && (i === 0 || text[i - 1] !== "\\")) {
      inQuotes = !inQuotes;
    } else if (ch === "|" && !inQuotes) {
      return true;
    }
  }
  return false;
}

const LOGSQL_FIELDS = [
  "severity",
  "stream",
  "container_key",
  "container_name",
  "docker_container_id",
  "herald_id",
  "herald_name",
  "service_name",
  "service_namespace",
  "msg",
  "time",
] as const;

const LOGSQL_BOOLEAN_RE = /(?:\bAND\b)|(?:\bOR\b)|(?:\bNOT\b)|(?:re\()|(?:seq\()|(?:exact\()|(?:~")/;

function isFieldBoundary(ch: string | undefined): boolean {
  return !ch || /\s|\(/u.test(ch);
}

function hasWhitelistedFieldFilter(text: string): boolean {
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"' && (i === 0 || text[i - 1] !== "\\")) {
      inQuotes = !inQuotes;
      continue;
    }
    if (inQuotes || !isFieldBoundary(text[i - 1])) {
      continue;
    }

    for (const field of LOGSQL_FIELDS) {
      if (!text.startsWith(field, i)) {
        continue;
      }
      const colonIndex = i + field.length;
      if (text[colonIndex] !== ":") {
        continue;
      }
      const value = text.slice(colonIndex + 1).trimStart();
      if (!value) {
        continue;
      }
      return true;
    }
  }

  return false;
}

function hasLogsQLSyntax(text: string): boolean {
  return hasWhitelistedFieldFilter(text) || LOGSQL_BOOLEAN_RE.test(text);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Classify a filter string into a viewer mode.
 *
 * Order matters — pipe detection runs first because a query like
 * `severity:error | stats count()` should be classified as vquery,
 * not vtail.
 */
export function classifyFilter(text: string): ViewerMode {
  const trimmed = text.trim();
  if (!trimmed) return "fast-lane";

  if (hasPipeOutsideQuotes(trimmed)) return "vquery";
  if (hasLogsQLSyntax(trimmed)) return "vtail";

  return "fast-lane";
}

export function resolveViewerMode(text: string, monitoringEnabled: boolean): ViewerMode {
  if (!monitoringEnabled) return "fast-lane";
  return classifyFilter(text);
}

/**
 * Split a vquery filter into its boolean `where` part and `pipes` part.
 * Everything before the first unquoted `|` is the where clause; everything
 * from the first `|` onward (inclusive) is the pipes string.
 *
 * Returns `{ where, pipes }`.  Either may be empty.
 */
export function splitFilterIntoParts(text: string): {
  where: string;
  pipes: string;
} {
  const trimmed = text.trim();
  let inQuotes = false;
  for (let i = 0; i < trimmed.length; i++) {
    const ch = trimmed[i];
    if (ch === '"' && (i === 0 || trimmed[i - 1] !== "\\")) {
      inQuotes = !inQuotes;
    } else if (ch === "|" && !inQuotes) {
      return {
        where: trimmed.slice(0, i).trim(),
        pipes: trimmed.slice(i).trim(),
      };
    }
  }
  return { where: trimmed, pipes: "" };
}
