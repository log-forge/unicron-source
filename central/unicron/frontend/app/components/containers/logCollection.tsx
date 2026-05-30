import React from "react";

export type LogCollectionStatus = "ok" | "unavailable";

export type LogCollectionIssue = "inspect_failed" | "missing_log_path" | "unsupported_source";

export interface LogCollectionStateChangedEventData {
  host_id?: string;
  container_key?: string;
  name?: string;
  image?: string;
  container_name?: string;
  docker_container_id?: string;
  log_collection_status?: LogCollectionStatus;
  log_collection_issue?: LogCollectionIssue | null;
}

export interface LogCollectionContainerLike {
  identifier: string;
  container_key: string;
  name: string;
  host_id?: string;
  image_name?: string;
  log_collection_status?: LogCollectionStatus | null;
  log_collection_issue?: LogCollectionIssue | null;
}

function normalizeText(value?: string | null): string {
  return (value ?? "").trim();
}

export function getLogCollectionIssueLabel(issue?: LogCollectionIssue | null): string {
  switch (issue) {
    case "inspect_failed":
      return "inspect failed";
    case "missing_log_path":
      return "log path missing";
    case "unsupported_source":
      return "unsupported logging setup";
    default:
      return "logs unavailable";
  }
}

export function getLogCollectionIssueTitle(issue?: LogCollectionIssue | null): string {
  const label = getLogCollectionIssueLabel(issue);
  return label === "logs unavailable" ? label : `Logs unavailable: ${label}`;
}

export function shouldShowLogCollectionBadge(
  monitored: boolean,
  status?: LogCollectionStatus | null
): boolean {
  return monitored && status === "unavailable";
}

function matchesContainerIdentity(
  container: LogCollectionContainerLike,
  payload: LogCollectionStateChangedEventData
): boolean {
  const payloadContainerKey = normalizeText(payload.container_key);
  if (payloadContainerKey && payloadContainerKey === container.container_key) {
    return true;
  }

  const payloadHostId = normalizeText(payload.host_id);
  const payloadName = normalizeText(payload.container_name ?? payload.name);
  if (!payloadHostId || !payloadName) {
    return false;
  }

  const containerHostId = normalizeText(container.host_id) || "local";
  if (payloadHostId !== containerHostId) {
    return false;
  }

  const payloadImage = normalizeText(payload.image);
  const containerImage = normalizeText(container.image_name);
  if (payloadImage && payloadImage !== containerImage) {
    return false;
  }

  return payloadName === container.name;
}

export function mergeLogCollectionStateIntoContainers<T extends LogCollectionContainerLike>(
  containers: T[],
  payload: LogCollectionStateChangedEventData
): T[] {
  if (!containers.length) return containers;

  const nextStatus = payload.log_collection_status ?? "ok";
  const nextIssue = nextStatus === "unavailable" ? payload.log_collection_issue ?? null : null;

  let updated = false;
  const next = containers.map((container) => {
    if (!matchesContainerIdentity(container, payload)) {
      return container;
    }

    updated = true;
    return {
      ...container,
      log_collection_status: nextStatus,
      log_collection_issue: nextIssue,
    };
  });

  return updated ? next : containers;
}

export function LogCollectionBadge({
  monitored,
  status,
  issue,
  size = "md",
  className = "",
}: {
  monitored: boolean;
  status?: LogCollectionStatus | null;
  issue?: LogCollectionIssue | null;
  size?: "sm" | "md";
  className?: string;
}): React.ReactElement | null {
  if (!shouldShowLogCollectionBadge(monitored, status)) {
    return null;
  }

  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-0.5 text-xs";

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border border-amber-300 bg-amber-100 font-medium text-amber-900",
        "dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-200",
        sizeClasses,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      title={getLogCollectionIssueTitle(issue)}
    >
      Logs unavailable
    </span>
  );
}
