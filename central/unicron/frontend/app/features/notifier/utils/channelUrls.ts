// Channel URL builders for Apprise notification delivery
// Ported from LogForge notifier

// Config type definitions
export interface EmailConfig {
  smtp_host: string;
  smtp_port?: string | number;
  username: string;
  password: string;
  to_email: string;
  from_email?: string;
  mode?: 'ssl' | 'starttls';
}

export interface SmsConfig {
  sid: string;
  token: string;
  from_number: string;
  to_number: string;
}

export interface PushoverConfig {
  user_key: string;
  api_token: string;
}

export interface TelegramConfig {
  bot_token: string;
}

export interface GotifyConfig {
  host: string;
  token: string;
  secure?: boolean;
  port?: string | number;
  path?: string;
}

export interface WebhookConfig {
  kind: 'json' | 'form';
  host: string;
  secure?: boolean;
  port?: string | number;
  path?: string;
  user?: string;
  password?: string;
}

export interface SlackConfig {
  webhook_url: string;
}

export interface TeamsConfig {
  webhook_url: string;
}

export interface DiscordConfig {
  webhook_url: string;
}

export type PersonalChannelConfig =
  | EmailConfig
  | SlackConfig
  | TeamsConfig
  | DiscordConfig
  | SmsConfig
  | PushoverConfig
  | TelegramConfig
  | GotifyConfig
  | WebhookConfig;

export type PresetChannelConfig =
  | SlackConfig
  | TeamsConfig
  | DiscordConfig
  | TelegramConfig
  | GotifyConfig
  | WebhookConfig;

// Helper functions
const encode = (value: unknown): string => encodeURIComponent(String(value));

const buildQuery = (params: Record<string, unknown> | null | undefined): string => {
  const entries = Object.entries(params || {})
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encode(key)}=${encode(value)}`);

  return entries.length ? `?${entries.join('&')}` : '';
};

const normalizePath = (value: unknown): string => {
  if (!value) return '';
  const trimmed = String(value).trim();
  if (!trimmed) return '';
  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
};

const firstConfigValue = (
  config: Record<string, unknown> | null | undefined,
  keys: string[]
): string => {
  for (const key of keys) {
    const raw = config?.[key];
    if (raw === undefined || raw === null) continue;
    const value = String(raw).trim();
    if (value) return value;
  }
  return '';
};

const getEmailRecipient = (config: Record<string, unknown>): string => {
  const toEmail = firstConfigValue(config, ['to_email', 'email']);
  if (!toEmail) {
    throw new Error('email requires an address');
  }
  if (toEmail.includes(',')) {
    throw new Error('email address must be a single address');
  }
  return toEmail;
};

const getSmsRecipient = (config: Record<string, unknown>): string => {
  const toNumber = firstConfigValue(config, ['to_number', 'phone']);
  if (!toNumber) {
    throw new Error('sms requires a destination number');
  }
  if (toNumber.includes(',')) {
    throw new Error('sms destination must be a single number');
  }
  return toNumber;
};

const validateEmailTransport = (config: Record<string, unknown>): void => {
  const smtpHost = String(config.smtp_host || '').trim();
  const username = String(config.username || '').trim();
  const password = String(config.password || '').trim();
  if (!smtpHost || !username || !password) {
    throw new Error('email transport requires smtp_host, username, and password');
  }
};

const validateSmsTransport = (config: Record<string, unknown>): void => {
  const sid = String(config.sid || '').trim();
  const token = String(config.token || '').trim();
  const fromNumber = String(config.from_number || '').trim();
  if (!sid || !token || !fromNumber) {
    throw new Error('sms transport requires sid, token, and from_number');
  }
};

// URL builder functions
export const buildEmailUrl = (config: Record<string, unknown>): string => {
  const smtpHost = String(config.smtp_host || '').trim();
  const smtpPort = String(config.smtp_port || '').trim();
  const username = String(config.username || '').trim();
  const password = String(config.password || '').trim();
  const toEmail = String(config.to_email || '').trim();
  const fromEmail = String(config.from_email || '').trim();
  const mode = String(config.mode || '').trim().toLowerCase();

  if (!smtpHost || !username || !password || !toEmail) {
    throw new Error('email requires smtp_host, username, password, and to_email');
  }
  if (toEmail.includes(',')) {
    throw new Error('email to_email must be a single address');
  }

  const domainSource = fromEmail || username || toEmail;
  const domain = domainSource.includes('@') ? domainSource.split('@')[1] : smtpHost;
  if (!domain) {
    throw new Error('email requires a valid domain or from_email');
  }

  let host = domain;
  if (smtpPort) {
    host = `${host}:${smtpPort}`;
  }

  const params: Record<string, string> = {
    user: username,
    pass: password,
    smtp: smtpHost,
    to: toEmail,
  };

  if (fromEmail) {
    params.from = fromEmail;
  }
  if (mode === 'ssl' || mode === 'starttls') {
    params.mode = mode;
  }

  return `mailtos://${host}/` + buildQuery(params);
};

export const buildSmsUrl = (config: Record<string, unknown>): string => {
  const sid = String(config.sid || '').trim();
  const token = String(config.token || '').trim();
  const fromNumber = String(config.from_number || '').trim();
  const toNumber = String(config.to_number || '').trim();

  if (!sid || !token || !fromNumber || !toNumber) {
    throw new Error('sms requires sid, token, from_number, and to_number');
  }
  if (toNumber.includes(',')) {
    throw new Error('sms to_number must be a single number');
  }

  return `twilio://${encode(sid)}:${encode(token)}@${encode(fromNumber)}/${encode(toNumber)}`;
};

export const buildPushoverUrl = (config: Record<string, unknown>): string => {
  const userKey = String(config.user_key || '').trim();
  const apiToken = String(config.api_token || '').trim();
  if (!userKey || !apiToken) {
    throw new Error('pushover requires user_key and api_token');
  }
  return `pover://${encode(userKey)}@${encode(apiToken)}`;
};

export const buildTelegramUrl = (config: Record<string, unknown>): string => {
  const botToken = String(config.bot_token || '').trim();
  if (!botToken) {
    throw new Error('telegram requires bot_token');
  }
  return `tgram://${encode(botToken)}/`;
};

export const buildGotifyUrl = (config: Record<string, unknown>): string => {
  const host = String(config.host || '').trim();
  const token = String(config.token || '').trim();
  const secure = config.secure !== false;
  const port = String(config.port || '').trim();
  const path = normalizePath(config.path || '');

  if (!host || !token) {
    throw new Error('gotify requires host and token');
  }

  const scheme = secure ? 'gotifys' : 'gotify';
  let netloc = host;
  if (port) {
    netloc = `${netloc}:${port}`;
  }
  const fullPath = path ? `${path}/${encode(token)}` : `/${encode(token)}`;
  return `${scheme}://${netloc}${fullPath}`;
};

export const buildWebhookUrl = (config: Record<string, unknown>): string => {
  const kind = String(config.kind || '').trim().toLowerCase();
  const host = String(config.host || '').trim();
  const secure = config.secure !== false;
  const port = String(config.port || '').trim();
  const path = normalizePath(config.path || '');
  const user = String(config.user || '').trim();
  const password = String(config.password || '').trim();

  if (kind !== 'json' && kind !== 'form') {
    throw new Error('webhook kind must be json or form');
  }
  if (!host) {
    throw new Error('webhook requires host');
  }

  let scheme = kind === 'json' ? 'json' : 'form';
  if (secure) {
    scheme = `${scheme}s`;
  }

  let auth = '';
  if (user) {
    auth = encode(user);
    if (password) {
      auth = `${auth}:${encode(password)}`;
    }
    auth = `${auth}@`;
  }

  let netloc = `${auth}${host}`;
  if (port) {
    netloc = `${netloc}:${port}`;
  }

  return `${scheme}://${netloc}${path}`;
};

export const buildPersonalUrl = (
  channelType: string,
  config: Record<string, unknown>,
  transport?: Record<string, unknown>
): string => {
  switch (channelType) {
    case 'email':
      if (!transport) {
        throw new Error('email requires a transport preset');
      }
      return buildEmailUrl({ ...transport, to_email: getEmailRecipient(config) });
    case 'sms':
      if (!transport) {
        throw new Error('sms requires a transport preset');
      }
      return buildSmsUrl({ ...transport, to_number: getSmsRecipient(config) });
    case 'slack':
    case 'teams':
    case 'discord': {
      const url = String(config.webhook_url || '').trim();
      if (!url) throw new Error(`${channelType} requires webhook_url`);
      return url;
    }
    case 'pushover':
      return buildPushoverUrl(config);
    case 'telegram':
      return buildTelegramUrl(config);
    case 'gotify':
      return buildGotifyUrl(config);
    case 'webhook':
      return buildWebhookUrl(config);
    default:
      throw new Error(`unsupported channel type: ${channelType}`);
  }
};

export const buildPresetUrl = (
  channelType: string,
  config: Record<string, unknown>
): string => {
  const mode = String(config.mode || '').trim().toLowerCase();
  if (mode === 'advanced') {
    const url = String(config.url || '').trim();
    if (!url) {
      throw new Error('advanced mode requires url');
    }
    return url;
  }

  if (channelType === 'slack' || channelType === 'msteams' || channelType === 'discord') {
    const url = String(config.webhook_url || '').trim();
    if (!url) {
      throw new Error(`${channelType} requires webhook_url`);
    }
    return url;
  }
  if (channelType === 'telegram') {
    return buildTelegramUrl(config);
  }
  if (channelType === 'gotify') {
    return buildGotifyUrl(config);
  }
  if (channelType === 'webhook') {
    return buildWebhookUrl(config);
  }

  throw new Error(`unsupported preset channel type: ${channelType}`);
};

export const validatePersonalConfig = (
  channelType: string,
  config: Record<string, unknown>
): void => {
  if (channelType === 'email') {
    getEmailRecipient(config);
    return;
  }
  if (channelType === 'sms') {
    getSmsRecipient(config);
    return;
  }
  buildPersonalUrl(channelType, config, {});
};

export const validatePresetConfig = (
  channelType: string,
  config: Record<string, unknown>
): void => {
  if (channelType === 'email') {
    validateEmailTransport(config);
    return;
  }
  if (channelType === 'sms') {
    validateSmsTransport(config);
    return;
  }
  buildPresetUrl(channelType, config);
};

export const maskUrlSecrets = (url: string | null | undefined): string => {
  if (!url) return '';
  let masked = String(url);
  masked = masked.replace(/(pass=)([^&]+)/gi, '$1***');
  masked = masked.replace(/(token=)([^&]+)/gi, '$1***');
  masked = masked.replace(/(bot_token=)([^&]+)/gi, '$1***');
  masked = masked.replace(/(sid=)([^&]+)/gi, '$1***');
  masked = masked.replace(/(twilio:\/\/[^:]+:)([^@]+)@/gi, '$1***@');
  masked = masked.replace(/(mailto[s]?:\/\/[^:]+:)([^@]+)@/gi, '$1***@');
  masked = masked.replace(/(tgram:\/\/)([^/]+)/gi, '$1***');
  masked = masked.replace(/(pover:\/\/[^@]+@)([^/?#]+)/gi, '$1***');
  masked = masked.replace(/(gotify[s]?:\/\/[^/]+\/)([^/?#]+)/gi, '$1***');
  return masked;
};
