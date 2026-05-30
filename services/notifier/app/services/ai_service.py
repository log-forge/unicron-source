"""AI enrichment service for notification processing.

Wraps Ollama /api/generate with Redis caching, regex gating, and
graceful fallback.  Designed for cooperative execution under gevent
monkey-patching (synchronous requests, async Redis).

Usage:
    from app.services.ai_service import ai_service
    enrichment = await ai_service.enrich(alert_id, alert_data)
"""

import json
import re
from typing import Any, Dict, Optional, Protocol

import requests

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("notifier.services.ai_service")


class AISettingsSnapshot(Protocol):
    ai_enabled: bool
    ollama_url: str
    ollama_model: str
    ai_timeout: int
    ai_cache_ttl: int
    ai_default_preprompt: str


class AIEnrichmentService:
    """AI enrichment via local Ollama LLM with Redis caching.

    Key design decisions:
    - Synchronous ``requests.Session`` for Ollama calls (gevent-safe).
    - Async Redis for cache get/setex (matches notifier async stack).
    - No model verification on init -- Ollama may start after notifier.
    - No retry logic -- single attempt with timeout + graceful fallback.
    """

    def __init__(self) -> None:
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enrich(
        self,
        alert_id: str,
        alert_data: Dict[str, Any],
        preprompt: Optional[str] = None,
        regex_gate: Optional[str] = None,
        effective_settings: Optional[AISettingsSnapshot] = None,
    ) -> Optional[Dict[str, str]]:
        """Enrich an alert with AI-generated summary.

        Args:
            alert_id: Unique alert identifier (used as cache key).
            alert_data: Alert payload dict (title, severity, message, labels).
            preprompt: Optional custom system prompt override.
            regex_gate: Optional regex pattern to strip from AI output.
            effective_settings: Optional org-scoped effective AI settings.

        Returns:
            ``{"ai_summary": "..."}`` on success, ``None`` on any
            failure, timeout, or when AI is disabled.
        """
        if not self._ai_enabled(effective_settings):
            return None

        # --- Redis cache check ---
        from app.core.redis import get_redis

        redis = await get_redis()
        organization_id = (
            str(alert_data.get("organization_id") or "local").strip() or "local"
        )
        cache_key = f"ai:enrichment:{organization_id}:{alert_id}"

        try:
            cached = await redis.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for alert %s", alert_id)
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Redis cache read failed for %s: %s", alert_id, exc)

        # --- Build prompt & call Ollama ---
        prompt = self._build_prompt(alert_data, preprompt, effective_settings)
        result = self._call_ollama(prompt, effective_settings)

        if result is None:
            return None

        # --- Regex gate ---
        if regex_gate:
            result = self._apply_regex_gate(result, regex_gate)

        enrichment: Dict[str, str] = {"ai_summary": result}

        # --- Cache result ---
        try:
            await redis.setex(
                cache_key,
                self._cache_ttl(effective_settings),
                json.dumps(enrichment),
            )
        except Exception as exc:
            logger.warning("Redis cache write failed for %s: %s", alert_id, exc)

        return enrichment

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        alert_data: Dict[str, Any],
        preprompt: Optional[str] = None,
        effective_settings: Optional[AISettingsSnapshot] = None,
    ) -> str:
        """Build the LLM prompt from alert data.

        Format:
            <preprompt>

            Alert Title: ...
            Severity: ...
            Message: ...
            Labels: { ... }
        """
        prefix = preprompt or self._default_preprompt(effective_settings)

        title = alert_data.get("title", "")
        severity = alert_data.get("severity", "unknown")
        message = alert_data.get("message", "")
        labels = alert_data.get("labels", {})

        parts = [
            prefix,
            "",
            f"Alert Title: {title}",
            f"Severity: {severity}",
            f"Message: {message}",
            f"Labels: {json.dumps(labels)}",
        ]
        return "\n".join(parts)

    def _call_ollama(
        self,
        prompt: str,
        effective_settings: Optional[AISettingsSnapshot] = None,
    ) -> Optional[str]:
        """Synchronous Ollama /api/generate call.

        Returns the generated text on success, ``None`` on any error.
        Cooperative under gevent monkey-patching.
        """
        ollama_url = self._ollama_url(effective_settings).rstrip("/")
        timeout = self._timeout(effective_settings)
        url = f"{ollama_url}/api/generate"
        payload = {
            "model": self._ollama_model(effective_settings),
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = self._session.post(
                url,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json().get("response", "")

        except requests.exceptions.Timeout:
            logger.warning(
                "Ollama request timed out after %ds", timeout
            )
            return None

        except requests.exceptions.ConnectionError:
            logger.warning("Ollama service unreachable at %s", ollama_url)
            return None

        except Exception as exc:
            logger.error("Ollama call failed: %s", exc)
            return None

    @staticmethod
    def _apply_regex_gate(text: str, pattern: str) -> str:
        """Strip substrings matching *pattern* from AI output.

        Returns the original text unchanged if the pattern is invalid.
        """
        try:
            return re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE).strip()
        except re.error as exc:
            logger.warning("Invalid regex gate pattern %r: %s", pattern, exc)
            return text

    @staticmethod
    def _ai_enabled(effective_settings: Optional[AISettingsSnapshot]) -> bool:
        if effective_settings is not None:
            return effective_settings.ai_enabled
        return settings.AI_ENABLED

    @staticmethod
    def _ollama_url(effective_settings: Optional[AISettingsSnapshot]) -> str:
        if effective_settings is not None:
            return effective_settings.ollama_url
        return settings.OLLAMA_URL

    @staticmethod
    def _ollama_model(effective_settings: Optional[AISettingsSnapshot]) -> str:
        if effective_settings is not None:
            return effective_settings.ollama_model
        return settings.OLLAMA_MODEL

    @staticmethod
    def _timeout(effective_settings: Optional[AISettingsSnapshot]) -> int:
        if effective_settings is not None:
            return effective_settings.ai_timeout
        return settings.AI_TIMEOUT

    @staticmethod
    def _cache_ttl(effective_settings: Optional[AISettingsSnapshot]) -> int:
        if effective_settings is not None:
            return effective_settings.ai_cache_ttl
        return settings.AI_CACHE_TTL

    @staticmethod
    def _default_preprompt(effective_settings: Optional[AISettingsSnapshot]) -> str:
        if effective_settings is not None:
            return effective_settings.ai_default_preprompt
        return settings.AI_DEFAULT_PREPROMPT


# Module-level singleton
ai_service = AIEnrichmentService()
