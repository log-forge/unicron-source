export interface ApiResponse<T> {
  data?: T;
  error?: string;
}

export interface BackpressureSnapshot {
  status: 'ok' | 'warning' | 'critical' | 'unknown';
  alerts: string[];
  streams?: {
    status?: 'ok' | 'warning' | 'critical' | 'unknown';
    totals?: {
      pending?: number;
      lag?: number;
      dlq_depth?: number;
    };
    streams?: Record<string, {
      stream: string;
      consumer_group: string;
      length: number;
      pending: number;
      lag: number;
      dlq_depth: number;
      status: 'ok' | 'warning' | 'critical' | 'unknown';
    }>;
  };
  central_log_ingest?: {
    status: 'ok' | 'warning' | 'critical' | 'unknown';
    dropped_total?: number;
    requests_total?: number;
  };
  otlp_metrics_path?: {
    status: 'ok' | 'warning' | 'critical' | 'unknown';
    queue_saturation?: number | null;
    refused_metric_points?: number;
    send_failed_metric_points?: number;
  };
  drop_counters?: {
    totals?: {
      failed_total?: number;
      parse_dropped_total?: number;
      dlq_published_total?: number;
    };
  };
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'error';
  rules_count: number;
  alerts_count: number;
  containers_count: number;
  backpressure?: BackpressureSnapshot;
  timestamp: string;
}

export interface GatekeeperSettings {
  cooldown_minutes: Record<string, number>;
  backoff_delays: number[];
  max_backoff_minutes: number;
  disable_after_failures: number;
  disable_duration_minutes: number;
  max_actions_per_rule_per_hour: number;
  max_actions_per_container_per_hour: number;
  verification_delay_seconds: number;
  trigger_suppression_enabled: boolean;
  trigger_suppression_minutes: number;
  trigger_suppression_actions: string[];
  trigger_suppression_rule_types: string[];
  dedup_enabled: boolean;
  dedup_window_seconds: number;
}

export type GatekeeperSettingsUpdate = Partial<GatekeeperSettings>;

export interface KeywordSettings {
  case_sensitive: boolean;
  multi_mode: 'any' | 'all';
  ignore_patterns: string[];
}

export type KeywordSettingsUpdate = Partial<KeywordSettings>;
