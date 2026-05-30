/**
 * Active Rules Component
 *
 * Displays the 5 most recently updated active rules.
 */

import { CheckCircle2, Shield, XCircle } from "lucide-react";
import { useNavigate } from "react-router";
import type { RuleResponse } from "../../utils/api/alert-engine";
import { Button } from "../library/buttons/Button";

// ============================================================================
// Types
// ============================================================================

interface ActiveRulesProps {
  rules: RuleResponse[];
  isLoading?: boolean;
}

// ============================================================================
// Helper Functions
// ============================================================================

function getSeverityBadge(severity: string): { color: string; label: string } {
  switch (severity) {
    case "critical":
      return { color: "bg-error/10 text-error", label: "Critical" };
    case "warning":
      return { color: "bg-warning/10 text-warning", label: "Warning" };
    case "info":
    default:
      return { color: "bg-primary/10 text-primary", label: "Info" };
  }
}

function getTriggerTypeLabel(type: string): string {
  switch (type) {
    case "threshold":
      return "Threshold";
    case "keyword":
      return "Keyword";
    case "rate":
      return "Rate";
    case "absence":
      return "Absence";
    default:
      return type;
  }
}

// ============================================================================
// Skeleton Loader
// ============================================================================

function ActiveRulesSkeleton() {
  return (
    <div className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
      <div className="mb-md flex items-center justify-between">
        <div className="h-5 w-24 animate-pulse rounded bg-neutral/20" />
        <div className="h-8 w-24 animate-pulse rounded bg-neutral/20" />
      </div>
      <div className="space-y-sm">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="flex items-center justify-between rounded-lg border border-neutral/10 p-sm"
          >
            <div className="flex items-center gap-sm">
              <div className="h-8 w-8 animate-pulse rounded-lg bg-neutral/20" />
              <div className="space-y-2">
                <div className="h-4 w-32 animate-pulse rounded bg-neutral/20" />
                <div className="h-3 w-20 animate-pulse rounded bg-neutral/20" />
              </div>
            </div>
            <div className="h-5 w-16 animate-pulse rounded-full bg-neutral/20" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function ActiveRules({ rules, isLoading = false }: ActiveRulesProps) {
  const navigate = useNavigate();

  if (isLoading) {
    return <ActiveRulesSkeleton />;
  }

  // Sort by updated_at and take top 5
  const activeRules = [...rules]
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 5);

  return (
    <div className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
      <div className="mb-md flex items-center justify-between">
        <h3 className="text-base font-semibold text-text">Active Rules</h3>
        <Button
          variant="ghost"
          tone="primary"
          textSize="xs"
          padding="3xs"
          onPress={() => navigate("/alerting")}
        >
          Manage rules
        </Button>
      </div>

      {activeRules.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-lg text-center">
          <div className="mb-sm rounded-full bg-neutral/10 p-md">
            <Shield className="h-8 w-8 text-neutral" />
          </div>
          <p className="text-sm text-neutral">No rules configured</p>
          <p className="text-xs text-neutral/60">
            Create alert rules to start monitoring
          </p>
        </div>
      ) : (
        <div className="space-y-sm">
          {activeRules.map((rule) => {
            const severityBadge = getSeverityBadge(rule.severity);
            return (
              <div
                key={rule.id}
                className="group flex items-center justify-between rounded-lg border border-neutral/10 p-sm transition-colors hover:border-neutral/30 hover:bg-neutral/5"
              >
                <div className="flex items-center gap-sm">
                  <div
                    className={`rounded-lg p-2xs ${
                      rule.enabled
                        ? "bg-success/10 text-success"
                        : "bg-neutral/10 text-neutral"
                    }`}
                  >
                    {rule.enabled ? (
                      <CheckCircle2 className="h-4 w-4" />
                    ) : (
                      <XCircle className="h-4 w-4" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-text">
                      {rule.name}
                    </p>
                    <p className="text-xs text-neutral">
                      {getTriggerTypeLabel(rule.trigger_type)}
                    </p>
                  </div>
                </div>
                <span
                  className={`rounded-full px-2xs py-4xs text-xs font-medium ${severityBadge.color}`}
                >
                  {severityBadge.label}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default ActiveRules;
