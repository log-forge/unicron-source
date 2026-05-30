import type { Log } from "~/utils/logCache";
import type { ILogRow } from "~/types/victoria/logs.types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function firstStringValue(
  record: Record<string, unknown>,
  keys: string[]
): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return null;
}

function parseEmbeddedLogEnvelope(
  raw: string
): Record<string, unknown> | null {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (!isRecord(parsed)) {
      return null;
    }
    return firstStringValue(parsed, ["log", "message", "body"]) ? parsed : null;
  } catch {
    return null;
  }
}

function resolveNestedMessage(value: unknown, depth = 0): string | null {
  if (depth > 2) {
    return null;
  }
  if (typeof value === "string") {
    const embedded = parseEmbeddedLogEnvelope(value);
    if (embedded) {
      const nested = firstStringValue(embedded, ["log", "message", "body"]);
      if (nested) {
        return resolveNestedMessage(nested, depth + 1) ?? nested.trimEnd();
      }
    }
    const trimmed = value.trimEnd();
    return trimmed ? trimmed : null;
  }
  if (isRecord(value)) {
    const nested = firstStringValue(value, ["log", "message", "body"]);
    if (nested) {
      return resolveNestedMessage(nested, depth + 1) ?? nested.trimEnd();
    }
  }
  return null;
}

export function normalizeLogMessage(
  message: unknown,
  msgJSON?: Record<string, unknown> | null
): string {
  return (
    resolveNestedMessage(msgJSON) ??
    resolveNestedMessage(message) ??
    ""
  );
}

export function convertLivePayloadToLog(
  message: unknown,
  timestamp: unknown,
  row?: Record<string, unknown>
): Log | null {
  const normalizedMessage = normalizeLogMessage(message, row?.msg_json as Record<string, unknown> | null);
  if (!normalizedMessage) {
    return null;
  }

  return {
    timeStamp:
      typeof timestamp === "string" && timestamp
        ? timestamp
        : new Date().toISOString(),
    message: normalizedMessage,
    severity: typeof row?.severity === "string" ? row.severity : null,
    stream: typeof row?.stream === "string" ? row.stream : null,
    container_key: typeof row?.container_key === "string" ? row.container_key : null,
    container_name: typeof row?.container_name === "string" ? row.container_name : null,
    docker_container_id:
      typeof row?.docker_container_id === "string" ? row.docker_container_id : null,
    herald_id: typeof row?.herald_id === "string" ? row.herald_id : null,
    herald_name: typeof row?.herald_name === "string" ? row.herald_name : null,
    service_name: typeof row?.service_name === "string" ? row.service_name : null,
    service_namespace:
      typeof row?.service_namespace === "string" ? row.service_namespace : null,
    msg_json:
      row?.msg_json != null && typeof row.msg_json === "object"
        ? (row.msg_json as Record<string, unknown>)
        : null,
  };
}

export function convertVictoriaRowToLog(row: ILogRow): Log {
  const timeStamp =
    row.time ??
    row._time ??
    (typeof row["msg_json.time"] === "string" ? row["msg_json.time"] : null) ??
    new Date().toISOString();
  const message =
    normalizeLogMessage(
      row.msg ?? row._msg ?? "",
      row.msg_json ? { ...row.msg_json } : null
    );
  return {
    timeStamp,
    message,
    severity: row.severity ?? null,
    stream: row.stream ?? null,
    container_key: row.container_key ?? null,
    container_name: row.container_name ?? null,
    docker_container_id: row.docker_container_id ?? null,
    herald_id: row.herald_id ?? null,
    herald_name: row.herald_name ?? null,
    service_name: row.service_name ?? null,
    service_namespace: row.service_namespace ?? null,
    msg_json: row.msg_json ? { ...row.msg_json } : null,
  };
}
