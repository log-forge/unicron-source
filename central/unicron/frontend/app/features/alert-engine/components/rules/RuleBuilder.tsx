import React, { useState, useMemo } from "react";
import Button from "../ui/Button";
import MultiSelect from "../ui/MultiSelect";
import TagInput from "../ui/TagInput";
import { Plus, Trash2, AlertTriangle, Target, Send, Info, Tag, ChevronDown, ChevronRight, HelpCircle, X } from "lucide-react";
import { useContainers } from "../../hooks/useApi";
import { apiService, type DryRunResult, type NotificationTargets } from "../../services/api";

interface RuleBuilderProps {
  onSave: (rule: any) => void;
  onCancel: () => void;
  initialRule?: any;
}

interface ActionConfig {
  delay_seconds?: number;
  channel_ids?: string[];
  group_ids?: string[];
  preset_ids?: string[];
}

interface Action {
  id: string;
  type: 'notification' | 'restart_container' | 'kill_container' | 'stop_container' | 'start_container' | 'run_script';
  config: ActionConfig;
}

interface RuleDryRunState {
  triggered: boolean;
  message: string;
  logsChecked: number;
  value?: string | null;
}

const buildContainerKey = (container: { name: string; host_id?: string }) => {
  const hostId = container.host_id || 'local';
  return `${hostId}:${container.name}`;
};

const formatContainerLabel = (container: { name: string; host_id?: string }) => {
  if (!container.host_id || container.host_id === 'local') {
    return container.name;
  }
  return `${container.name} (${container.host_id})`;
};

const RuleBuilder: React.FC<RuleBuilderProps> = ({ onSave, onCancel, initialRule = null }) => {
  const { containers, groups } = useContainers();
  const [isTestingNotification, setIsTestingNotification] = useState(false);
  const [testNotificationMessage, setTestNotificationMessage] = useState('');
  const [isTestingRule, setIsTestingRule] = useState(false);
  const [ruleDryRunState, setRuleDryRunState] = useState<RuleDryRunState | null>(null);
  const [ruleDryRunError, setRuleDryRunError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showScriptGuide, setShowScriptGuide] = useState(false);
  const [rule, setRule] = useState<any>(() => {
    const base = {
      name: '',
      trigger_type: 'keyword',
      trigger_value: '',
      timeline_minutes: initialRule ? undefined : 5,
      timeline_count: initialRule ? undefined : 3,
      severity: 'warning',
      action_type: 'notification',
      scope_type: 'herald',
      scope_targets: [],
      enabled: true,
      tags: [],
      ...initialRule
    };
    // If existing rule had global scope, treat as herald with no host (user must select)
    if (initialRule?.scope_type === 'global') {
      base.scope_type = 'herald';
      base.scope_targets = [];
    }
    return base;
  });

  // Derive initial selectedHost from initialRule
  const [selectedHost, setSelectedHost] = useState<string>(() => {
    if (!initialRule) return '';
    if (initialRule.scope_type === 'herald' && initialRule.scope_targets?.[0]) {
      return initialRule.scope_targets[0];
    }
    if (initialRule.scope_type === 'container' && initialRule.scope_targets?.[0]) {
      // Format is "hostId:containerName" — extract hostId
      const firstTarget = initialRule.scope_targets[0];
      const colonIndex = firstTarget.indexOf(':');
      return colonIndex > -1 ? firstTarget.substring(0, colonIndex) : '';
    }
    return '';
  });

  // Derive initial scopeMode from initialRule
  const [scopeMode, setScopeMode] = useState<'all' | 'specific'>(() => {
    if (initialRule?.scope_type === 'container') return 'specific';
    return 'all';
  });

  // Container search state for specific mode
  const [containerSearch, setContainerSearch] = useState('');

  const normalizeIdList = (rawValue: any): string[] => {
    if (rawValue === undefined || rawValue === null) {
      return [];
    }
    const values = Array.isArray(rawValue) ? rawValue : [rawValue];
    return values
      .map((value) => String(value ?? '').trim())
      .filter((value) => value.length > 0);
  };

  const normalizeActionConfig = (config: any): ActionConfig => {
    const normalized: ActionConfig = {};
    const base = (config && typeof config === 'object') ? config : {};

    if (typeof base.delay_seconds === 'number') {
      normalized.delay_seconds = base.delay_seconds;
    }

    normalized.channel_ids = normalizeIdList(base.channel_ids ?? base.channels ?? base.channelIds);
    normalized.group_ids = normalizeIdList(base.group_ids ?? base.groups ?? base.groupIds);
    normalized.preset_ids = normalizeIdList(base.preset_ids ?? base.presets ?? base.presetIds);

    return normalized;
  };

  const [actions, setActions] = useState<Action[]>(() => {
    // Initialize actions from initialRule if available, otherwise default
    if (initialRule?.actions && Array.isArray(initialRule.actions)) {
      return initialRule.actions.map((action: any, index: number) => ({
        id: (index + 1).toString(),
        type: action.type,
        config: normalizeActionConfig(action.config)
      }));
    }
    return [{
      id: '1',
      type: 'notification',
      config: { channel_ids: [], group_ids: [], preset_ids: [] }
    }];
  });
  const [notificationTargets, setNotificationTargets] = useState<NotificationTargets>({
    channels: [],
    groups: [],
    presets: []
  });
  const [targetsError, setTargetsError] = useState<string | null>(null);

  const notificationAction = useMemo(
    () => actions.find(action => action.type === 'notification'),
    [actions]
  );

  const notificationConfig = useMemo(() => {
    if (!notificationAction) {
      return null;
    }
    return normalizeActionConfig(notificationAction.config);
  }, [notificationAction, actions]);

  const selectedNotificationChannels = notificationConfig?.channel_ids ?? [];
  const selectedNotificationGroups = notificationConfig?.group_ids ?? [];
  const selectedNotificationPresets = notificationConfig?.preset_ids ?? [];

  const hasNotificationTargets = useMemo(() => {
    return (
      selectedNotificationChannels.length > 0 ||
      selectedNotificationGroups.length > 0 ||
      selectedNotificationPresets.length > 0
    );
  }, [selectedNotificationChannels, selectedNotificationGroups, selectedNotificationPresets]);

  const disableTestNotification =
    isTestingNotification || !notificationAction || !hasNotificationTargets;

  const testNotificationHelper = !notificationAction
    ? 'Add a notification action before sending a test.'
    : (!hasNotificationTargets
        ? 'Select at least one channel, group, or preset.'
        : null);

  const renderInfoTooltip = (messages: string[]) => {
    if (!messages.length) {
      return null;
    }
    const ariaLabel = messages.join(' ');
    return (
      <span
        className="relative group cursor-help"
        tabIndex={0}
        aria-label={ariaLabel}
      >
        <HelpCircle className="w-3 h-3 text-neutral-text" />
        <span className="pointer-events-none invisible absolute bottom-full left-1/2 mb-2 w-52 -translate-x-1/2 transform rounded-md border border-divider bg-alt-foreground px-3 py-2 text-left text-[11px] text-text opacity-0 shadow-lg transition-all duration-150 group-hover:visible group-hover:opacity-100 group-focus:visible group-focus:opacity-100">
          {messages.map((message, index) => (
            <span key={index} className="block">
              {message}
            </span>
          ))}
        </span>
      </span>
    );
  };

  React.useEffect(() => {
    let isMounted = true;
    apiService
      .getNotificationTargets()
      .then((data) => {
        if (!isMounted) return;
        setNotificationTargets({
          channels: data.channels || [],
          groups: data.groups || [],
          presets: data.presets || []
        });
        setTargetsError(null);
      })
      .catch((error) => {
        if (!isMounted) return;
        console.error('Failed to fetch notification targets:', error);
        setTargetsError(error instanceof Error ? error.message : 'Failed to load notification targets');
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const addAction = () => {
    const newAction: Action = {
      id: Date.now().toString(),
      type: 'restart_container',
      config: normalizeActionConfig({})
    };
    setActions([...actions, newAction]);
  };

  const removeAction = (id: string) => {
    if (actions.length > 1) {
      setActions(actions.filter(action => action.id !== id));
    }
  };

  const updateAction = (id: string, updates: Partial<Action>) => {
    setActions(actions.map(action => {
      if (action.id !== id) {
        return action;
      }
      const nextAction: Action = { ...action, ...updates };
      const baseConfig = normalizeActionConfig(nextAction.config);
      nextAction.config = baseConfig;
      return nextAction;
    }));
  };

  const updateActionConfig = (id: string, configUpdates: Partial<ActionConfig>) => {
    setActions(prevActions =>
      prevActions.map(action => {
        if (action.id !== id) {
          return action;
        }
        const existingConfig = normalizeActionConfig(action.config);
        const nextConfig: ActionConfig = { ...existingConfig };

        if ('delay_seconds' in configUpdates) {
          const delay = configUpdates.delay_seconds;
          if (typeof delay === 'number' && !Number.isNaN(delay)) {
            nextConfig.delay_seconds = delay;
          } else {
            delete nextConfig.delay_seconds;
          }
        }

        if (configUpdates.channel_ids !== undefined) {
          nextConfig.channel_ids = configUpdates.channel_ids ?? [];
        }

        if (configUpdates.group_ids !== undefined) {
          nextConfig.group_ids = configUpdates.group_ids ?? [];
        }

        if (configUpdates.preset_ids !== undefined) {
          nextConfig.preset_ids = configUpdates.preset_ids ?? [];
        }

        return { ...action, config: nextConfig };
      })
    );
  };

  // Check if there are notification actions
  const hasNotificationActions = useMemo(() => {
    return actions.some(action => action.type === 'notification');
  }, [actions]);

  const hostOptions = useMemo(() => {
    const uniqueHosts = new Map<string, { containerCount: number }>();
    containers.forEach(container => {
      const hostId = container.host_id || 'local';
      const existing = uniqueHosts.get(hostId);
      if (existing) {
        existing.containerCount += 1;
      } else {
        uniqueHosts.set(hostId, { containerCount: 1 });
      }
    });
    return Array.from(uniqueHosts.entries()).map(([hostId, data]) => ({
      value: hostId,
      label: hostId,
      subtitle: `${data.containerCount} container${data.containerCount !== 1 ? 's' : ''}`
    }));
  }, [containers]);

  const channelOptions = useMemo(() => (
    notificationTargets.channels.map((channel) => ({
      value: String(channel.id),
      label: channel.label ? channel.label : `Channel ${channel.id}`,
      subtitle: channel.enabled ? channel.type : `${channel.type || 'channel'} disabled`
    }))
  ), [notificationTargets.channels]);

  const groupOptions = useMemo(() => (
    notificationTargets.groups.map((group) => ({
      value: String(group.id),
      label: group.name || `Group ${group.id}`,
      subtitle: group.enabled ? 'Delivery bundle' : 'Group disabled',
    }))
  ), [notificationTargets.groups]);

  const presetOptions = useMemo(() => (
    notificationTargets.presets.map((preset) => ({
      value: String(preset.id),
      label: preset.label ? preset.label : `Preset ${preset.id}`,
      subtitle: preset.enabled ? preset.type : `${preset.type || 'preset'} disabled`,
    }))
  ), [notificationTargets.presets]);

  const channelLabelMap = useMemo(() => {
    const map = new Map<string, string>();
    notificationTargets.channels.forEach((channel) => {
      map.set(channel.id, channel.label ? channel.label : `Channel ${channel.id}`);
    });
    return map;
  }, [notificationTargets.channels]);

  const groupLabelMap = useMemo(() => {
    const map = new Map<string, string>();
    notificationTargets.groups.forEach((group) => {
      map.set(group.id, group.name || `Group ${group.id}`);
    });
    return map;
  }, [notificationTargets.groups]);

  const presetLabelMap = useMemo(() => {
    const map = new Map<string, string>();
    notificationTargets.presets.forEach((preset) => {
      map.set(preset.id, preset.label ? preset.label : `Preset ${preset.id}`);
    });
    return map;
  }, [notificationTargets.presets]);

  // Auto-convert script actions when scope is host-level (herald)
  // run_script requires a specific container target, so host-level scope can't use it
  React.useEffect(() => {
    if (rule.scope_type === 'herald') {
      const hasScriptActions = actions.some(action => action.type === 'run_script');
      if (hasScriptActions) {
        const updatedActions = actions.map(action =>
          action.type === 'run_script'
            ? { ...action, type: 'restart_container' as const }
            : action
        );
        setActions(updatedActions);
      }
    }
  }, [rule.scope_type, actions]);

  // Generate plain English translation
  const plainEnglishTranslation = useMemo(() => {
    let translation = `Rule: When `;

    // Trigger part
    switch (rule.trigger_type) {
      case 'keyword':
        if (Array.isArray(rule.trigger_value)) {
          const list = rule.trigger_value.filter((k: string) => k && k.trim()).join(', ');
          translation += `logs contain any of: ${list || '[keyword]'}`;
        } else {
          translation += `logs contain the keyword "${rule.trigger_value || '[keyword]'}"`;
        }
        break;
      case 'metric_threshold':
        const metric = rule.metric_type || 'CPU';
        const operator = rule.operator === '>' ? 'exceeds' : rule.operator === '<' ? 'falls below' : 'equals';
        const threshold = rule.threshold || '90';
        translation += `${metric.toUpperCase()} usage ${operator} ${threshold}%`;
        break;
      case 'container_event':
        const event = rule.trigger_value || 'restart';
        translation += `container ${event} occurs`;
        break;
      default:
        translation += `[trigger condition]`;
    }

    // Timeline part
    if (rule.timeline_count && rule.timeline_minutes) {
      translation += ` at least ${rule.timeline_count} times within ${rule.timeline_minutes} minutes`;
    } else if (rule.timeline_minutes && rule.trigger_type === 'metric_threshold') {
      translation += ` continuously for ${rule.timeline_minutes} minutes`;
    }

    // Scope part
    if (rule.scope_type === 'container' && rule.scope_targets.length > 0) {
      translation += ` for containers: ${rule.scope_targets.join(', ')}`;
    } else if (rule.scope_type === 'group' && rule.scope_targets.length > 0) {
      const groupNames = rule.scope_targets.map((id: string) => {
        const group = groups.find(g => g.groupId.toString() === id);
        return group ? (group.name || `Group ${group.groupId}`) : `Group ${id}`;
      });
      translation += ` for groups: ${groupNames.join(', ')}`;
    } else if (rule.scope_type === 'herald' && rule.scope_targets.length > 0) {
      translation += ` for all containers on host: ${rule.scope_targets[0]}`;
    }

    translation += `, then:`;

    // Actions part
    actions.forEach((action, index) => {
      translation += `\n  ${index + 1}. `;
      switch (action.type) {
        case 'notification':
          translation += `Send notification via Notifier service`;
          {
            const config = normalizeActionConfig(action.config);
            const channels = Array.isArray(config.channel_ids)
              ? config.channel_ids.filter((value) => value.trim().length > 0)
              : [];
            const groups = Array.isArray(config.group_ids)
              ? config.group_ids.filter((value) => value.trim().length > 0)
              : [];
            const presets = Array.isArray(config.preset_ids)
              ? config.preset_ids.filter((value) => value.trim().length > 0)
              : [];
            if (channels.length || groups.length || presets.length) {
              const parts: string[] = [];
              if (channels.length) {
                const labels = channels.map((id) => channelLabelMap.get(id) || `Channel ${id}`);
                parts.push(`channels: ${labels.join(', ')}`);
              }
              if (groups.length) {
                const labels = groups.map((id) => groupLabelMap.get(id) || `Group ${id}`);
                parts.push(`groups: ${labels.join(', ')}`);
              }
              if (presets.length) {
                const labels = presets.map((id) => presetLabelMap.get(id) || `Preset ${id}`);
                parts.push(`presets: ${labels.join(', ')}`);
              }
              translation += ` (targets ${parts.join('; ')})`;
            } else {
              translation += ` (no targets selected)`;
            }
          }
          break;
        case 'restart_container':
          translation += `Restart the container`;
          break;
        case 'stop_container':
          translation += `Stop the container`;
          break;
        case 'start_container':
          translation += `Start the container`;
          break;
        case 'kill_container':
          translation += `Kill the container`;
          break;
        case 'run_script':
          translation += `Run first script found in /logforge-scripts/ directory in the triggering container`;
          break;
      }
      if (action.config.delay_seconds && index > 0) {
        translation += ` (after ${action.config.delay_seconds} seconds)`;
      }
    });

    return translation;
  }, [rule, actions, channelLabelMap, groupLabelMap, presetLabelMap]);

  const handleTestNotification = async () => {
    setIsTestingNotification(true);
    setTestNotificationMessage('');

    try {
      if (!notificationAction) {
        setTestNotificationMessage('Add a notification action before sending a test.');
        return;
      }

      if (!hasNotificationTargets) {
        setTestNotificationMessage('Select at least one channel, group, or preset.');
        return;
      }

      const actionConfig = notificationConfig ?? { channel_ids: [], group_ids: [], preset_ids: [] };
      const channelIds = (actionConfig.channel_ids || []).filter((value) => value.trim().length > 0);
      const groupIds = (actionConfig.group_ids || []).filter((value) => value.trim().length > 0);
      const presetIds = (actionConfig.preset_ids || []).filter((value) => value.trim().length > 0);

      const response = await apiService.sendTestNotification(
        plainEnglishTranslation,
        channelIds.length ? channelIds : undefined,
        groupIds.length ? groupIds : undefined,
        presetIds.length ? presetIds : undefined,
        rule.severity || 'warning'
      );
      setTestNotificationMessage(`Test notification queued to notifier pipeline. Alert ID: ${response.alert_id}`);
    } catch (error) {
      setTestNotificationMessage('Failed to queue test notification. Check the Notifier service configuration.');
      console.error('Test notification failed:', error);
    } finally {
      setIsTestingNotification(false);
      // Clear message after 5 seconds
      setTimeout(() => setTestNotificationMessage(''), 5000);
    }
  };

  const buildProcessedRule = () => {
    const invalidNotification = actions.some((action) => {
      if (action.type !== 'notification') {
        return false;
      }
      const config = normalizeActionConfig(action.config);
      const hasTargets =
        (config.channel_ids && config.channel_ids.length > 0) ||
        (config.group_ids && config.group_ids.length > 0) ||
        (config.preset_ids && config.preset_ids.length > 0);
      return !hasTargets;
    });

    if (invalidNotification) {
      throw new Error('Notification actions require at least one target.');
    }

    // Scope validation: all scope types require targets (global is removed)
    if (!rule.scope_targets || rule.scope_targets.length === 0) {
      throw new Error('Select a host and scope for this rule.');
    }

    const processedRule: any = { ...rule };

    if (rule.trigger_type === 'metric_threshold') {
      processedRule.trigger_value = {
        metric_type: rule.metric_type || 'cpu',
        threshold: parseFloat(rule.threshold || '90'),
        operator: rule.operator || '>'
      };
      // Remove the temporary fields used for form state
      delete processedRule.metric_type;
      delete processedRule.threshold;
      delete processedRule.operator;
    }

    // Normalize keyword trigger_value: split comma-separated to list when >1
    if (processedRule.trigger_type === 'keyword' && typeof processedRule.trigger_value === 'string') {
      const parts = processedRule.trigger_value
        .split(',')
        .map((p: string) => p.trim())
        .filter((s: string) => s.length > 0);
      if (parts.length > 1) {
        processedRule.trigger_value = parts;
      } else if (parts.length === 1) {
        processedRule.trigger_value = parts[0];
      } else {
        processedRule.trigger_value = '';
      }
    }

    // Client-side limits mirroring backend for keyword triggers
    if (processedRule.trigger_type === 'keyword') {
      const arr = Array.isArray(processedRule.trigger_value)
        ? processedRule.trigger_value
        : (processedRule.trigger_value ? [processedRule.trigger_value] : []);
      // Enforce 1..100 char per keyword and <=20 items
      const tooLong = arr.find((k: string) => (k || '').trim().length > 100);
      if (tooLong) {
        throw new Error('Each keyword must be ≤ 100 characters');
      }
      if (arr.length > 20) {
        throw new Error('At most 20 keywords are allowed per rule');
      }

      if (!processedRule.timeline_minutes || processedRule.timeline_minutes < 1) {
        processedRule.timeline_minutes = 5;
      }
      if (!processedRule.timeline_count || processedRule.timeline_count < 1) {
        processedRule.timeline_count = 3;
      }
    }

    // Add chained actions to the rule (clean by removing frontend-only 'id' field)
    processedRule.actions = actions.map(action => {
      const config = normalizeActionConfig(action.config);
      return {
        type: action.type,
        config,
        ...(config.delay_seconds && { delay_seconds: config.delay_seconds })
      };
    });

    // Ensure required fields have default values
    if (!processedRule.scope_type) {
      processedRule.scope_type = 'herald';
    }
    if (!processedRule.scope_targets) {
      processedRule.scope_targets = [];
    }
    if (!processedRule.tags) {
      processedRule.tags = [];
    }

    // Clean up other undefined/empty fields, but preserve required ones
    const requiredFields = ['scope_type', 'scope_targets', 'tags', 'enabled'];
    Object.keys(processedRule).forEach(key => {
      if (!requiredFields.includes(key) && (processedRule[key] === undefined || processedRule[key] === '')) {
        delete processedRule[key];
      }
    });

    return processedRule;
  };

  const handleTestRule = async () => {
    setSaveError(null);
    setRuleDryRunError(null);
    setRuleDryRunState(null);
    setIsTestingRule(true);

    try {
      const processedRule = buildProcessedRule();
      const result: DryRunResult = await apiService.testRuleConfig(processedRule);
      setRuleDryRunState({
        triggered: Boolean(result.triggered),
        message: result.message || '',
        logsChecked: result.logs_checked || 0,
        value: result.value ?? null,
      });
    } catch (error) {
      setRuleDryRunError(error instanceof Error ? error.message : 'Failed to dry-run rule');
    } finally {
      setIsTestingRule(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Clear any previous errors
    setSaveError(null);
    setIsSaving(true);

    try {
      const processedRule = buildProcessedRule();
      console.log('🚀 Sending rule data:', JSON.stringify(processedRule, null, 2));
      await onSave(processedRule);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Failed to save rule');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-w-0">
      <form onSubmit={handleSubmit} className="min-w-0 space-y-8">
        {/* Main Content Area */}
        <div className="min-w-0 space-y-8">
          {/* Rule Name - Compact */}
          <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
            <div className="min-w-0">
              <label className="block text-sm font-bold text-text mb-2">Rule Name</label>
              <input
                type="text"
                value={rule.name}
                onChange={(e) => setRule({ ...rule, name: e.target.value })}
                className="input-modern"
                placeholder="e.g., High CPU Alert"
                required
                maxLength={48}
              />
              <div className="mt-1 text-xs text-neutral-text">{rule.name.length}/48</div>
            </div>
            <div className="min-w-0">
              <label className="block text-sm font-bold text-text mb-2">Severity</label>
              <select
                value={rule.severity || 'warning'}
                onChange={(e) => setRule({ ...rule, severity: e.target.value })}
                className="select-modern"
              >
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>
              <div className="mt-1 text-xs text-neutral-text">
                Controls how the alert is classified in the UI.
              </div>
            </div>
          </div>

          {/* Tags */}
          <div className="min-w-0">
            <label className="block text-sm font-bold text-text mb-2 flex items-center">
              <Tag className="w-4 h-4 mr-2 text-neutral-text" />
              Tags
            </label>
            <TagInput
              tags={rule.tags || []}
              onChange={(tags) => setRule({ ...rule, tags })}
              placeholder="Add tags to organize your rules..."
              predefinedTags={['Stability', 'Performance', 'Logs', 'Security', 'Metrics', 'Events', 'Notify', 'Restart', 'Stop', 'Kill', 'Start', 'Script']}
            />
          </div>

          {/* Trigger Configuration */}
          <div className="min-w-0 border border-divider dark:border-divider rounded-xl p-4 sm:p-6 lg:p-8 space-y-4">
            <h4 className="text-sm font-bold text-text flex items-center">
              <AlertTriangle className="w-4 h-4 mr-2 text-neutral-text" />
              Trigger Condition
            </h4>

            <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="min-w-0">
                <label className="block text-xs font-semibold text-neutral-text mb-2">Type</label>
                <select
                  value={rule.trigger_type}
                  onChange={(e) => {
                    const newTriggerType = e.target.value;
                    let newTriggerValue = rule.trigger_value;
                    let nextTimelineMinutes = rule.timeline_minutes;
                    let nextTimelineCount = rule.timeline_count;
                    // Set appropriate default trigger_value based on trigger_type
                    if (newTriggerType === 'container_event' && (!newTriggerValue || typeof newTriggerValue !== 'string' || newTriggerValue === '')) {
                      newTriggerValue = 'start';
                    } else if (newTriggerType === 'keyword' && (typeof newTriggerValue !== 'string' || newTriggerValue === '')) {
                      newTriggerValue = '';
                    }
                    if ((newTriggerType === 'keyword' || newTriggerType === 'container_event') && (!nextTimelineMinutes || nextTimelineMinutes < 1)) {
                      nextTimelineMinutes = 5;
                    }
                    if ((newTriggerType === 'keyword' || newTriggerType === 'container_event') && (!nextTimelineCount || nextTimelineCount < 1)) {
                      nextTimelineCount = 3;
                    }
                    setRule({
                      ...rule,
                      trigger_type: newTriggerType,
                      trigger_value: newTriggerValue,
                      timeline_minutes: nextTimelineMinutes,
                      timeline_count: nextTimelineCount,
                    });
                  }}
                  className="select-modern text-sm"
                >
                  <option value="keyword">Keyword in Logs</option>
                  <option value="metric_threshold">Metric Threshold</option>
                  <option value="container_event">Container Event</option>
                </select>
              </div>

              {/* Dynamic Trigger Configuration */}
              {rule.trigger_type === 'keyword' && (
                <div className="min-w-0 animate-slide-up">
                  <label className="block text-xs font-semibold text-neutral-text mb-2">Keywords (comma-separated)</label>
                  <input
                    type="text"
                    value={Array.isArray(rule.trigger_value) ? (rule.trigger_value as string[]).join(', ') : (typeof rule.trigger_value === 'string' ? rule.trigger_value : '')}
                    onChange={(e) => setRule({ ...rule, trigger_value: e.target.value })}
                    className="input-modern text-sm"
                    placeholder="ERROR, FATAL, Exception"
                    required
                  />
                </div>
              )}

              {rule.trigger_type === 'container_event' && (
                <div className="min-w-0 animate-slide-up">
                  <label className="block text-xs font-semibold text-neutral-text mb-2">Event Type</label>
                  <select
                    value={typeof rule.trigger_value === 'string' ? rule.trigger_value : 'start'}
                    onChange={(e) => setRule({ ...rule, trigger_value: e.target.value })}
                    className="select-modern text-sm"
                  >
                    <option value="start">Container Start</option>
                    <option value="stop">Container Stop</option>
                    <option value="restart">Container Restart</option>
                    <option value="kill">Container Kill</option>
                  </select>
                </div>
              )}
            </div>

            {/* Metric threshold fields */}
            {rule.trigger_type === 'metric_threshold' && (
              <div className="grid min-w-0 grid-cols-1 gap-3 animate-slide-up lg:grid-cols-3">
                <div className="min-w-0">
                  <label className="block text-xs font-semibold text-neutral-text mb-2">Metric</label>
                  <select
                    value={rule.metric_type || 'cpu'}
                    onChange={(e) => setRule({ ...rule, metric_type: e.target.value })}
                    className="select-modern text-sm"
                  >
                    <option value="cpu">CPU Usage</option>
                    <option value="memory">Memory Usage</option>
                    <option value="disk">Disk Usage</option>
                    <option value="network">Network Usage</option>
                  </select>
                </div>
                <div className="min-w-0">
                  <label className="block text-xs font-semibold text-neutral-text mb-2">Operator</label>
                  <select
                    value={rule.operator || '>'}
                    onChange={(e) => setRule({ ...rule, operator: e.target.value })}
                    className="select-modern text-sm"
                  >
                    <option value=">">Greater than</option>
                    <option value="<">Less than</option>
                    <option value="==">Equal to</option>
                  </select>
                </div>
                <div className="min-w-0">
                  <label className="block text-xs font-semibold text-neutral-text mb-2">Threshold (%)</label>
                  <input
                    type="number"
                    value={rule.threshold || '90'}
                    onChange={(e) => setRule({ ...rule, threshold: e.target.value })}
                    className="input-modern text-sm"
                    placeholder="90"
                    min="0"
                    max="100"
                    required
                  />
                </div>
              </div>
            )}

            {/* Timeline Settings */}
            <div className={`grid min-w-0 grid-cols-1 gap-3 ${rule.trigger_type === 'metric_threshold' ? 'lg:grid-cols-1' : 'lg:grid-cols-2'}`}>
              <div className="min-w-0">
                <label className="block text-xs font-semibold text-neutral-text mb-2">
                  {rule.trigger_type === 'metric_threshold' ? 'Sustain Duration (minutes)' : 'Time Window (minutes)'}
                </label>
                <input
                  type="number"
                  value={rule.timeline_minutes || ''}
                  onChange={(e) => setRule({ ...rule, timeline_minutes: e.target.value ? parseInt(e.target.value) : undefined })}
                  className="input-modern text-sm"
                  placeholder="5"
                  min="1"
                />
              </div>
              {rule.trigger_type !== 'metric_threshold' && (
                <div className="min-w-0">
                  <label className="block text-xs font-semibold text-neutral-text mb-2">Count Threshold</label>
                  <input
                    type="number"
                    value={rule.timeline_count || ''}
                    onChange={(e) => setRule({ ...rule, timeline_count: e.target.value ? parseInt(e.target.value) : undefined })}
                    className="input-modern text-sm"
                    placeholder="3"
                    min="1"
                  />
                </div>
              )}
            </div>
          </div>

          {/* Rule Scope */}
          <div className="min-w-0 border border-divider dark:border-divider rounded-xl p-4 sm:p-6 lg:p-8 space-y-4">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
              <h4 className="min-w-0 text-sm font-bold text-text flex items-center">
                <Target className="w-4 h-4 mr-2 text-neutral-text" />
                Rule Scope
              </h4>
              {(selectedHost || rule.scope_targets.length > 0) && (
                <button
                  type="button"
                  onClick={() => {
                    setSelectedHost('');
                    setScopeMode('all');
                    setContainerSearch('');
                    setRule({ ...rule, scope_type: 'herald', scope_targets: [] });
                  }}
                  className="text-xs text-neutral-text hover:text-text dark:hover:text-neutral-text transition-colors"
                >
                  Clear
                </button>
              )}
            </div>

            {/* Legacy group scope notice */}
            {rule.scope_type === 'group' ? (
              <div className="min-w-0 space-y-3">
                <div className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
                  This rule uses group scope (legacy). Edit scope to switch to host-based targeting.
                </div>
                <div className="min-w-0">
                  <label className="block text-xs font-semibold text-neutral-text mb-2">Current Groups</label>
                  <MultiSelect
                    options={groups.map(group => ({
                      value: group.groupId.toString(),
                      label: group.name || `Group ${group.groupId}`,
                      subtitle: group.monitoredContainerCount !== undefined
                        ? `${group.containerIds.length} containers (${group.monitoredContainerCount} monitored)`
                        : `${group.containerIds.length} containers`
                    }))}
                    value={rule.scope_targets}
                    onChange={(value) => setRule({ ...rule, scope_targets: value })}
                    placeholder="Choose groups..."
                    className="text-sm"
                  />
                </div>
              </div>
            ) : (
              <div className="min-w-0 space-y-4">
                {/* Host Selector */}
                <div className="min-w-0">
                  <label className="block text-xs font-semibold text-neutral-text dark:text-neutral-text mb-2">Host</label>
                  <select
                    value={selectedHost}
                    disabled={hostOptions.length === 0}
                    onChange={(e) => {
                      const newHost = e.target.value;
                      setSelectedHost(newHost);
                      setContainerSearch('');
                      // When host changes, clear selections and update rule
                      if (scopeMode === 'all' && newHost) {
                        setRule({ ...rule, scope_type: 'herald', scope_targets: [newHost] });
                      } else {
                        setRule({ ...rule, scope_type: scopeMode === 'all' ? 'herald' : 'container', scope_targets: [] });
                      }
                    }}
                    className="select-modern text-sm w-full"
                  >
                    <option value="">
                      {hostOptions.length === 0 ? 'No monitored containers' : 'Select a host...'}
                    </option>
                    {hostOptions.map(host => (
                      <option key={host.value} value={host.value}>
                        {host.label} ({host.subtitle})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Scope Mode Toggle */}
                {selectedHost && (
                  <div className="min-w-0 space-y-3">
                    <label className="block text-xs font-semibold text-neutral-text dark:text-neutral-text">Scope Mode</label>
                    <div className="flex min-w-0 rounded-lg border border-divider dark:border-divider overflow-hidden">
                      <button
                        type="button"
                        onClick={() => {
                          setScopeMode('all');
                          setContainerSearch('');
                          setRule({ ...rule, scope_type: 'herald', scope_targets: [selectedHost] });
                        }}
                        className={`flex-1 px-4 py-2 text-xs font-semibold transition-colors ${
                          scopeMode === 'all'
                            ? 'bg-info text-info-950'
                            : 'bg-background dark:bg-foreground text-neutral-text dark:text-neutral-text hover:bg-foreground/70 dark:hover:bg-alt-foreground'
                        }`}
                      >
                        All containers
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setScopeMode('specific');
                          setRule({ ...rule, scope_type: 'container', scope_targets: [] });
                        }}
                        className={`flex-1 px-4 py-2 text-xs font-semibold transition-colors border-l border-divider dark:border-divider ${
                          scopeMode === 'specific'
                            ? 'bg-info text-info-950'
                            : 'bg-background dark:bg-foreground text-neutral-text dark:text-neutral-text hover:bg-foreground/70 dark:hover:bg-alt-foreground'
                        }`}
                      >
                        Specific containers
                      </button>
                    </div>

                    {/* Selection display: "All on: [host]" badge for host-level */}
                    {scopeMode === 'all' && (
                      <div className="flex min-w-0 items-center gap-2">
                        <div className="flex min-w-0 max-w-full items-center gap-1.5 rounded-lg border border-info/30 bg-info/15 px-3 py-1.5 text-sm text-info">
                          <span className="min-w-0 truncate">All on: {selectedHost}</span>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedHost('');
                              setScopeMode('all');
                              setRule({ ...rule, scope_type: 'herald', scope_targets: [] });
                            }}
                            className="flex-shrink-0 rounded p-0.5 transition-colors hover:bg-info/20"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Container list for specific mode */}
                    {scopeMode === 'specific' && (
                      <div className="min-w-0 space-y-2">
                        <input
                          type="text"
                          placeholder="Search containers..."
                          value={containerSearch}
                          onChange={(e) => setContainerSearch(e.target.value)}
                          className="input-modern text-sm w-full"
                        />
                        <MultiSelect
                          options={containers
                            .filter(c => (c.host_id || 'local') === selectedHost)
                            .filter(c => !containerSearch || c.name.toLowerCase().includes(containerSearch.toLowerCase()))
                            .map(container => ({
                              value: buildContainerKey(container),
                              label: container.name,
                              subtitle: container.identifier
                            }))}
                          value={rule.scope_targets}
                          onChange={(value) => setRule({ ...rule, scope_targets: value })}
                          placeholder="Choose containers..."
                          className="text-sm"
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Warning when no targets */}
            {rule.scope_targets.length === 0 && (
              <div className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
                {!selectedHost
                  ? 'Select a host to define the rule scope.'
                  : scopeMode === 'specific'
                    ? 'Select at least one container for this rule.'
                    : 'No targets selected. Rule will not trigger.'
                }
              </div>
            )}
          </div>

          {/* Chained Actions */}
          <div className="min-w-0 border border-divider dark:border-divider rounded-xl p-4 sm:p-6 lg:p-8 space-y-4">
            <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <h4 className="min-w-0 text-sm font-bold text-text">Actions Chain</h4>
              <div className="flex min-w-0 flex-wrap items-start gap-2 lg:justify-end">
                {hasNotificationActions && (
                  <div className="flex min-w-0 max-w-full flex-col">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleTestNotification}
                      disabled={disableTestNotification}
                      className="h-auto min-h-9 max-w-full px-2 py-1 text-xs bg-success/10 text-success border-success/30 hover:bg-success/10 disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                      <Send className="w-3 h-3 mr-1" />
                      {isTestingNotification ? 'Queueing...' : 'Send Test Notification'}
                    </Button>
                    {testNotificationHelper && (
                      <span className="mt-1 max-w-full text-xs text-warning break-words">{testNotificationHelper}</span>
                    )}
                  </div>
                )}
                {!hasNotificationActions && (
                  <span className="max-w-full self-center pr-2 text-xs text-neutral-text break-words">Add a notification action to enable test sends.</span>
                )}
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={addAction}
                  className="h-auto min-h-9 px-2 py-1 text-xs"
                >
                  <Plus className="w-3 h-3 mr-1" />
                  Add Action
                </Button>
              </div>
            </div>

            {/* Test notification message */}
            {testNotificationMessage && (
              <div className="animate-slide-up bg-foreground/70 dark:bg-foreground/50 border border-divider dark:border-divider rounded-lg p-3">
                <p className="text-xs text-text dark:text-neutral-text">{testNotificationMessage}</p>
              </div>
            )}

            {actions.map((action, index) => {
              const normalizedConfig = normalizeActionConfig(action.config);
              const actionChannelIds = Array.isArray(normalizedConfig.channel_ids) ? normalizedConfig.channel_ids : [];
              const actionGroupIds = Array.isArray(normalizedConfig.group_ids) ? normalizedConfig.group_ids : [];
              const actionPresetIds = Array.isArray(normalizedConfig.preset_ids) ? normalizedConfig.preset_ids : [];
              const actionHasTargets =
                actionChannelIds.length > 0 || actionGroupIds.length > 0 || actionPresetIds.length > 0;

              const channelMessages: string[] = [];
              const groupMessages: string[] = [];
              const presetMessages: string[] = [];

              if (action.type === 'notification') {
                const disabledChannels = actionChannelIds.filter((id) => {
                  const channel = notificationTargets.channels.find((entry) => entry.id === id);
                  return channel ? !channel.enabled : false;
                });
                if (disabledChannels.length > 0) {
                  const labels = disabledChannels.map((id) => channelLabelMap.get(id) || `Channel ${id}`);
                  channelMessages.push(`Disabled channels: ${labels.join(', ')}`);
                }

                const disabledGroups = actionGroupIds.filter((id) => {
                  const group = notificationTargets.groups.find((entry) => entry.id === id);
                  return group ? !group.enabled : false;
                });
                if (disabledGroups.length > 0) {
                  const labels = disabledGroups.map((id) => groupLabelMap.get(id) || `Group ${id}`);
                  groupMessages.push(`Disabled groups: ${labels.join(', ')}`);
                }

                const emptyTargets = actionGroupIds.filter((id) => {
                  const group = notificationTargets.groups.find((entry) => entry.id === id);
                  const targets = group?.targets;
                  const channelIds = targets?.channel_ids || [];
                  const presetIds = targets?.preset_ids || [];
                  return group ? channelIds.length === 0 && presetIds.length === 0 : false;
                });
                if (emptyTargets.length > 0) {
                  const labels = emptyTargets.map((id) => groupLabelMap.get(id) || `Group ${id}`);
                  groupMessages.push(`No targets configured: ${labels.join(', ')}`);
                }

                const disabledPresets = actionPresetIds.filter((id) => {
                  const preset = notificationTargets.presets.find((entry) => entry.id === id);
                  return preset ? !preset.enabled : false;
                });
                if (disabledPresets.length > 0) {
                  const labels = disabledPresets.map((id) => presetLabelMap.get(id) || `Preset ${id}`);
                  presetMessages.push(`Disabled presets: ${labels.join(', ')}`);
                }
              }
              return (
                <div key={action.id} className="min-w-0 bg-foreground/70 dark:bg-foreground/50 rounded-lg p-4 border border-divider dark:border-divider">
                  <div className="mb-3 flex min-w-0 flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-neutral-text dark:text-neutral-text">Action {index + 1}</span>
                    {actions.length > 1 && (
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => removeAction(action.id)}
                        className="text-error hover:text-error text-xs py-1 px-2"
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    )}
                  </div>

                  <div className="grid min-w-0 grid-cols-1 gap-3 lg:grid-cols-2">
                    <div className="min-w-0">
                      <label className="block text-xs font-semibold text-neutral-text mb-2">Type</label>
                      <div className="relative">
                        <select
                          value={action.type}
                          onChange={(e) => updateAction(action.id, { type: e.target.value as any })}
                          className="select-modern text-sm pr-8"
                        >
                          <option value="restart_container">Restart Container</option>
                          <option value="start_container">Start Container</option>
                          <option value="stop_container">Stop Container</option>
                          <option value="kill_container">Kill Container</option>
                          <option
                            value="run_script"
                            disabled={rule.scope_type === 'herald'}
                            title={rule.scope_type === 'herald' ? 'Requires specific container scope' : ''}
                          >
                            Run Script
                          </option>
                          <option value="notification">Send Notification</option>
                        </select>
                        {action.type === 'notification' && (
                          <div className="absolute right-2 top-1/2 transform -translate-y-1/2 pointer-events-none">
                            <div className="group relative">
                              <Info className="w-3 h-3 text-neutral-text cursor-help pointer-events-auto" />
                              <div className="invisible absolute bottom-full right-0 z-10 mb-2 w-64 rounded-lg border border-divider bg-alt-foreground px-3 py-2 text-xs text-text opacity-0 transition-all duration-200 group-hover:visible group-hover:opacity-100">
                                Sent via the Notifier service to selected channels, groups, and presets
                                <div className="absolute top-full right-4 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-divider"></div>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    {index > 0 && (
                      <div className="min-w-0">
                        <label className="block text-xs font-semibold text-neutral-text mb-2">Delay (seconds)</label>
                        <input
                          type="number"
                          value={action.config?.delay_seconds ?? ''}
                          onChange={(e) => {
                            const value = e.target.value ? parseInt(e.target.value, 10) : undefined;
                            updateActionConfig(action.id, { delay_seconds: value });
                          }}
                          className="input-modern text-sm"
                          placeholder="30"
                          min="0"
                        />
                      </div>
                    )}
                  </div>

                  {action.type === 'notification' && (
                    <div className="min-w-0 space-y-2">
                      <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-2">
                        <div className="min-w-0">
                          <div className="mb-2 flex min-w-0 items-center gap-1">
                            <span className="text-xs font-semibold text-neutral-text">Channels</span>
                            {renderInfoTooltip(channelMessages)}
                          </div>
                          <MultiSelect
                            options={channelOptions}
                            value={actionChannelIds.map(String)}
                            onChange={(selected) => updateActionConfig(action.id, { channel_ids: normalizeIdList(selected) })}
                            placeholder={channelOptions.length ? "Select channels" : "No channels available"}
                            className="w-full"
                          />
                        </div>
                        <div className="min-w-0">
                          <div className="mb-2 flex min-w-0 items-center gap-1">
                            <span className="text-xs font-semibold text-neutral-text">Groups</span>
                            {renderInfoTooltip(groupMessages)}
                          </div>
                          <MultiSelect
                            options={groupOptions}
                            value={actionGroupIds.map(String)}
                            onChange={(selected) => updateActionConfig(action.id, { group_ids: normalizeIdList(selected) })}
                            placeholder={groupOptions.length ? "Select groups" : "No groups available"}
                            className="w-full"
                          />
                        </div>
                        <div className="min-w-0">
                          <div className="mb-2 flex min-w-0 items-center gap-1">
                            <span className="text-xs font-semibold text-neutral-text">Presets</span>
                            {renderInfoTooltip(presetMessages)}
                          </div>
                          <MultiSelect
                            options={presetOptions}
                            value={actionPresetIds.map(String)}
                            onChange={(selected) => updateActionConfig(action.id, { preset_ids: normalizeIdList(selected) })}
                            placeholder={presetOptions.length ? "Select presets" : "No presets available"}
                            className="w-full"
                          />
                        </div>
                      </div>
                      {!actionHasTargets && (
                        <p className="text-[11px] text-neutral-text">Select at least one channel, group, or preset.</p>
                      )}
                      {targetsError && (
                        <p className="text-[11px] text-error">{targetsError}</p>
                      )}
                    </div>
                  )}

                  {/* Script Configuration */}
                  {action.type === 'run_script' && (
                    <div className="mt-3 min-w-0 p-3 bg-info/10 dark:bg-foreground rounded-lg border border-primary/30 dark:border-divider">
                      <h5 className="text-xs font-semibold text-info dark:text-info mb-2">Script Configuration</h5>

                      {/* Execution Behavior Info */}
                      <div className="mb-3 min-w-0 p-2 bg-info/10 dark:bg-alt-foreground/50 rounded border border-primary/30 dark:border-divider">
                        <p className="text-xs font-semibold text-info dark:text-info mb-1">ℹ️ Script Execution Behavior:</p>
                        <p className="text-xs text-info dark:text-neutral-text">
                          Scripts run only on the container that triggers the alert, not on other containers in scope.
                        </p>
                        <p className="text-xs text-success dark:text-success mt-1 font-medium">
                          ✅ The first script found (alphabetically) in /logforge-scripts/ will be executed.
                        </p>
                      </div>

                      {/* Collapsible Setup Guide */}
                      <div>
                        <button
                          type="button"
                          onClick={() => setShowScriptGuide(!showScriptGuide)}
                          className="flex items-center gap-1 text-xs font-semibold text-info dark:text-info hover:text-info dark:hover:text-info transition-colors"
                        >
                          {showScriptGuide ? (
                            <ChevronDown className="w-3 h-3" />
                          ) : (
                            <ChevronRight className="w-3 h-3" />
                          )}
                          Requirements & Setup Guide
                        </button>

                        {showScriptGuide && (
                          <div className="mt-2 min-w-0 text-xs text-info dark:text-neutral-text bg-info/10 dark:bg-alt-foreground/50 rounded p-2 border border-primary/30 dark:border-divider">
                            <p className="font-semibold mb-1">⚠️ Requirements:</p>
                            <ul className="space-y-1 text-xs">
                              <li>• Container must have shell (/bin/sh)</li>
                              <li>• Create <code className="bg-info/20 dark:bg-neutral/60 px-1 rounded break-all">/logforge-scripts/</code> directory in container root</li>
                              <li>• Add one .sh script file with execute permissions</li>
                              <li>• Only shell scripts (.sh) are supported</li>
                            </ul>
                            <p className="font-semibold mt-2 mb-1">💡 Setup Guide:</p>
                            <ul className="space-y-1 text-xs">
                              <li>• <code className="bg-info/20 dark:bg-neutral/60 px-1 rounded break-all">mkdir /logforge-scripts</code></li>
                              <li>• <code className="bg-info/20 dark:bg-neutral/60 px-1 rounded break-all">chmod +x /logforge-scripts/*.sh</code></li>
                              <li>• First script alphabetically will be executed</li>
                              <li>• Setup failures reported in alert notifications</li>
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Plain English Translation */}
          <div className="min-w-0 border border-divider dark:border-divider rounded-xl p-4 sm:p-6 lg:p-8">
            <h4 className="text-sm font-bold text-text dark:text-neutral-text mb-3">Rule Preview</h4>
            <div className="min-w-0 overflow-x-hidden bg-foreground/70 dark:bg-foreground/60 rounded-lg p-4 border border-divider dark:border-divider">
              <pre className="max-w-full whitespace-pre-wrap break-words text-xs text-text dark:text-text font-mono">
                {plainEnglishTranslation}
              </pre>
            </div>
          </div>
        </div>

        {/* Dry-run result */}
        {ruleDryRunState && (
          <div
            className={`border rounded-lg p-4 ${
              ruleDryRunState.triggered
                ? 'bg-error/10 border-error/30'
                : 'bg-success/10 border-success/30'
            }`}
          >
            <div className="flex min-w-0 items-start">
              <AlertTriangle
                className={`w-5 h-5 mr-2 flex-shrink-0 ${
                  ruleDryRunState.triggered ? 'text-error' : 'text-success'
                }`}
              />
              <div className="min-w-0 text-sm">
                <p className={ruleDryRunState.triggered ? 'font-semibold text-error' : 'font-semibold text-success'}>
                  {ruleDryRunState.triggered ? 'Dry Run: Rule would trigger' : 'Dry Run: Rule would not trigger'}
                </p>
                <p className={`${ruleDryRunState.triggered ? 'text-error' : 'text-success'} break-words`}>
                  {ruleDryRunState.message}
                </p>
                <p className="text-xs text-neutral-text mt-1">
                  Logs checked: {ruleDryRunState.logsChecked}
                  {ruleDryRunState.value ? ` • Value: ${ruleDryRunState.value}` : ''}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Dry-run error */}
        {ruleDryRunError && (
          <div className="rounded-lg border border-warning/30 bg-warning/10 p-4">
            <div className="flex min-w-0 items-start">
              <AlertTriangle className="w-5 h-5 text-warning mr-2 flex-shrink-0" />
              <p className="min-w-0 break-words text-sm text-warning">{ruleDryRunError}</p>
            </div>
          </div>
        )}

        {/* Save error */}
        {saveError && (
          <div className="rounded-lg border border-error/30 bg-error/10 p-4">
            <div className="flex min-w-0 items-start">
              <AlertTriangle className="w-5 h-5 text-error mr-2 flex-shrink-0" />
              <p className="min-w-0 break-words text-sm text-error">{saveError}</p>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="sticky bottom-0 z-10 -mx-4 flex flex-col gap-3 border-t border-divider bg-background/95 px-4 pt-4 pb-1 backdrop-blur dark:border-divider dark:bg-foreground/95 sm:mx-0 sm:flex-row sm:justify-end sm:bg-transparent sm:px-0 sm:pb-0 sm:backdrop-blur-none dark:sm:bg-transparent">
          <Button
            type="button"
            variant="secondary"
            onClick={handleTestRule}
            className="sm:order-1"
            disabled={isSaving || isTestingRule}
          >
            {isTestingRule ? 'Testing Rule...' : 'Dry Run Rule'}
          </Button>
          <Button
            variant="secondary"
            onClick={onCancel}
            className="sm:order-2"
            disabled={isSaving || isTestingRule}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            className="sm:order-3"
            disabled={isSaving || isTestingRule}
          >
            {isSaving ? 'Saving...' : 'Save Rule'}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default RuleBuilder;
