import type { AlertRule, MetricThresholdConfig } from '../types';

export const getTriggerValueDisplay = (rule: AlertRule): string => {
  if (rule.trigger_type === 'keyword') {
    const values = Array.isArray(rule.trigger_value)
      ? rule.trigger_value
      : (typeof rule.trigger_value === 'string' ? [rule.trigger_value] : []);
    if (values.length > 0) {
      const label = values.length > 1 ? 'Keywords' : 'Keyword';
      return `${label}: "${values.join('", "')}"`;
    }
  }

  if (rule.trigger_type === 'metric_threshold' && typeof rule.trigger_value === 'object' && rule.trigger_value) {
    const config = rule.trigger_value as MetricThresholdConfig;
    return `${config.metric_type} ${config.operator} ${config.threshold}`;
  }

  if (rule.trigger_type === 'container_event' && typeof rule.trigger_value === 'string') {
    return `Event: ${rule.trigger_value}`;
  }

  return 'Unknown trigger';
};

export const formatTimestamp = (timestamp: string): string => {
  return new Date(timestamp).toLocaleString();
};

export const formatRuleName = (trigger_type: string): string => {
  return trigger_type.replace('_', ' ');
};
