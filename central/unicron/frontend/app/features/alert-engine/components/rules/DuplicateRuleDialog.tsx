import React from 'react';
import type { AlertRule } from '../../types';
import Button from '../ui/Button';
import { AlertTriangle, X, Eye, Settings, ArrowRight } from 'lucide-react';

/**
 * DuplicateRuleDialog - Shows comparison between existing and new rule when duplicate detected
 *
 * Data format compatibility:
 * - Accepts AlertRule from checkDuplicateRule API (full rule with id, name, scope_type, scope_targets)
 * - Handles both actions[] array and legacy action_type field
 * - Gracefully handles optional fields (timeline_minutes, timeline_count, tags)
 * - Works with both string and object trigger_value formats
 */
interface DuplicateRuleDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateAnyway: () => void;
  onModifySettings: () => void;
  existingRule: AlertRule;
  newRuleData: Partial<AlertRule>;
  templateName: string;
}

const DuplicateRuleDialog: React.FC<DuplicateRuleDialogProps> = ({
  isOpen,
  onClose,
  onCreateAnyway,
  onModifySettings,
  existingRule,
  newRuleData,
  templateName
}) => {
  if (!isOpen) return null;

  const formatTriggerValue = (rule: AlertRule | Partial<AlertRule>) => {
    if (Array.isArray(rule.trigger_value)) {
      return rule.trigger_value.join(', ');
    }
    if (typeof rule.trigger_value === 'string') {
      return rule.trigger_value;
    } else if (rule.trigger_value && typeof rule.trigger_value === 'object') {
      const config = rule.trigger_value as any;
      return `${config.metric_type?.toUpperCase()} ${config.operator} ${config.threshold}%`;
    }
    return 'Not set';
  };

  const formatActions = (rule: AlertRule | Partial<AlertRule>) => {
    if (rule.actions && rule.actions.length > 0) {
      return rule.actions.map(action => {
        switch (action.type) {
          case 'notification': return 'Send Notification';
          case 'restart_container': return 'Restart Container';
          case 'kill_container': return 'Kill Container';
          case 'stop_container': return 'Stop Container';
          case 'start_container': return 'Start Container';
          default: return action.type;
        }
      }).join(', ');
    } else if (rule.action_type) {
      switch (rule.action_type) {
        case 'notification': return 'Send Notification';
        case 'restart_container': return 'Restart Container';
        case 'kill_container': return 'Kill Container';
        case 'stop_container': return 'Stop Container';
        case 'start_container': return 'Start Container';
        default: return rule.action_type;
      }
    }
    return 'Not set';
  };

  const formatScope = (rule: AlertRule | Partial<AlertRule>) => {
    if (rule.scope_type === 'global') {
      return 'All Containers';
    } else if (rule.scope_type === 'container' && rule.scope_targets?.length) {
      return `Containers: ${rule.scope_targets.join(', ')}`;
    } else if (rule.scope_type === 'group' && rule.scope_targets?.length) {
      return `Groups: ${rule.scope_targets.join(', ')}`;
    }
    return 'Global';
  };

  const formatTimeline = (rule: AlertRule | Partial<AlertRule>) => {
    const parts = [];
    if (rule.timeline_count) parts.push(`${rule.timeline_count} times`);
    if (rule.timeline_minutes) parts.push(`within ${rule.timeline_minutes} min`);
    return parts.length > 0 ? parts.join(' ') : 'No timeline set';
  };

  const ComparisonRow: React.FC<{
    label: string;
    existing: string;
    new: string;
    isDifferent?: boolean
  }> = ({ label, existing, new: newValue, isDifferent = false }) => (
    <div className={`grid grid-cols-3 gap-4 border-b border-divider py-3 ${isDifferent ? 'bg-warning/10' : ''}`}>
      <div className="text-sm font-medium text-text">{label}</div>
      <div className="text-sm text-neutral-text">{existing}</div>
      <div className="text-sm text-neutral-text">{newValue}</div>
    </div>
  );

  // Check for differences
  const namesDifferent = existingRule.name !== newRuleData.name;
  const tagsDifferent = JSON.stringify(existingRule.tags?.sort()) !== JSON.stringify(newRuleData.tags?.sort());
  const scopeDifferent = existingRule.scope_type !== newRuleData.scope_type ||
    JSON.stringify(existingRule.scope_targets?.sort()) !== JSON.stringify(newRuleData.scope_targets?.sort());

  const hasVisibleDifferences = namesDifferent || tagsDifferent || scopeDifferent;

  return (
    <div className="fixed inset-0 bg-shadow/50 flex items-center justify-center z-50 p-4">
      <div className="bg-background rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-warning/30 bg-warning/10 p-6">
          <div className="flex items-center space-x-3">
            <AlertTriangle className="w-6 h-6 text-warning" />
            <div>
              <h2 className="text-lg font-semibold text-text">Duplicate Rule Detected</h2>
              <p className="text-sm text-neutral-text">
                A similar rule from template "{templateName}" already exists
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-text hover:text-neutral-text transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-200px)]">
          {/* Warning message */}
          <div className="mb-6 rounded-lg border border-warning/30 bg-warning/10 p-4">
            <div className="flex items-start space-x-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-warning" />
              <div className="text-sm text-warning">
                <p className="font-medium mb-1">This template creates a rule very similar to an existing one.</p>
                <p>
                  The core functionality (trigger conditions and actions) is identical.
                  {hasVisibleDifferences ? ' However, some settings like name, tags, or scope may differ.' : ' All settings appear to be identical.'}
                </p>
              </div>
            </div>
          </div>

          {/* Comparison table */}
          <div className="border border-divider rounded-lg overflow-hidden">
            <div className="grid grid-cols-3 gap-4 py-3 px-4 bg-foreground/70 border-b border-divider">
              <div className="text-sm font-semibold text-text">Setting</div>
              <div className="text-sm font-semibold text-text flex items-center">
                <Eye className="w-4 h-4 mr-2" />
                Existing Rule
              </div>
              <div className="text-sm font-semibold text-text flex items-center">
                <Settings className="w-4 h-4 mr-2" />
                New Rule (from Template)
              </div>
            </div>

            <div className="px-4">
              <ComparisonRow
                label="Name"
                existing={existingRule.name}
                new={newRuleData.name || templateName}
                isDifferent={namesDifferent}
              />

              <ComparisonRow
                label="Trigger Type"
                existing={existingRule.trigger_type.replace('_', ' ')}
                new={newRuleData.trigger_type?.replace('_', ' ') || 'Not set'}
              />

              <ComparisonRow
                label="Trigger Value"
                existing={formatTriggerValue(existingRule)}
                new={formatTriggerValue(newRuleData)}
              />

              <ComparisonRow
                label="Timeline"
                existing={formatTimeline(existingRule)}
                new={formatTimeline(newRuleData)}
              />

              <ComparisonRow
                label="Actions"
                existing={formatActions(existingRule)}
                new={formatActions(newRuleData)}
              />

              <ComparisonRow
                label="Scope"
                existing={formatScope(existingRule)}
                new={formatScope(newRuleData)}
                isDifferent={scopeDifferent}
              />

              <ComparisonRow
                label="Tags"
                existing={existingRule.tags?.join(', ') || 'None'}
                new={newRuleData.tags?.join(', ') || 'None'}
                isDifferent={tagsDifferent}
              />

              <ComparisonRow
                label="State"
                existing={existingRule.enabled ? 'Enabled' : 'Disabled'}
                new="Enabled (default for new rules)"
              />
            </div>
          </div>

          {hasVisibleDifferences && (
            <div className="mt-4 rounded-lg border border-info/30 bg-info/10 p-3">
              <p className="text-sm text-info">
                <span className="font-medium">Note:</span> Highlighted rows show differences between the existing and new rule.
                The core trigger and action logic remains identical.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-divider bg-foreground/70">
          <div className="text-sm text-neutral-text">
            What would you like to do?
          </div>
          <div className="flex space-x-3">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="secondary"
              onClick={onModifySettings}
              className="border-info/30 bg-info/10 text-info hover:bg-info/15"
            >
              <Settings className="w-4 h-4 mr-2" />
              Modify Settings
            </Button>
            <Button
              onClick={onCreateAnyway}
              className="bg-warning text-warning-950 hover:brightness-110"
            >
              <ArrowRight className="w-4 h-4 mr-2" />
              Create Anyway
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DuplicateRuleDialog;
