import type { AlertRule } from '../types';

export function generateRuleDescription(rule: AlertRule, _containers: any[] = [], groups: any[] = []): string {
  let description = '';

  // Trigger part
  switch (rule.trigger_type) {
    case 'keyword':
      if (Array.isArray(rule.trigger_value)) {
        description += `When logs contain the keywords "${rule.trigger_value.join('", "')}"`;
      } else {
        description += `When logs contain "${rule.trigger_value}"`;
      }
      break;
    case 'metric_threshold':
      if (typeof rule.trigger_value === 'object' && rule.trigger_value) {
        const config = rule.trigger_value as any;
        const metric = config.metric_type || 'CPU';
        const operator = config.operator === '>' ? 'exceeds' : config.operator === '<' ? 'falls below' : 'equals';
        const threshold = config.threshold || '90';
        description += `When ${metric.toUpperCase()} usage ${operator} ${threshold}%`;
      }
      break;
    case 'container_event':
      const event = rule.trigger_value || 'restart';
      description += `When container ${event} occurs`;
      break;
    default:
      description += 'When trigger condition is met';
  }

  // Timeline part
  if (rule.timeline_count && rule.timeline_minutes) {
    description += ` at least ${rule.timeline_count} times within ${rule.timeline_minutes} minutes`;
  } else if (rule.timeline_minutes && rule.trigger_type === 'metric_threshold') {
    description += ` continuously for ${rule.timeline_minutes} minutes`;
  }

  // Scope part
  if (rule.scope_type === 'herald' && rule.scope_targets && rule.scope_targets.length > 0) {
    description += ` for all containers on host: ${rule.scope_targets.join(', ')}`;
  } else if (rule.scope_type === 'container' && rule.scope_targets && rule.scope_targets.length > 0) {
    description += ` for containers: ${rule.scope_targets.slice(0, 2).join(', ')}${rule.scope_targets.length > 2 ? ` and ${rule.scope_targets.length - 2} more` : ''}`;
  } else if (rule.scope_type === 'group' && rule.scope_targets && rule.scope_targets.length > 0) {
    const groupNames = rule.scope_targets.map((id: string) => {
      const group = groups.find((g: any) => g.groupId.toString() === id);
      return group ? (group.name || `Group ${group.groupId}`) : `Group ${id}`;
    });
    description += ` for groups: ${groupNames.slice(0, 2).join(', ')}${groupNames.length > 2 ? ` and ${groupNames.length - 2} more` : ''}`;
  } else if (rule.scope_type === 'global') {
    description += ' for all containers (legacy global)';
  }

  // Actions part
  if (rule.actions && rule.actions.length > 0) {
    description += `, then:\n`;
    rule.actions.forEach((action, index) => {
      const actionName = action.type === 'notification' ? 'Send Notification' :
                        action.type === 'restart_container' ? 'Restart Container' :
                        action.type === 'stop_container' ? 'Stop Container' :
                        action.type === 'start_container' ? 'Start Container' :
                        action.type === 'kill_container' ? 'Kill Container' :
                        action.type;
      description += `${index + 1}. ${actionName}\n`;
    });
    description = description.trim(); // Remove trailing newline
  } else {
    description += `, then send notification`;
  }

  return description;
}
