export type AlertStatus = 'firing' | 'acknowledged';

export interface Alert {
  id: string;
  rule_id: string;
  rule_name: string;
  message: string;
  context: any;
  timestamp: string;
  action_type: string;
  status: AlertStatus;
  severity?: string;
  labels?: Record<string, string>;
  annotations?: Record<string, any>;
  started_at?: string;
  ends_at?: string;
  updated_at?: string;
  count?: number;
  last_seen?: string;
}

export interface AlertsMeta {
  limit: number | null;
  requestedLimit: number | null;
  hasMore: boolean;
  totalAvailable: number | null;
  edition: string;
}

export interface AlertsPayload {
  alerts: Alert[];
  meta: AlertsMeta;
}

export interface AlertHistoryItem {
  id: string;
  rule_id: string;
  rule_name: string;
  severity: string;
  message: string;
  context: Record<string, any>;
  status: string;
  triggered_at: string;
  organization_id: string;
}
