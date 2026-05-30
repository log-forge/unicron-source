"""Template rendering service for notification messages."""

from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.logging import get_logger

logger = get_logger("template_service")

# Default templates directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class TemplateService:
    """Renders notification templates using Jinja2."""

    def __init__(self):
        self._env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Default template mapping for all 9 channel types
        self._default_templates = {
            "email": "default_email.jinja2",
            "slack": "default_slack.jinja2",
            "teams": "default_teams.jinja2",
            "webhook": "default_webhook.jinja2",
            "sms": "default_sms.jinja2",
            "pushover": "default_pushover.jinja2",
            "discord": "default_discord.jinja2",
            "telegram": "default_slack.jinja2",    # Telegram uses markdown, same as Slack
            "gotify": "default_slack.jinja2",      # Gotify supports markdown, same as Slack
        }

    def render(
        self,
        channel_type: str,
        context: Dict[str, Any],
        custom_template: Optional[str] = None,
    ) -> str:
        """
        Render notification message from template.

        Args:
            channel_type: Type of channel (email, slack, teams, webhook, sms, pushover, discord, telegram, gotify)
            context: Template variables (title, message, severity, etc.)
            custom_template: Optional custom template string to use

        Returns:
            Rendered message string
        """
        if custom_template:
            # Use custom template string
            template = self._env.from_string(custom_template)
        else:
            # Use default template for channel type
            template_name = self._default_templates.get(channel_type)
            if not template_name:
                raise ValueError(f"No default template for channel type: {channel_type}")
            template = self._env.get_template(template_name)

        return template.render(**context)

    def render_preview(
        self,
        channel_type: str,
        template_string: str,
    ) -> str:
        """
        Render template with sample data for preview.

        Args:
            channel_type: Type of channel
            template_string: Template to preview

        Returns:
            Rendered preview string
        """
        sample_context = {
            "title": "Sample Alert: High CPU Usage",
            "message": "Container web-app-1 CPU usage exceeded 90% threshold",
            "severity": "warning",
            "rule_name": "High CPU Alert",
            "triggered_at": "2026-01-16T12:00:00Z",
            "alert_id": "sample123",
            "context": {
                "container": "web-app-1",
                "cpu_percent": 92.5,
                "threshold": 90,
            },
        }
        return self.render(channel_type, sample_context, custom_template=template_string)

    def get_default_template(self, channel_type: str) -> str:
        """Get the default template content for a channel type."""
        template_name = self._default_templates.get(channel_type)
        if not template_name:
            raise ValueError(f"No default template for channel type: {channel_type}")

        template_path = TEMPLATES_DIR / template_name
        return template_path.read_text()


# Singleton instance
template_service = TemplateService()
