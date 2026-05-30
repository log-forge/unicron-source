export type ApplianceUpdateStatus = {
  status: "ok" | "degraded" | "updating" | string;
  updater_health: "ok" | "degraded" | "unavailable" | string;
  auto_update_enabled: boolean;
  check_state?: "unknown" | "ok" | "check_failed" | "no_update_source" | string;
  in_progress: boolean;
  last_check?: string;
  last_apply?: string;
  last_error?: string;
  current_image?: string;
  current_image_id?: string;
  tracked_image?: string;
  latest_image?: string;
  latest_image_id?: string;
  update_available: boolean;
  rollback_image?: string;
  rollback_available: boolean;
};

export type ApplianceUpdateAction = "check" | "apply" | null;
export type ApplianceUpdateSummaryTone = "neutral" | "info" | "success" | "warning";

export type ApplianceUpdateSummary = {
  message: string;
  tone: ApplianceUpdateSummaryTone;
};

const NO_SOURCE_MESSAGE =
  "Unicron updates are unavailable because this container was started from a local image. Restart the appliance with the official Docker Hub image logforge/unicron:latest to receive updates.";

function statusCheckState(status: ApplianceUpdateStatus): string {
  return status.check_state || status.status || "unknown";
}

export function summarizeApplianceUpdateStatus({
  status,
  loading = false,
  action = null,
  actionError = null,
}: {
  status: ApplianceUpdateStatus | null;
  loading?: boolean;
  action?: ApplianceUpdateAction;
  actionError?: string | null;
}): ApplianceUpdateSummary {
  if (actionError) {
    return { message: actionError, tone: "warning" };
  }
  if (action === "check") {
    return { message: "Checking for updates...", tone: "info" };
  }
  if (action === "apply") {
    return { message: "Pulling new image...", tone: "info" };
  }
  if (loading) {
    return { message: "Loading update status", tone: "info" };
  }
  if (!status) {
    return { message: "Update status unavailable", tone: "warning" };
  }
  if (status.in_progress) {
    return { message: "Update job running", tone: "info" };
  }
  if (status.updater_health !== "ok") {
    return { message: status.last_error || "Appliance updater is unavailable.", tone: "warning" };
  }

  const checkState = statusCheckState(status);
  if (checkState === "no_update_source" || status.status === "no_update_source") {
    return { message: status.last_error || NO_SOURCE_MESSAGE, tone: "warning" };
  }
  if (checkState === "check_failed" || status.status === "check_failed") {
    return { message: status.last_error || "Update check failed.", tone: "warning" };
  }
  if (status.update_available) {
    return { message: "New image pulled; ready to update", tone: "info" };
  }
  if (checkState === "ok") {
    return { message: "Up to date", tone: "success" };
  }
  return { message: "Update status unknown", tone: "neutral" };
}
