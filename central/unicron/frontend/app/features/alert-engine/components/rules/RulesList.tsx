import React, { useState } from "react";
import Card from "../ui/Card";
import { Edit, Trash2, Play, Pause, Shield, ChevronDown, ChevronRight } from "lucide-react";
import type { AlertRule, MetricThresholdConfig } from "../../types";
import { generateRuleDescription } from "../../utils/ruleHelpers";
import { useContainers } from "../../hooks/useApi";

interface RulesListProps {
  rules: AlertRule[];
  onDelete: (id: string) => void;
  onEdit?: (rule: AlertRule) => void;
  onToggleEnabled?: (id: string, enabled: boolean) => void;
  summaryMode?: boolean; // NEW!
  canManageRules?: boolean;
  loading?: boolean;
}

interface RulesSummaryListProps {
  rules: AlertRule[];
  loading?: boolean;
}

function RulesSummaryList({ rules, loading = false }: RulesSummaryListProps) {
  return (
    <Card className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-xl font-bold text-text dark:text-text">Active Rules</h3>
        <div className="status-indicator status-success">
          {rules.length} active
        </div>
      </div>
      <div className="space-y-3">
        {loading && rules.length === 0 && (
          <>
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                key={`rules-loading-${index}`}
                className="flex items-center justify-between rounded-xl border border-divider bg-foreground/70 p-4 animate-pulse dark:border-divider dark:bg-foreground"
              >
                <div className="flex items-center space-x-3">
                  <div className="h-8 w-8 rounded-lg bg-neutral/20 dark:bg-alt-foreground" />
                  <div className="space-y-2">
                    <div className="h-3 w-28 rounded bg-neutral/20 dark:bg-alt-foreground" />
                    <div className="h-3 w-20 rounded bg-neutral/20 dark:bg-alt-foreground" />
                  </div>
                </div>
                <div className="h-5 w-14 rounded-full bg-neutral/20 dark:bg-alt-foreground" />
              </div>
            ))}
          </>
        )}

        {rules.slice(0, 5).map((rule, index) => (
          <div
            key={rule.id}
            className="group flex items-center justify-between rounded-xl border border-divider bg-gradient-to-r from-foreground/70 to-background p-4 transition-all duration-200 animate-slide-up hover:border-divider dark:border-divider dark:from-foreground dark:to-background dark:hover:border-divider"
            style={{animationDelay: `${index * 100}ms`}}
          >
            <div className="flex items-center space-x-3">
              <div className="mt-0.5 rounded-lg border border-info/30 bg-info/15 p-2 text-info transition-all duration-200 group-hover:brightness-105">
                <Shield className="w-4 h-4" />
              </div>
              <div>
                <p className="text-sm font-semibold text-text dark:text-text">{rule.name}</p>
                <p className="text-xs capitalize text-neutral-text dark:text-neutral-text">{rule.trigger_type.replace('_', ' ')}</p>
              </div>
            </div>
            <div className="status-indicator status-success text-xs">
              Active
            </div>
          </div>
        ))}

        {rules.length === 0 && (
          <div className="text-center py-8">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-success/30 bg-success/15 text-success">
              <Shield className="h-8 w-8" />
            </div>
            <h4 className="mb-1 text-sm font-semibold text-text dark:text-text">No active rules</h4>
            <p className="text-xs text-neutral-text dark:text-neutral-text">Enabled rules will appear here</p>
          </div>
        )}
      </div>
    </Card>
  );
}

type FullRulesListProps = Omit<RulesListProps, "summaryMode">;

function FullRulesList({
  rules,
  onDelete,
  onEdit,
  onToggleEnabled,
  canManageRules = true,
}: FullRulesListProps) {
  const { containers, groups } = useContainers();
  const [expandedRules, setExpandedRules] = useState<Set<string>>(new Set());

  const toggleExpanded = (ruleId: string) => {
    const newExpanded = new Set(expandedRules);
    if (newExpanded.has(ruleId)) {
      newExpanded.delete(ruleId);
    } else {
      newExpanded.add(ruleId);
    }
    setExpandedRules(newExpanded);
  };

  // Full rules grid for "Rules" tab
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-8">
      {rules.map((rule, index) => {
        const isTemplate = Boolean(rule.template_source);
        const toggleTitle = isTemplate
          ? (rule.enabled ? 'Disable template rule' : 'Enable template rule')
          : (rule.enabled ? 'Disable rule' : 'Enable rule');

        const toggleClassName = rule.enabled
          ? 'text-warning hover:bg-warning/10'
          : 'text-success hover:bg-success/10';


        return (
          <Card key={rule.id} className="p-6 card-hover group animate-scale-in" style={{animationDelay: `${index * 100}ms`}}>
          <div className="flex items-start justify-between mb-5">
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-bold text-text dark:text-text mb-3 truncate">{rule.name}</h3>
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <div className={`status-indicator ${
                    rule.trigger_type === 'keyword' ? 'status-info' :
                    rule.trigger_type === 'metric_threshold' ? 'status-warning' :
                    'status-success'
                  } text-xs`}>
                    {rule.trigger_type.replace('_', ' ')}
                  </div>
                  <div className={`status-indicator ${rule.enabled ? 'status-success' : 'status-error'} text-xs`}>
                    {rule.enabled ? 'Enabled' : 'Disabled'}
                  </div>
                </div>
                <div className="bg-foreground/70 dark:bg-alt-foreground/50 rounded-lg p-3 text-sm text-text dark:text-neutral-text">
                  {rule.trigger_type === 'keyword' && (
                    <span>
                      {Array.isArray(rule.trigger_value) ? 'Keywords' : 'Keyword'}:{' '}
                      <span className="font-mono bg-background dark:bg-foreground px-2 py-1 rounded text-xs">
                        "
                        {Array.isArray(rule.trigger_value)
                          ? rule.trigger_value.join('", "')
                          : (typeof rule.trigger_value === 'string' ? rule.trigger_value : '')}
                        "
                      </span>
                    </span>
                  )}
                  {rule.trigger_type === 'metric_threshold' && typeof rule.trigger_value === 'object' && rule.trigger_value && (
                    <span>
                      {(rule.trigger_value as MetricThresholdConfig).metric_type} {(rule.trigger_value as MetricThresholdConfig).operator} {(rule.trigger_value as MetricThresholdConfig).threshold}%
                    </span>
                  )}
                  {rule.trigger_type === 'container_event' && typeof rule.trigger_value === 'string' && (
                    <span>Event: <span className="font-medium">{rule.trigger_value}</span></span>
                  )}
                </div>
                {(rule.timeline_minutes || rule.timeline_count) && (
                  <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                    Timeline: {rule.timeline_count && `${rule.timeline_count} times`}
                    {rule.timeline_minutes && ` in ${rule.timeline_minutes} minutes`}
                  </div>
                )}
              </div>
            </div>
            {canManageRules && (
              <div className="flex space-x-1 ml-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <button
                  className={`p-2 rounded-lg transition-all duration-200 ${toggleClassName}`}
                  onClick={() => {
                    if (onToggleEnabled) {
                      onToggleEnabled(rule.id, !rule.enabled);
                    }
                  }}
                  title={toggleTitle}
                >
                  {rule.enabled ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                </button>
                <button
                  className={`p-2 rounded-lg transition-all duration-200 ${isTemplate ? 'cursor-not-allowed text-neutral-text' : 'text-neutral-text hover:bg-info/10 hover:text-info'}`}
                  onClick={() => {
                    if (isTemplate) return;
                    onEdit && onEdit(rule);
                  }}
                  disabled={isTemplate}
                  title={isTemplate ? 'Template rules can only change their enabled state. Convert to a custom rule to edit other settings.' : 'Edit rule'}
                >
                  <Edit className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onDelete(rule.id)}
                  className="p-2 text-neutral-text hover:bg-error/10 hover:text-error rounded-lg transition-all duration-200"
                  title="Delete rule"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          <div className="border-t border-divider/60 pt-4 mt-4">
            <div className="space-y-3">
              {/* Rule Description */}
              <div>
                <button
                  onClick={() => toggleExpanded(rule.id)}
                  className="flex items-center text-left w-full text-sm text-neutral-text hover:text-text transition-colors"
                >
                  {expandedRules.has(rule.id) ? (
                    <ChevronDown className="w-4 h-4 mr-2 flex-shrink-0" />
                  ) : (
                    <ChevronRight className="w-4 h-4 mr-2 flex-shrink-0" />
                  )}
                  <span className="flex-1">
                    {generateRuleDescription(rule, containers, groups)}
                  </span>
                </button>

                {/* Expanded Details */}
                {expandedRules.has(rule.id) && (
                  <div className="mt-3 ml-6 space-y-2 text-xs text-neutral-text dark:text-neutral-text">
                    {rule.actions && rule.actions.length > 0 ? (
                      <div>
                        <span className="font-medium">Actions:</span>
                        <ol className="list-decimal list-inside mt-1 space-y-1">
                          {rule.actions.map((action: any, index: number) => (
                            <li key={index}>
                              {action.type === 'notification' ? 'Send notification' :
                               action.type === 'restart_container' ? 'Restart container' :
                               action.type === 'kill_container' ? 'Kill container' : action.type}
                              {action.delay_seconds && index > 0 && ` (after ${action.delay_seconds}s)`}
                            </li>
                          ))}
                        </ol>
                      </div>
                    ) : (
                      <div>
                        <span className="font-medium">Action:</span> {rule.action_type.replace('_', ' ')}
                      </div>
                    )}

                    {rule.scope_type !== 'global' && (
                      <div>
                        <span className="font-medium">Scope:</span> {rule.scope_type === 'container' ? 'Specific containers' : 'Container groups'}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Status */}
              <div className="flex items-center justify-end">
                <div className={`flex items-center text-sm font-medium ${
                  rule.enabled ? 'text-success' : 'text-neutral-text'
                }`}>
                  {rule.enabled ? (
                    <>
                      <Play className="w-3 h-3 mr-1" />
                      Active
                    </>
                  ) : (
                    <>
                      <Pause className="w-3 h-3 mr-1" />
                      Paused
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Card>
      );
    })}
    </div>
  );
}

const RulesList: React.FC<RulesListProps> = (props) => {
  const { rules, onDelete, onEdit, onToggleEnabled, summaryMode = false, canManageRules, loading = false } = props;

  if (summaryMode) {
    return <RulesSummaryList rules={rules} loading={loading} />;
  }

  return (
    <FullRulesList
      rules={rules}
      onDelete={onDelete}
      onEdit={onEdit}
      onToggleEnabled={onToggleEnabled}
      canManageRules={canManageRules}
    />
  );
};

export default RulesList;
