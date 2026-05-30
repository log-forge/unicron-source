/**
 * Notifier API client for global notification preferences and channels.
 *
 * Provides functions for managing deployment-wide notification preferences including
 * preferred channels, minimum severity, and quiet hours configuration.
 * Also provides full CRUD for notification channels.
 */

import { httpApp } from "../http.client";
import { clientLog } from "../logging/logger.client";

// ============================================================================
// Types
// ============================================================================

/**
 * Severity levels for notification filtering.
 */
export type SeverityLevel = "critical" | "warning" | "info";

/**
 * Channel types supported by the notifier.
 * Extended to include SMS, Pushover, Telegram, Gotify from original LogForge.
 */
export type ChannelType =
  | "email"
  | "slack"
  | "teams"
  | "webhook"
  | "sms"
  | "pushover"
  | "telegram"
  | "gotify"
  | "discord";

/**
 * Deployment-wide notification preference.
 */
export interface NotificationPreference {
  quiet_hours_start: number | null; // Hour 0-23
  quiet_hours_end: number | null; // Hour 0-23
  quiet_hours_timezone: string | null; // e.g., "America/New_York"
  min_severity: SeverityLevel;
  preferred_channels: string[]; // Channel IDs
  created_at: string;
  updated_at: string;
}

/**
 * Request payload for updating global preferences.
 */
export interface PreferenceUpdateRequest {
  quiet_hours?: {
    start_hour: number;
    end_hour: number;
    timezone: string;
  } | null;
  min_severity?: SeverityLevel | null;
  preferred_channels?: string[];
}

// ============================================================================
// Channel Configuration Types
// ============================================================================

/**
 * Email channel configuration.
 */
export interface EmailConfig {
  smtp_host: string;
  smtp_port: number;
  username: string;
  password: string;
  to_email: string;
  from_email?: string;
  mode?: "ssl" | "starttls";
}

/**
 * Slack channel configuration.
 */
export interface SlackConfig {
  webhook_url: string;
}

/**
 * Microsoft Teams channel configuration.
 */
export interface TeamsConfig {
  webhook_url: string;
}

/**
 * Generic webhook channel configuration.
 */
export interface WebhookConfig {
  kind?: "json" | "form";
  host: string;
  secure?: boolean;
  port?: number;
  path?: string;
  user?: string;
  password?: string;
}

/**
 * SMS channel configuration (via Twilio).
 */
export interface SmsConfig {
  sid: string;
  token: string;
  from_number: string;
  to_number: string;
}

/**
 * Pushover channel configuration.
 */
export interface PushoverConfig {
  user_key: string;
  api_token: string;
}

/**
 * Telegram channel configuration.
 */
export interface TelegramConfig {
  bot_token: string;
  chat_id?: string;
}

/**
 * Gotify channel configuration.
 */
export interface GotifyConfig {
  host: string;
  token: string;
  secure?: boolean;
  port?: number;
  path?: string;
}

/**
 * Discord channel configuration.
 */
export interface DiscordConfig {
  webhook_url: string;
}

/**
 * Union type for all channel configurations.
 */
export type ChannelConfig =
  | EmailConfig
  | SlackConfig
  | TeamsConfig
  | WebhookConfig
  | SmsConfig
  | PushoverConfig
  | TelegramConfig
  | GotifyConfig
  | DiscordConfig;

// ============================================================================
// Channel Types
// ============================================================================

/**
 * Notification channel configuration.
 */
export interface Channel {
  id: string;
  name: string;
  channel_type: ChannelType;
  enabled: boolean;
  verified: boolean;
  config: ChannelConfig;
  created_at: string;
  updated_at: string;
}

/**
 * Request payload for creating a channel.
 */
export interface ChannelCreateRequest {
  name: string;
  channel_type: ChannelType;
  enabled?: boolean;
  config: ChannelConfig;
  from_preset_id?: string;
}

/**
 * Request payload for updating a channel.
 */
export interface ChannelUpdateRequest {
  name?: string;
  enabled?: boolean;
  config?: Partial<ChannelConfig>;
}

/**
 * Paginated channel list response.
 */
export interface ChannelListResponse {
  items: Channel[];
  total: number;
}

/**
 * Response from testing a channel.
 */
export interface TestChannelResponse {
  success: boolean;
  message?: string;
}

// ============================================================================
// Preference API Functions
// ============================================================================

const NOTIFIER_BASE = "/notifier";

/**
 * Get the deployment-wide notification preferences.
 *
 * Creates default preferences if none exist.
 */
export async function getMyPreferences(): Promise<NotificationPreference> {
  const response = await httpApp.get<NotificationPreference>(`${NOTIFIER_BASE}/preferences`);
  return response.data;
}

/**
 * Update the deployment-wide notification preferences.
 *
 * Supports partial updates - only provided fields are updated.
 */
export async function updateMyPreferences(
  data: PreferenceUpdateRequest
): Promise<NotificationPreference> {
  const response = await httpApp.patch<NotificationPreference>(
    `${NOTIFIER_BASE}/preferences`,
    data
  );
  return response.data;
}

/**
 * Get available notification channels.
 * @deprecated Use getChannels() instead for full filtering support.
 */
export async function getMyChannels(): Promise<ChannelListResponse> {
  const response = await httpApp.get<ChannelListResponse>(`${NOTIFIER_BASE}/channels`);
  return response.data;
}

// ============================================================================
// Channel CRUD API Functions
// ============================================================================

/**
 * List all notification channels.
 */
export async function getChannels(params?: {
  channel_type?: ChannelType;
  enabled_only?: boolean;
  offset?: number;
  limit?: number;
}): Promise<ChannelListResponse> {
  const queryParams = new URLSearchParams();
  if (params?.channel_type) queryParams.set("channel_type", params.channel_type);
  if (params?.enabled_only) queryParams.set("enabled_only", "true");
  if (params?.offset !== undefined) queryParams.set("offset", String(params.offset));
  if (params?.limit !== undefined) queryParams.set("limit", String(params.limit));

  const queryString = queryParams.toString();
  const url = `${NOTIFIER_BASE}/channels${queryString ? `?${queryString}` : ""}`;

  const { status, data } = await httpApp.get<ChannelListResponse>(url);
  if (status !== 200) throw new Error("Failed to fetch channels");
  clientLog.debug({ count: data.items.length, total: data.total }, "Fetched channels");
  return data;
}

/**
 * Get a specific notification channel by ID.
 */
export async function getChannel(id: string): Promise<Channel> {
  const { status, data } = await httpApp.get<Channel>(`${NOTIFIER_BASE}/channels/${id}`);
  if (status !== 200) throw new Error(`Failed to fetch channel ${id}`);
  clientLog.debug({ channelId: id }, "Fetched channel");
  return data;
}

/**
 * Create a new notification channel.
 */
export async function createChannel(request: ChannelCreateRequest): Promise<Channel> {
  const { status, data } = await httpApp.post<Channel>(`${NOTIFIER_BASE}/channels`, request);
  if (status !== 201) throw new Error("Failed to create channel");
  clientLog.info({ channelId: data.id, name: data.name }, "Created channel");
  return data;
}

/**
 * Update an existing notification channel.
 */
export async function updateChannel(id: string, request: ChannelUpdateRequest): Promise<Channel> {
  const { status, data } = await httpApp.patch<Channel>(`${NOTIFIER_BASE}/channels/${id}`, request);
  if (status !== 200) throw new Error(`Failed to update channel ${id}`);
  clientLog.info({ channelId: id }, "Updated channel");
  return data;
}

/**
 * Delete a notification channel.
 */
export async function deleteChannel(id: string): Promise<void> {
  const { status } = await httpApp.delete(`${NOTIFIER_BASE}/channels/${id}`);
  if (status !== 204) throw new Error(`Failed to delete channel ${id}`);
  clientLog.info({ channelId: id }, "Deleted channel");
}

/**
 * Enable a notification channel.
 */
export async function enableChannel(id: string): Promise<Channel> {
  const { status, data } = await httpApp.post<Channel>(`${NOTIFIER_BASE}/channels/${id}/enable`);
  if (status !== 200) throw new Error(`Failed to enable channel ${id}`);
  clientLog.info({ channelId: id }, "Enabled channel");
  return data;
}

/**
 * Disable a notification channel.
 */
export async function disableChannel(id: string): Promise<Channel> {
  const { status, data } = await httpApp.post<Channel>(`${NOTIFIER_BASE}/channels/${id}/disable`);
  if (status !== 200) throw new Error(`Failed to disable channel ${id}`);
  clientLog.info({ channelId: id }, "Disabled channel");
  return data;
}

/**
 * Verify a notification channel.
 */
export async function verifyChannel(id: string): Promise<Channel> {
  const { status, data } = await httpApp.post<Channel>(`${NOTIFIER_BASE}/channels/${id}/verify`);
  if (status !== 200) throw new Error(`Failed to verify channel ${id}`);
  clientLog.info({ channelId: id }, "Verified channel");
  return data;
}

/**
 * Test a notification channel by sending a test message.
 * Note: This endpoint may not exist yet in backend - returns helpful message.
 */
export async function testChannel(id: string): Promise<TestChannelResponse> {
  try {
    const { status, data } = await httpApp.post<TestChannelResponse>(
      `${NOTIFIER_BASE}/channels/${id}/test`
    );
    if (status !== 200) {
      return { success: false, message: "Test failed" };
    }
    clientLog.info({ channelId: id, success: data.success }, "Tested channel");
    return data;
  } catch (error) {
    // If endpoint doesn't exist, return a helpful message
    return {
      success: false,
      message: "Test endpoint not available. Channel configuration saved.",
    };
  }
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get a human-readable label for a channel type.
 */
export function getChannelTypeLabel(type: ChannelType): string {
  const labels: Record<ChannelType, string> = {
    email: "Email",
    slack: "Slack",
    teams: "Microsoft Teams",
    webhook: "Webhook",
    sms: "SMS",
    pushover: "Pushover",
    telegram: "Telegram",
    gotify: "Gotify",
    discord: "Discord",
  };
  return labels[type] ?? type;
}

/**
 * Get configuration summary for display in channel list.
 */
export function getChannelConfigSummary(channel: Channel): string {
  const config = channel.config;

  switch (channel.channel_type) {
    case "email": {
      const emailConfig = config as EmailConfig;
      return emailConfig.to_email || "Email recipient not set";
    }
    case "slack": {
      const slackConfig = config as SlackConfig;
      return slackConfig.webhook_url ? "Webhook configured" : "Webhook not configured";
    }
    case "teams": {
      const teamsConfig = config as TeamsConfig;
      return teamsConfig.webhook_url ? "Webhook configured" : "Webhook not configured";
    }
    case "webhook": {
      const webhookConfig = config as WebhookConfig;
      const protocol = webhookConfig.secure !== false ? "https" : "http";
      const port = webhookConfig.port ? `:${webhookConfig.port}` : "";
      const path = webhookConfig.path || "";
      return `${protocol}://${webhookConfig.host}${port}${path}`;
    }
    case "sms": {
      const smsConfig = config as SmsConfig;
      return smsConfig.to_number || "Phone number not set";
    }
    case "pushover": {
      const pushoverConfig = config as PushoverConfig;
      return pushoverConfig.user_key ? "User configured" : "Not configured";
    }
    case "telegram": {
      const telegramConfig = config as TelegramConfig;
      return telegramConfig.bot_token ? "Bot configured" : "Bot not configured";
    }
    case "gotify": {
      const gotifyConfig = config as GotifyConfig;
      const protocol = gotifyConfig.secure !== false ? "https" : "http";
      return gotifyConfig.host ? `${protocol}://${gotifyConfig.host}` : "Not configured";
    }
    case "discord": {
      const discordConfig = config as DiscordConfig;
      return discordConfig.webhook_url ? "Webhook configured" : "Webhook not configured";
    }
    default:
      return "Configuration details";
  }
}

/**
 * Get default configuration for a channel type.
 */
export function getDefaultChannelConfig(type: ChannelType): ChannelConfig {
  switch (type) {
    case "email":
      return {
        smtp_host: "",
        smtp_port: 587,
        username: "",
        password: "",
        to_email: "",
        from_email: "",
        mode: "starttls",
      } as EmailConfig;
    case "slack":
      return {
        webhook_url: "",
      } as SlackConfig;
    case "teams":
      return {
        webhook_url: "",
      } as TeamsConfig;
    case "webhook":
      return {
        kind: "json",
        host: "",
        secure: true,
        port: undefined,
        path: "",
        user: "",
        password: "",
      } as WebhookConfig;
    case "sms":
      return {
        sid: "",
        token: "",
        from_number: "",
        to_number: "",
      } as SmsConfig;
    case "pushover":
      return {
        user_key: "",
        api_token: "",
      } as PushoverConfig;
    case "telegram":
      return {
        bot_token: "",
        chat_id: "",
      } as TelegramConfig;
    case "gotify":
      return {
        host: "",
        token: "",
        secure: true,
        port: undefined,
        path: "",
      } as GotifyConfig;
    case "discord":
      return {
        webhook_url: "",
      } as DiscordConfig;
    default:
      return {} as ChannelConfig;
  }
}
