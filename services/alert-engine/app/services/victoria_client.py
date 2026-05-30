"""Client for querying VictoriaLogs."""
import json
import re
from typing import Dict, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.victoria_schemas import LogQueryResponse, LogRow

logger = get_logger("alert-engine.services.victoria")


class VictoriaQueryError(Exception):
    """Error executing Victoria query."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class VictoriaLogsClient:
    """
    Async client for VictoriaLogs queries.

    Supports LogsQL queries against VictoriaLogs /select/logsql/query endpoint.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or settings.VLOGS_BASE).rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _split_container_key(container_key: str) -> tuple[str, str]:
        raw = (container_key or "").strip()
        if ":" not in raw:
            return "", ""
        host_id, container_name = raw.split(":", 1)
        return host_id.strip(), container_name.strip()

    def _container_scope_expr(self, container_key: str) -> str:
        host_id, container_name = self._split_container_key(container_key)
        if host_id and container_name:
            host = self._escape(host_id)
            name = self._escape(container_name)
            # Canonical multi-host filter: host + container name.
            # Also include container_key when present in telemetry.
            key = self._escape(f"{host_id}:{container_name}")
            return f'(container_key:"{key}" OR (herald_id:"{host}" AND container_name:"{name}"))'

        raise ValueError(
            "container scope must be host_id:container_name for multi-host evaluation"
        )

    async def query(
        self,
        query: str,
        *,
        limit: int = 1000,
        start: Optional[str] = None,
        end: Optional[str] = None,
        account_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> LogQueryResponse:
        """
        Execute a LogsQL query.

        Args:
            query: LogsQL query string
            limit: Maximum rows to return
            start: Start time (RFC3339 or relative like "5m")
            end: End time (RFC3339 or relative)
            account_id: Optional tenant account ID
            project_id: Optional tenant project ID

        Returns:
            LogQueryResponse with parsed log rows
        """
        form_data = {"query": query, "limit": str(limit)}

        if start:
            form_data["start"] = start
        if end:
            form_data["end"] = end

        headers: Dict[str, str] = {}
        if account_id is not None:
            headers["AccountID"] = str(account_id)
        if project_id is not None:
            headers["ProjectID"] = str(project_id)

        url = f"{self.base_url}/select/logsql/query"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, data=form_data, headers=headers)

                if resp.status_code >= 400:
                    logger.error(
                        "Victoria query failed: status=%s body=%s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    raise VictoriaQueryError(
                        f"Query failed: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                # Parse NDJSON response
                lines = [ln for ln in resp.text.splitlines() if ln.strip()]
                rows = []
                for line in lines:
                    try:
                        data = json.loads(line)
                        rows.append(LogRow.model_validate(data))
                    except Exception as e:
                        logger.warning("Failed to parse log row: %s", e)

                return LogQueryResponse(rows=rows, count=len(rows), query=query)

        except httpx.TimeoutException:
            raise VictoriaQueryError("Query timed out", status_code=504)
        except httpx.RequestError as e:
            raise VictoriaQueryError(f"Request failed: {e}")

    async def query_logs_for_container(
        self,
        container_id: str,
        *,
        pattern: Optional[str] = None,
        window_minutes: int = 5,
        limit: int = 1000,
    ) -> LogQueryResponse:
        """
        Query logs for a specific container.

        Args:
            container_id: Container key in format host_id:container_name
            pattern: Optional text pattern to search for
            window_minutes: Time window to query (default 5 min)
            limit: Maximum rows to return

        Returns:
            LogQueryResponse with matching logs
        """
        # Build LogsQL query
        query_parts = [self._container_scope_expr(container_id)]

        if pattern:
            # Escape special characters in pattern
            escaped = self._escape(pattern)
            query_parts.append(f'_msg:"{escaped}"')

        query = " AND ".join(query_parts)
        start = f"-{window_minutes}m"

        return await self.query(query, limit=limit, start=start)

    async def count_logs_matching(
        self,
        container_id: str,
        pattern: str,
        window_minutes: int = 5,
    ) -> int:
        """
        Count logs matching a pattern for rate limiting checks.

        Args:
            container_id: Container key in format host_id:container_name
            pattern: Text pattern to match
            window_minutes: Time window

        Returns:
            Count of matching log entries
        """
        result = await self.query_logs_for_container(
            container_id,
            pattern=pattern,
            window_minutes=window_minutes,
            limit=10000,  # High limit for counting
        )
        return result.count

    async def check_keyword_match(
        self,
        container_id: str,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        window_minutes: int = 5,
    ) -> tuple[bool, Optional[LogRow]]:
        """
        Check if any logs match a keyword pattern.

        Args:
            container_id: Container key in format host_id:container_name
            pattern: Pattern to search for
            is_regex: Whether pattern is a regex
            case_sensitive: Case-sensitive matching
            window_minutes: Time window

        Returns:
            Tuple of (has_match, first_matching_row)
        """
        scope = self._container_scope_expr(container_id)

        # Build appropriate LogsQL query
        if is_regex:
            regex_pattern = self._escape(pattern)
            query = f'{scope} AND _msg:~"{regex_pattern}"'
        elif case_sensitive:
            literal = self._escape(pattern)
            query = f'{scope} AND _msg:"{literal}"'
        else:
            # Case-insensitive literal match via escaped regex.
            regex_pattern = self._escape(re.escape(pattern))
            query = f'{scope} AND _msg:~"(?i){regex_pattern}"'

        result = await self.query(query, limit=1, start=f"-{window_minutes}m")

        if result.count > 0:
            return True, result.rows[0]
        return False, None

    async def check_absence(
        self,
        container_id: str,
        pattern: Optional[str] = None,
        window_minutes: int = 5,
    ) -> bool:
        """
        Check if expected logs are absent.

        Args:
            container_id: Container key in format host_id:container_name
            pattern: Optional expected pattern
            window_minutes: Time window to check

        Returns:
            True if logs are absent (trigger condition met)
        """
        result = await self.query_logs_for_container(
            container_id,
            pattern=pattern,
            window_minutes=window_minutes,
            limit=1,
        )
        return result.count == 0


# Singleton instance for app-wide use
victoria_logs_client = VictoriaLogsClient()


__all__ = ["VictoriaLogsClient", "VictoriaQueryError", "victoria_logs_client"]
