import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.modules.setdefault(
    "apprise",
    SimpleNamespace(Apprise=lambda: SimpleNamespace(add=lambda url: None)),
)

from app.services.ai_service import AIEnrichmentService


class ResponseStub:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"response": "saved-settings summary"}


class AIServiceEffectiveSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_enrich_uses_effective_settings_for_ollama_and_cache(self) -> None:
        redis = SimpleNamespace(
            get=AsyncMock(return_value=None),
            setex=AsyncMock(),
        )
        post = Mock(return_value=ResponseStub())
        service = AIEnrichmentService()
        service._session = SimpleNamespace(post=post)
        effective_settings = SimpleNamespace(
            ai_enabled=True,
            ollama_url="http://ollama.local:11434/",
            ollama_model="llama-test",
            ai_timeout=7,
            ai_cache_ttl=30,
            ai_default_preprompt="Summarize precisely.",
        )

        with patch("app.core.redis.get_redis", new=AsyncMock(return_value=redis)):
            result = await service.enrich(
                alert_id="alert-1",
                alert_data={
                    "organization_id": "org-1",
                    "title": "Disk alert",
                    "severity": "warning",
                    "message": "disk full",
                    "labels": {"host": "node-a"},
                },
                effective_settings=effective_settings,
            )

        self.assertEqual(result, {"ai_summary": "saved-settings summary"})
        post.assert_called_once()
        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        self.assertEqual(url, "http://ollama.local:11434/api/generate")
        self.assertEqual(payload["model"], "llama-test")
        self.assertIn("Summarize precisely.", payload["prompt"])
        self.assertEqual(post.call_args.kwargs["timeout"], 7)
        redis.setex.assert_awaited_once()
        self.assertEqual(redis.setex.await_args.args[0], "ai:enrichment:org-1:alert-1")
        self.assertEqual(redis.setex.await_args.args[1], 30)


if __name__ == "__main__":
    unittest.main()
