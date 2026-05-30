"""Logging configuration for notifier service.

Includes CredentialScrubFilter for redacting sensitive fields and
Apprise URLs from log messages in notification code paths.
"""

import logging
import re
import sys
from app.core.config import settings

# ---------------------------------------------------------------------------
# Credential scrubbing
# ---------------------------------------------------------------------------

# Known sensitive field names that must never appear in plaintext in logs.
# Sorted longest-first so that e.g. "bot_token" is matched before "token".
_SCRUB_FIELDS = sorted(
    [
        "password",
        "token",
        "bot_token",
        "api_token",
        "webhook_url",
        "user_key",
        "sid",
        "api_key",
        "secret",
        "pass",
    ],
    key=len,
    reverse=True,
)

# Build a single alternation for all field names (longest-first for priority).
_FIELD_ALT = "|".join(re.escape(f) for f in _SCRUB_FIELDS)

# Pattern for field=value (until whitespace, comma, quote, paren, or end)
_PAT_FIELD_EQ = re.compile(
    rf"\b({_FIELD_ALT})\s*=\s*([^\s,'\"\)]+)",
    re.IGNORECASE,
)

# Pattern for field: value (plain, no quotes; exclude < to avoid re-matching redacted markers)
_PAT_FIELD_COLON = re.compile(
    rf"\b({_FIELD_ALT})\s*:\s*([^\s,'\"\)<]+)",
    re.IGNORECASE,
)

# Pattern for 'field': 'value' or "field": "value"
_PAT_FIELD_QUOTED = re.compile(
    rf"""(['"])({_FIELD_ALT})\1\s*:\s*(['"])(.+?)\3""",
    re.IGNORECASE,
)

# Apprise URL schemes and known webhook hosts to redact entirely.
_APPRISE_SCHEMES = (
    "mailtos://",
    "mailto://",
    "tgram://",
    "pover://",
    "gotifys://",
    "gotify://",
    "jsons://",
    "json://",
    "forms://",
    "form://",
    "twilio://",
    "msteams://",
)
_WEBHOOK_HOSTS = (
    "https://hooks.slack.com/",
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)

# Build a single regex that matches any Apprise URL or known webhook URL
_url_alts = [re.escape(s) + r"[^\s'\"]*" for s in _APPRISE_SCHEMES]
_url_alts += [re.escape(h) + r"[^\s'\"]*" for h in _WEBHOOK_HOSTS]
_URL_PATTERN = re.compile("|".join(_url_alts), re.IGNORECASE)


def scrub_text(text: str) -> str:
    """Apply credential scrubbing to an arbitrary string.

    Redacts:
      - Known sensitive field values (password, token, etc.)
      - Apprise URLs and known webhook URLs

    This is the standalone function for non-logger contexts such as
    error messages stored in the database.
    """
    if not text:
        return text

    # --- Apprise / webhook URL scrubbing (do first so field patterns
    # don't partially mangle URLs) ---
    text = _URL_PATTERN.sub("[REDACTED URL]", text)

    # --- Known field scrubbing ---
    # field=value  ->  field: <field redacted>
    text = _PAT_FIELD_EQ.sub(
        lambda m: f"{m.group(1)}: <{m.group(1)} redacted>", text
    )
    # field: value  ->  field: <field redacted>
    text = _PAT_FIELD_COLON.sub(
        lambda m: f"{m.group(1)}: <{m.group(1)} redacted>", text
    )
    # 'field': 'value' or "field": "value"  ->  field: <field redacted>
    text = _PAT_FIELD_QUOTED.sub(
        lambda m: f"{m.group(2)}: <{m.group(2)} redacted>", text
    )

    return text


class CredentialScrubFilter(logging.Filter):
    """Logging filter that redacts sensitive credentials from log records.

    Scrubs:
      - Known field names (password, token, api_key, etc.)
      - Apprise URL schemes and known webhook URLs

    Applied only to notification/channel code-path loggers, not globally.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Scrub the message string
        if isinstance(record.msg, str):
            record.msg = scrub_text(record.msg)

        # Scrub %-format args if they are strings
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: scrub_text(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    scrub_text(a) if isinstance(a, str) else a for a in record.args
                )

        return True


# Logger names that should have the credential scrub filter attached
_SCRUBBED_LOGGER_PREFIXES = (
    "delivery_service",
    "notifier",
    "app.tasks",
    "app.services",
)


def setup_logging() -> None:
    """Configure logging for notifier service.

    Attaches CredentialScrubFilter to notification/channel loggers.
    """
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Attach scrub filter to targeted loggers
    scrub_filter = CredentialScrubFilter()
    for prefix in _SCRUBBED_LOGGER_PREFIXES:
        target_logger = logging.getLogger(prefix)
        # Avoid duplicate filters on repeated calls
        if not any(isinstance(f, CredentialScrubFilter) for f in target_logger.filters):
            target_logger.addFilter(scrub_filter)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


def get_scrubbed_logger(name: str) -> logging.Logger:
    """Get a logger with CredentialScrubFilter already attached.

    Use this in notification-related modules to ensure credentials are
    scrubbed even if setup_logging() hasn't run yet (e.g., Celery workers).
    """
    lgr = logging.getLogger(name)
    if not any(isinstance(f, CredentialScrubFilter) for f in lgr.filters):
        lgr.addFilter(CredentialScrubFilter())
    return lgr
