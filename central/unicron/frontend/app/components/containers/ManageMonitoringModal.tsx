/**
 * ManageMonitoringModal Component
 *
 * Bulk monitoring toggle modal for host containers.
 * Allows enabling/disabling monitoring for all containers on a host with batch processing.
 */

import { useState } from "react";
import { X } from "lucide-react";
import type { ContainerInfo } from "./ContainersTable";

// ============================================================================
// Types
// ============================================================================

export interface ManageMonitoringModalProps {
  /** Host ID for which containers are being managed */
  hostId: string;
  /** List of containers in this host */
  containers: ContainerInfo[];
  /** Current monitoring states for containers */
  monitoringStates: Record<string, boolean>;
  /** Close modal callback */
  onClose: () => void;
  /** Bulk toggle handler - processes in batches and returns results */
  onBulkToggle: (
    containerIds: string[],
    enable: boolean
  ) => Promise<{ succeeded: string[]; failed: string[] }>;
}

// ============================================================================
// Main Component
// ============================================================================

export const ManageMonitoringModal: React.FC<ManageMonitoringModalProps> = ({
  hostId,
  containers,
  monitoringStates,
  onClose,
  onBulkToggle,
}) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [progressText, setProgressText] = useState("");
  const [results, setResults] = useState<{
    succeeded: string[];
    failed: string[];
  } | null>(null);
  const [lastAction, setLastAction] = useState<"enable" | "disable" | null>(
    null
  );

  // Calculate monitoring stats
  const totalCount = containers.length;
  const monitoredCount = containers.filter(
    (c) => monitoringStates[c.identifier] ?? false
  ).length;

  // Status display
  let statusIcon = "";
  let statusText = "";
  let statusBgClass = "";

  if (monitoredCount === totalCount) {
    statusIcon = "🟢";
    statusText = `All ${totalCount} containers monitored`;
    statusBgClass = "bg-success/15 border-success/20";
  } else if (monitoredCount === 0) {
    statusIcon = "⚫";
    statusText = `None of ${totalCount} containers monitored`;
    statusBgClass = "bg-neutral/10 border-neutral/20";
  } else {
    statusIcon = "🟡";
    statusText = `${monitoredCount} of ${totalCount} containers monitored`;
    statusBgClass = "bg-warning/15 border-warning/20";
  }

  const handleBulkAction = async (enable: boolean) => {
    setIsProcessing(true);
    setResults(null);
    setLastAction(enable ? "enable" : "disable");
    setProgressText(
      `${enable ? "Enabling" : "Disabling"} monitoring for ${
        containers.length
      } containers...`
    );

    try {
      const containerIds = containers.map((c) => c.identifier);
      const result = await onBulkToggle(containerIds, enable);
      setResults(result);
      setProgressText("");
    } catch (error) {
      console.error("Bulk toggle failed:", error);
      setResults({
        succeeded: [],
        failed: containers.map((c) => c.identifier),
      });
      setProgressText("");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRetry = async () => {
    if (!results || !lastAction || results.failed.length === 0) return;

    setIsProcessing(true);
    setProgressText(`Retrying ${results.failed.length} failed containers...`);

    try {
      const retryResult = await onBulkToggle(
        results.failed,
        lastAction === "enable"
      );

      // Merge results: keep old successes, add new successes, update failures
      setResults({
        succeeded: [...results.succeeded, ...retryResult.succeeded],
        failed: retryResult.failed,
      });
      setProgressText("");
    } catch (error) {
      console.error("Retry failed:", error);
      setProgressText("");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-md"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl rounded-xl bg-background shadow-2xl border border-neutral/20 flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-neutral/20 p-lg flex-shrink-0">
          <h2 className="text-xl font-bold text-text pr-md">
            Manage Monitoring: {hostId}
          </h2>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-full hover:bg-neutral/10 transition-colors cursor-pointer flex-shrink-0"
            aria-label="Close"
          >
            <X className="h-5 w-5 text-neutral" />
          </button>
        </div>

        {/* Content - Scrollable */}
        <div className="p-lg overflow-y-auto flex-1">
          <div className="grid gap-lg lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] items-start">
            {/* Left Column: Actions and Results */}
            <div className="space-y-md">
              {/* Status Summary */}
              <div
                className={`flex items-center gap-md p-md rounded-lg border ${statusBgClass}`}
              >
                <span className="text-3xl flex-shrink-0">{statusIcon}</span>
                <span className="text-base font-semibold text-text">
                  {statusText}
                </span>
              </div>

              {/* Progress Indicator */}
              {progressText && (
                <div className="flex items-center gap-sm p-md rounded-lg bg-primary/10 border border-primary/20">
                  <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-base font-medium text-primary">
                    {progressText}
                  </span>
                </div>
              )}

              {/* Bulk Action Buttons */}
              <div className="flex gap-sm">
                <button
                  onClick={() => handleBulkAction(true)}
                  disabled={isProcessing || monitoredCount === totalCount}
                  className={`
                    flex-1 rounded-lg px-md py-sm text-base font-medium transition-all
                    ${
                      isProcessing || monitoredCount === totalCount
                        ? "opacity-50 cursor-not-allowed bg-success/20 text-success"
                        : "bg-success text-white hover:bg-success/90"
                    }
                  `}
                >
                  Enable All
                </button>
                <button
                  onClick={() => handleBulkAction(false)}
                  disabled={isProcessing || monitoredCount === 0}
                  className={`
                    flex-1 rounded-lg px-md py-sm text-base font-medium transition-all
                    ${
                      isProcessing || monitoredCount === 0
                        ? "opacity-50 cursor-not-allowed bg-error/20 text-error"
                        : "bg-error text-white hover:bg-error/90"
                    }
                  `}
                >
                  Disable All
                </button>
              </div>

              {/* Results Section */}
              {results && (
                <div className="space-y-sm border-t border-neutral/20 pt-md">
                  <h3 className="text-base font-bold text-text">Results</h3>

                  {/* Success summary */}
                  {results.succeeded.length > 0 &&
                    results.failed.length === 0 && (
                      <div className="flex items-start gap-sm p-md rounded-lg bg-success/10 border border-success/20">
                        <span className="text-success text-xl flex-shrink-0">
                          ✓
                        </span>
                        <span className="text-base font-medium text-success">
                          Successfully updated {results.succeeded.length}{" "}
                          container
                          {results.succeeded.length !== 1 ? "s" : ""}
                        </span>
                      </div>
                    )}

                  {/* Partial success/failure */}
                  {results.succeeded.length > 0 && results.failed.length > 0 && (
                    <div className="flex items-start gap-sm p-md rounded-lg bg-warning/10 border border-warning/20">
                      <span className="text-warning text-xl flex-shrink-0">
                        ⚠
                      </span>
                      <div className="text-base space-y-1">
                        <div className="font-medium text-warning">
                          Updated {results.succeeded.length} of{" "}
                          {results.succeeded.length + results.failed.length}{" "}
                          containers
                        </div>
                        <div className="text-sm text-warning/80">
                          {results.failed.length} failed
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Details list */}
                  {(results.succeeded.length > 0 ||
                    results.failed.length > 0) && (
                    <div className="max-h-48 overflow-y-auto space-y-2 p-md rounded-lg bg-neutral/5 border border-neutral/10">
                      {results.succeeded.map((id) => {
                        const container = containers.find(
                          (c) => c.identifier === id
                        );
                        return (
                          <div
                            key={id}
                            className="flex items-center gap-sm text-sm py-1"
                          >
                            <span className="text-success flex-shrink-0 text-base">
                              ✓
                            </span>
                            <span className="text-text break-all">
                              {container?.name || id}
                            </span>
                          </div>
                        );
                      })}
                      {results.failed.map((id) => {
                        const container = containers.find(
                          (c) => c.identifier === id
                        );
                        return (
                          <div
                            key={id}
                            className="flex items-center gap-sm text-sm py-1"
                          >
                            <span className="text-error flex-shrink-0 text-base">
                              ✗
                            </span>
                            <span className="text-text break-all flex-1">
                              {container?.name || id}
                            </span>
                            <span className="text-neutral text-xs flex-shrink-0">
                              (failed)
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Retry button for failures */}
                  {results.failed.length > 0 && (
                    <button
                      onClick={handleRetry}
                      disabled={isProcessing}
                      className={`
                        w-full rounded-lg px-md py-sm text-base font-medium transition-all
                        ${
                          isProcessing
                            ? "opacity-50 cursor-not-allowed bg-warning/20 text-warning"
                            : "bg-warning text-white hover:bg-warning/90"
                        }
                      `}
                    >
                      Retry {results.failed.length} failed container
                      {results.failed.length !== 1 ? "s" : ""}
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Right Column: Container List */}
            <div className="space-y-sm border border-neutral/20 rounded-lg p-md bg-neutral/5">
              <h3 className="text-base font-bold text-text">
                Containers on this host
              </h3>
              <div className="max-h-80 overflow-y-auto space-y-2 pr-1">
                {containers.map((container) => (
                  <div
                    key={container.identifier}
                    className="flex items-center justify-between gap-md py-2 px-sm rounded hover:bg-background/50 transition-colors"
                  >
                    <span className="text-sm text-text break-all flex-1">
                      {container.name}
                    </span>
                    <span
                      className={`px-sm py-1 rounded-full text-xs font-semibold flex-shrink-0 ${
                        monitoringStates[container.identifier] ?? false
                          ? "bg-success/20 text-success"
                          : "bg-neutral/20 text-neutral"
                      }`}
                    >
                      {monitoringStates[container.identifier] ?? false
                        ? "ON"
                        : "OFF"}
                    </span>
                  </div>
                ))}
                {containers.length === 0 && (
                  <div className="text-sm text-neutral italic py-lg text-center">
                    No containers on this host.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ManageMonitoringModal;
