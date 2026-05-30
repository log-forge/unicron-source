import type { LogEntry, NotificationEntry, UserChannel, NotificationGroup, Preset, CurrentUser, GroupTargets, TestResult } from '../types';
import { clientEnv } from '~/utils/env.client';

const API_BASE = clientEnv?.VITE_NOTIFIER_API_BASE || '/unicron/api/notifier';

// Placeholder value sent to backend to indicate "keep existing credential"
export const CREDENTIAL_PLACEHOLDER = '********';

// Fields considered sensitive (must match backend SENSITIVE_FIELDS)
export const SENSITIVE_FIELDS = new Set([
  'password', 'token', 'bot_token', 'api_token', 'webhook_url',
  'user_key', 'sid', 'api_key', 'secret',
]);

// Backend response shape (channels/presets)
interface BackendChannel {
  id: string;
  name: string;
  channel_type: string;
  enabled: boolean;
  config: Record<string, unknown>;
  has_credential: boolean;
  verified: boolean;
  created_at: string;
  updated_at: string;
}

interface BackendGroup {
  id: string;
  name: string;
  enabled: boolean;
  target_config?: GroupTargets;
  created_at?: string;
  updated_at?: string;
}

function mapGroup(group: BackendGroup): NotificationGroup {
  const targets = group.target_config || { channel_ids: [], preset_ids: [] };
  return {
    id: group.id,
    name: group.name,
    enabled: group.enabled,
    targets,
    target_config: targets,
    created_at: group.created_at,
    updated_at: group.updated_at,
  };
}

export class NotifierApiService {
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options?.headers as Record<string, string>,
    };

    const response = await fetch(`${API_BASE}${endpoint}`, {
      credentials: 'include',
      headers,
      ...options,
    });

    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try {
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const body = await response.json();
          message = body.detail || body.error || body.message || message;
        } else {
          const text = await response.text();
          if (text) message = text;
        }
      } catch {
        // ignore parsing failures
      }
      throw new Error(message);
    }

    if (response.status === 204) {
      return null as T;
    }

    return response.json();
  }

  // Auth
  async getCurrentUser(): Promise<{ user: CurrentUser | null }> {
    return this.request('/auth/me');
  }

  // Notifications
  async getNotifications(): Promise<{ notifications: NotificationEntry[] }> {
    const response = await this.getLogs();

    return {
      notifications: response.logs.map((log) => ({
        id: log.id,
        timestamp: log.timestamp,
        client: log.channel_id,
        message: log.message,
        original: log.message,
        ai: log.error,
        severity: log.level?.toLowerCase(),
        status: log.status,
      })),
    };
  }

  // Logs
  async getLogs(): Promise<{ logs: LogEntry[] }> {
    return this.request('/logs');
  }

  // Channels
  async getUserChannels(): Promise<{ channels: UserChannel[] }> {
    const resp = await this.request<{ items: BackendChannel[]; total: number }>('/channels');
    return {
      channels: resp.items.map(ch => ({
        id: ch.id,
        type: ch.channel_type,
        label: ch.name,
        enabled: ch.enabled,
        config: ch.config,
        has_credential: ch.has_credential,
        created_at: ch.created_at,
        updated_at: ch.updated_at,
      })),
    };
  }

  async createUserChannel(data: { type: string; label?: string; enabled: boolean; config: Record<string, unknown> }): Promise<UserChannel> {
    const backendData = {
      name: data.label || data.type,
      channel_type: data.type,
      enabled: data.enabled,
      config: data.config,
    };
    const resp = await this.request<BackendChannel>('/channels', {
      method: 'POST',
      body: JSON.stringify(backendData),
    });
    return {
      id: resp.id,
      type: resp.channel_type,
      label: resp.name,
      enabled: resp.enabled,
      config: resp.config,
      has_credential: resp.has_credential,
      created_at: resp.created_at,
      updated_at: resp.updated_at,
    };
  }

  async updateUserChannel(id: string, data: { label?: string; enabled?: boolean; config?: Record<string, unknown> }): Promise<UserChannel> {
    const backendData: Record<string, unknown> = {};
    if (data.label !== undefined) backendData.name = data.label;
    if (data.enabled !== undefined) backendData.enabled = data.enabled;
    if (data.config !== undefined) backendData.config = data.config;
    const resp = await this.request<BackendChannel>(`/channels/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(backendData),
    });
    return {
      id: resp.id,
      type: resp.channel_type,
      label: resp.name,
      enabled: resp.enabled,
      config: resp.config,
      has_credential: resp.has_credential,
      created_at: resp.created_at,
      updated_at: resp.updated_at,
    };
  }

  async deleteUserChannel(id: string): Promise<void> {
    return this.request(`/channels/${id}`, { method: 'DELETE' });
  }

  // Groups
  async getMyGroups(): Promise<{ groups: NotificationGroup[] }> {
    return this.getAllGroups();
  }

  async createGroup(data: { name: string; enabled?: boolean; description?: string; target_config?: GroupTargets }): Promise<NotificationGroup> {
    const resp = await this.request<BackendGroup>('/groups', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return mapGroup(resp);
  }

  async updateGroup(id: string, data: { name?: string; enabled?: boolean; description?: string; target_config?: GroupTargets }): Promise<NotificationGroup> {
    const resp = await this.request<BackendGroup>(`/groups/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    return mapGroup(resp);
  }

  async deleteGroup(id: string): Promise<void> {
    return this.request(`/groups/${id}`, { method: 'DELETE' });
  }

  async updateGroupTargets(groupId: string, targets: GroupTargets): Promise<void> {
    await this.request(`/groups/${groupId}`, {
      method: 'PATCH',
      body: JSON.stringify({ target_config: targets }),
    });
  }

  // Admin: Presets
  async getPresets(): Promise<{ presets: Preset[] }> {
    const resp = await this.request<{ items: BackendChannel[]; total: number }>('/presets');
    return {
      presets: resp.items.map(p => ({
        id: p.id,
        type: p.channel_type,
        label: p.name,
        enabled: p.enabled,
        config: p.config,
        has_credential: p.has_credential,
        created_at: p.created_at,
        updated_at: p.updated_at,
      })),
    };
  }

  async createPreset(data: { type: string; label: string; enabled: boolean; config: Record<string, unknown> }): Promise<Preset> {
    const backendData = {
      name: data.label,
      channel_type: data.type,
      enabled: data.enabled,
      config: data.config,
    };
    const resp = await this.request<BackendChannel>('/presets', {
      method: 'POST',
      body: JSON.stringify(backendData),
    });
    return {
      id: resp.id,
      type: resp.channel_type,
      label: resp.name,
      enabled: resp.enabled,
      config: resp.config,
      has_credential: resp.has_credential,
      created_at: resp.created_at,
      updated_at: resp.updated_at,
    };
  }

  async updatePreset(id: string, data: { label?: string; enabled?: boolean; config?: Record<string, unknown> }): Promise<Preset> {
    const backendData: Record<string, unknown> = {};
    if (data.label !== undefined) backendData.name = data.label;
    if (data.enabled !== undefined) backendData.enabled = data.enabled;
    if (data.config !== undefined) backendData.config = data.config;
    const resp = await this.request<BackendChannel>(`/presets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(backendData),
    });
    return {
      id: resp.id,
      type: resp.channel_type,
      label: resp.name,
      enabled: resp.enabled,
      config: resp.config,
      has_credential: resp.has_credential,
      created_at: resp.created_at,
      updated_at: resp.updated_at,
    };
  }

  async deletePreset(id: string): Promise<void> {
    return this.request(`/presets/${id}`, { method: 'DELETE' });
  }

  // Admin: All Groups
  async getAllGroups(): Promise<{ groups: NotificationGroup[] }> {
    const resp = await this.request<{ items: BackendGroup[]; total: number }>('/groups');
    return { groups: resp.items.map(mapGroup) };
  }

  // AI Settings
  async getAISettings(): Promise<AISettingsData> {
    return this.request('/ai-settings');
  }

  async updateAISettings(data: Partial<AISettingsData>): Promise<AISettingsData> {
    return this.request('/ai-settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // Test methods
  async testChannel(channelId: string): Promise<TestResult> {
    return this.request(`/channels/${channelId}/test`, { method: 'POST' });
  }

  async testPreset(presetId: string): Promise<TestResult> {
    return this.request(`/presets/${presetId}/test`, { method: 'POST' });
  }
}

// AI Settings data type
export interface AISettingsData {
  ai_enabled: boolean;
  ollama_url: string;
  ollama_model: string;
  ai_timeout: number;
  ai_cache_ttl: number;
  ai_default_preprompt: string;
  has_overrides: boolean;
}

export const notifierApi = new NotifierApiService();
