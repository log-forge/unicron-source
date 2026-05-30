// Notification types for notifier feature.

export interface LogEntry {
  id: string;
  timestamp: string;
  level: string;
  message: string;
  channel_type?: string;
  channel_id?: string;
  status?: string;
  error?: string;
}

export interface NotificationEntry {
  id: string;
  timestamp: string;
  client?: string;
  message: string;
  original?: string;
  ai?: string;
  severity?: string;
  status?: string;
}

export interface UserChannel {
  id: string;
  type: string;
  label?: string;
  enabled: boolean;
  config: Record<string, unknown>;
  has_credential?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface GroupTargets {
  channel_ids?: string[];
  preset_ids?: string[];
}

export interface NotificationGroup {
  id: string;
  name: string;
  description?: string;
  enabled?: boolean;
  targets?: GroupTargets;
  target_config?: GroupTargets;
  created_at?: string;
  updated_at?: string;
}

export interface Preset {
  id: string;
  type: string;
  label: string;
  enabled: boolean;
  config: Record<string, unknown>;
  has_credential?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CurrentUser {
  id: number;
  email: string;
  role: string;
}

export interface TestResult {
  status: string;  // "success" or "failed"
  message: string;
  channel_type?: string;
}
