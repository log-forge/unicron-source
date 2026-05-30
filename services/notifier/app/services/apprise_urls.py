"""Build Apprise-compatible URLs from channel configurations."""

from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode


def _q(value: str) -> str:
    """URL-encode a value."""
    return quote(str(value), safe="")


def build_email_url(config: Dict[str, Any]) -> str:
    """
    Build Apprise mailto URL from email config.

    Config keys: smtp_host, smtp_port, username, password, to_email, from_email, mode
    Returns: mailtos://domain:port/?user=...&pass=...&smtp=...&to=...
    """
    smtp_host = (config.get("smtp_host") or "").strip()
    smtp_port = str(config.get("smtp_port") or "").strip()
    username = (config.get("username") or "").strip()
    password = (config.get("password") or "").strip()
    to_email = (config.get("to_email") or "").strip()
    from_email = (config.get("from_email") or "").strip()
    mode = (config.get("mode") or "").strip().lower()

    if not smtp_host or not username or not password or not to_email:
        raise ValueError("email requires smtp_host, username, password, and to_email")

    # Derive domain from email addresses
    domain_source = from_email or username or to_email
    domain = domain_source.split("@")[-1] if "@" in domain_source else smtp_host

    scheme = "mailtos"
    host = f"{domain}:{smtp_port}" if smtp_port else domain

    params = {"user": username, "pass": password, "smtp": smtp_host, "to": to_email}
    if from_email:
        params["from"] = from_email
    if mode in ("ssl", "starttls"):
        params["mode"] = mode

    query = urlencode(params, quote_via=quote)
    return f"{scheme}://{host}/?{query}"


def build_slack_url(config: Dict[str, Any]) -> str:
    """Build Apprise Slack webhook URL."""
    webhook_url = (config.get("webhook_url") or "").strip()
    if not webhook_url:
        raise ValueError("slack requires webhook_url")
    # Apprise accepts native Slack webhook URLs directly
    return webhook_url


def build_teams_url(config: Dict[str, Any]) -> str:
    """Build Apprise Teams webhook URL."""
    webhook_url = (config.get("webhook_url") or "").strip()
    if not webhook_url:
        raise ValueError("teams requires webhook_url")
    # Apprise accepts native Teams webhook URLs with msteams:// scheme
    if webhook_url.startswith("https://"):
        # Convert to msteams scheme
        return "msteams://" + webhook_url[8:]
    return webhook_url


def build_discord_url(config: Dict[str, Any]) -> str:
    """Build Apprise Discord webhook URL."""
    webhook_url = (config.get("webhook_url") or "").strip()
    if not webhook_url:
        raise ValueError("discord requires webhook_url")
    # Validate Discord webhook URL format
    if not (webhook_url.startswith("https://discord.com/api/webhooks/") or
            webhook_url.startswith("https://discordapp.com/api/webhooks/")):
        raise ValueError("Discord webhook URL must start with https://discord.com/api/webhooks/ or https://discordapp.com/api/webhooks/")
    # Apprise accepts native Discord webhook URLs directly
    return webhook_url


def build_telegram_url(config: Dict[str, Any]) -> str:
    """
    Build Apprise Telegram bot URL.

    Config keys: bot_token, chat_id
    Returns: tgram://{bot_token}/{chat_id}
    """
    bot_token = (config.get("bot_token") or "").strip()
    chat_id = (config.get("chat_id") or "").strip()

    if not bot_token or not chat_id:
        raise ValueError("telegram requires bot_token and chat_id")

    return f"tgram://{_q(bot_token)}/{_q(chat_id)}"


def build_gotify_url(config: Dict[str, Any]) -> str:
    """
    Build Apprise Gotify push URL.

    Config keys: host, token, secure (default true), port (optional), path (optional)
    Returns: gotifys://{host}:{port}{path}?token={token} (gotifys for secure, gotify for insecure)
    """
    host = (config.get("host") or "").strip()
    token = (config.get("token") or "").strip()
    secure = bool(config.get("secure", True))
    port = config.get("port")
    path = (config.get("path") or "").strip()

    if not host or not token:
        raise ValueError("gotify requires host and token")

    scheme = "gotifys" if secure else "gotify"
    netloc = host
    if port:
        netloc = f"{netloc}:{port}"

    if path and not path.startswith("/"):
        path = f"/{path}"

    return f"{scheme}://{netloc}{path or ''}?token={_q(token)}"


def build_webhook_url(config: Dict[str, Any]) -> str:
    """
    Build Apprise generic webhook URL.

    Config keys: kind (json/form), host, secure, port, path, user, password
    """
    kind = (config.get("kind") or "json").strip().lower()
    host = (config.get("host") or "").strip()
    secure = bool(config.get("secure", True))
    port = str(config.get("port") or "").strip()
    path = (config.get("path") or "").strip()
    user = (config.get("user") or "").strip()
    password = (config.get("password") or "").strip()

    if not host:
        raise ValueError("webhook requires host")

    scheme = "jsons" if kind == "json" and secure else "json"
    if kind == "form":
        scheme = "forms" if secure else "form"

    auth = ""
    if user:
        auth = _q(user)
        if password:
            auth = f"{auth}:{_q(password)}"
        auth = f"{auth}@"

    netloc = f"{auth}{host}"
    if port:
        netloc = f"{netloc}:{port}"

    if path and not path.startswith("/"):
        path = f"/{path}"

    return f"{scheme}://{netloc}{path or ''}"


def build_sms_url(config: Dict[str, Any]) -> str:
    """
    Build Apprise Twilio SMS URL.

    Config keys: sid, token, from_number, to_number
    Returns: twilio://{sid}:{token}@{from_number}/{to_number}
    """
    sid = (config.get("sid") or "").strip()
    token = (config.get("token") or "").strip()
    from_number = (config.get("from_number") or "").strip()
    to_number = (config.get("to_number") or "").strip()

    if not sid or not token or not from_number or not to_number:
        raise ValueError("sms requires sid, token, from_number, and to_number")

    return f"twilio://{_q(sid)}:{_q(token)}@{_q(from_number)}/{_q(to_number)}"


PUSHOVER_SEVERITY_MAP = {
    "critical": "emergency",
    "error": "emergency",
    "warning": "high",
    "info": "normal",
}


def build_pushover_url(config: Dict[str, Any], severity: Optional[str] = None) -> str:
    """
    Build Apprise Pushover URL with optional severity-based priority.

    Config keys: user_key, api_token
    Returns: pover://{user_key}@{api_token}[?priority=...&retry=...&expire=...]

    When severity is provided and maps to a Pushover priority:
    - "critical"/"error" -> emergency priority with retry=600 (10min) and expire=3600 (1hr)
    - "warning" -> high priority
    - "info" or None -> no priority params (Apprise defaults to normal)
    """
    user_key = (config.get("user_key") or "").strip()
    api_token = (config.get("api_token") or "").strip()

    if not user_key or not api_token:
        raise ValueError("pushover requires user_key and api_token")

    base_url = f"pover://{_q(user_key)}@{_q(api_token)}"

    if severity and severity in PUSHOVER_SEVERITY_MAP:
        priority = PUSHOVER_SEVERITY_MAP[severity]
        # Normal priority is Apprise default -- no params needed
        if priority == "normal":
            return base_url
        if priority == "emergency":
            return f"{base_url}?priority={priority}&retry=600&expire=3600"
        return f"{base_url}?priority={priority}"

    return base_url


def build_apprise_url(channel_type: str, config: Dict[str, Any]) -> str:
    """Build Apprise URL based on channel type."""
    builders = {
        "email": build_email_url,
        "slack": build_slack_url,
        "teams": build_teams_url,
        "discord": build_discord_url,
        "telegram": build_telegram_url,
        "gotify": build_gotify_url,
        "webhook": build_webhook_url,
        "sms": build_sms_url,
        "pushover": build_pushover_url,
    }
    builder = builders.get(channel_type)
    if not builder:
        raise ValueError(f"Unsupported channel type: {channel_type}")
    return builder(config)


__all__ = [
    "build_apprise_url",
    "build_email_url",
    "build_slack_url",
    "build_teams_url",
    "build_discord_url",
    "build_telegram_url",
    "build_gotify_url",
    "build_webhook_url",
    "build_sms_url",
    "build_pushover_url",
]
