export interface RuleTemplate {
  id: string;
  name: string;
  description: string;
  category: 'stability' | 'performance' | 'logs' | 'security';
  trigger_type: string;
  trigger_value: any;
  timeline_minutes?: number;
  timeline_count?: number;
  actions: Array<{
    type: string;
    config: any;
    delay_seconds?: number;
  }>;
  customizable_fields: string[];
  required_metrics: string[];
}

export interface TemplatesByCategory {
  [category: string]: RuleTemplate[];
}

export interface AvailableMetrics {
  available_metrics: string[];
  required_metrics: string[];
  last_checked: string;
}

export interface TemplateActivation {
  rule_name?: string;
  customizations: Record<string, any>;
  scope_type: 'global' | 'container' | 'group' | 'herald';
  scope_targets: string[];
  custom_tags?: string[];
}
