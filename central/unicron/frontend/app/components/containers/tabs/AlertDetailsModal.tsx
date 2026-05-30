/**
 * Alert Details Modal
 *
 * Displays full details of a single alert including rule info,
 * container details, triggering condition, log message, and metadata.
 *
 * Phase 66-02: Extended to show trigger_value, threshold, count, and host_id
 * from the FiringAlert data passed through the IAlert adapter.
 */

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X, Clock, Tag, ExternalLink, CheckCircle } from "lucide-react";
import type { IAlert } from "~/utils/api/alerts";

// ============================================================================
// Types
// ============================================================================

interface AlertDetailsModalProps {
  alert: IAlert;
  containerName: string;
  onJumpToLogs: () => void;
  onAcknowledge: () => void;
  onClose: () => void;
  acknowledged?: boolean;
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch {
    return timestamp;
  }
}

function extractLogMessage(alert: IAlert): string | null {
  // Try various paths where log message might be stored
  const metadata = alert.metadata as Record<string, unknown> | undefined;
  const context = alert.context as Record<string, unknown> | undefined;

  if (metadata?.log_message) return String(metadata.log_message);
  if (context?.message) return String(context.message);
  if (context?.log_message) return String(context.log_message);
  if (alert.message) return alert.message;

  return null;
}

function extractTags(alert: IAlert): string[] {
  const metadata = alert.metadata as Record<string, unknown> | undefined;
  const context = alert.context as Record<string, unknown> | undefined;

  const tags: string[] = [];

  if (metadata?.tags && Array.isArray(metadata.tags)) {
    tags.push(...metadata.tags.map(String));
  }
  if (context?.tags && Array.isArray(context.tags)) {
    tags.push(...context.tags.map(String));
  }

  return tags;
}

// ============================================================================
// Sub-Components
// ============================================================================

interface DetailRowProps {
  label: string;
  value: string | number | null | undefined;
}

function DetailRow({ label, value }: DetailRowProps) {
  if (value === null || value === undefined) return null;

  return (
    <div className="min-w-0 rounded-lg border border-neutral/15 bg-neutral/5 p-sm">
      <span className="text-xs font-medium text-neutral">{label}</span>
      <span className="mt-1 block text-sm text-text break-words">
        {String(value)}
      </span>
    </div>
  );
}

interface SectionProps {
  title: string;
  children: React.ReactNode;
}

function Section({ title, children }: SectionProps) {
  return (
    <div className="space-y-sm">
      <h4 className="text-sm font-semibold text-text">{title}</h4>
      {children}
    </div>
  );
}

interface KeyValuePairProps {
  data: Record<string, unknown>;
}

function KeyValuePairs({ data }: KeyValuePairProps) {
  const entries = Object.entries(data).filter(
    ([, value]) => value !== null && value !== undefined
  );

  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border border-neutral/20 bg-neutral/5 p-sm">
      <div className="grid gap-2xs">
        {entries.map(([key, value]) => (
          <div
            key={key}
            className="grid gap-1 text-sm sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)] sm:gap-sm"
          >
            <span className="font-mono text-neutral break-words">{key}:</span>
            <span className="text-text break-words">
              {typeof value === "object" ? JSON.stringify(value) : String(value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function AlertDetailsModal({
  alert,
  containerName,
  onJumpToLogs,
  onAcknowledge,
  onClose,
  acknowledged = false,
}: AlertDetailsModalProps) {
  // Prevent background scroll while modal is open
  useEffect(() => {
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original || "";
    };
  }, []);

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  const metadata = (alert.metadata as Record<string, unknown>) ?? {};
  const context = (alert.context as Record<string, unknown>) ?? {};
  const logMessage = extractLogMessage(alert);
  const tags = extractTags(alert);

  const hasMetadata = Object.keys(metadata).length > 0;
  const hasContext = Object.keys(context).length > 0;

  const modalNode = (
    <div className="fixed inset-0 z-50 animate-fade-in">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="fixed inset-0 flex items-start justify-center overflow-y-auto p-sm pt-md pointer-events-none sm:items-center sm:p-md">
        <div className="relative w-full max-w-6xl xl:max-w-7xl max-h-[calc(100vh-2rem)] rounded-xl border border-neutral/20 bg-background shadow-2xl dark:bg-neutral-900 flex flex-col pointer-events-auto sm:max-h-[85vh]">
          {/* Header */}
          <div className="flex-shrink-0 border-b border-neutral/20 p-md">
            <div className="flex flex-col gap-sm sm:flex-row sm:items-start sm:justify-between">
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-bold text-text break-words">
                {alert.rule_name || "Uncategorized alert"}
              </h3>
              <div className="mt-2xs flex flex-wrap items-center gap-xs text-sm text-neutral">
                <Clock className="h-4 w-4" />
                <span>{formatTimestamp(alert.timestamp)}</span>
              </div>
              {tags.length > 0 && (
                <div className="flex items-center gap-xs mt-sm flex-wrap">
                  <Tag className="h-4 w-4 text-neutral" />
                  {tags.map((tag, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center rounded-full bg-primary/10 px-2xs py-4xs text-xs font-medium text-primary"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={onClose}
              className="self-start rounded-lg p-xs text-neutral transition-colors hover:bg-neutral/10 hover:text-text sm:self-auto"
            >
              <X className="h-5 w-5" />
            </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 space-y-md overflow-y-auto p-sm sm:p-md">
            {/* Rule Details */}
            <Section title="Rule Details">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-md">
                <DetailRow label="Rule ID" value={alert.rule_id} />
                <DetailRow label="Action Type" value={alert.action_type} />
                <DetailRow
                  label="Trigger Type"
                  value={metadata.trigger_type as string | undefined}
                />
                <DetailRow
                  label="Threshold"
                  value={alert.threshold ?? (metadata.threshold as string | undefined)}
                />
                <DetailRow
                  label="Trigger Value"
                  value={alert.trigger_value}
                />
                <DetailRow
                  label="Timeline"
                  value={
                    metadata.timeline_minutes
                      ? `${metadata.timeline_minutes} minutes`
                      : undefined
                  }
                />
                  <DetailRow label="Severity" value={alert.severity} />
                {alert.count != null && alert.count > 1 && (
                  <DetailRow label="Occurrences" value={`Fired ${alert.count} times`} />
                )}
              </div>
            </Section>

            {/* Container Details */}
            <Section title="Container Details">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-md">
                <DetailRow label="Name" value={containerName} />
                <DetailRow label="Identifier" value={alert.container} />
                <DetailRow label="Host ID" value={alert.host_id} />
                <DetailRow
                  label="Container Key"
                  value={
                    (context.container_key as string) ||
                    (metadata.container_key as string)
                  }
                />
                <DetailRow
                  label="Docker Container ID"
                  value={
                    (context.docker_container_id as string) ||
                    (metadata.docker_container_id as string)
                  }
                />
              </div>
            </Section>

            {/* Log Message */}
            {logMessage && (
              <Section title="Log Message">
                <pre className="rounded-lg border border-neutral/20 bg-neutral/5 p-sm text-sm font-mono text-text whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                  {logMessage}
                </pre>
              </Section>
            )}

            {/* Metadata */}
            {hasMetadata && (
              <Section title="Metadata">
                <KeyValuePairs data={metadata} />
              </Section>
            )}

            {/* Context */}
            {hasContext && (
              <Section title="Context">
                <KeyValuePairs data={context} />
              </Section>
            )}
          </div>

          {/* Footer / Actions */}
          <div className="flex-shrink-0 flex flex-wrap items-center justify-end gap-sm border-t border-neutral/20 p-md">
            <button
              onClick={onJumpToLogs}
              className="flex items-center gap-xs px-md py-sm text-sm font-medium text-primary hover:text-primary/80 transition-colors"
            >
              <ExternalLink className="h-4 w-4" />
              Open Logs
            </button>
            <button
              onClick={onAcknowledge}
              disabled={acknowledged}
              className={`flex items-center gap-xs px-md py-sm text-sm font-medium rounded-lg transition-colors ${
                acknowledged
                  ? "bg-neutral/10 text-neutral cursor-not-allowed"
                  : "bg-primary text-white hover:bg-primary/90"
              }`}
            >
              <CheckCircle className="h-4 w-4" />
              {acknowledged ? "Acknowledged" : "Acknowledge"}
            </button>
            <button
              onClick={onClose}
              className="px-md py-sm text-sm font-medium text-neutral hover:text-text transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modalNode, document.body);
}
