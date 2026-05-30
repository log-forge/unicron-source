"""Client for querying VictoriaMetrics (Prometheus-compatible)."""

from typing import Any, Dict, List, Optional, Union

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("alert-engine.services.victoria_metrics")


class VictoriaMetricsQueryError(Exception):
    """Error executing VictoriaMetrics query."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class VictoriaMetricsClient:
    """
    Async client for VictoriaMetrics PromQL queries.

    Supports instant and range queries against VictoriaMetrics /api/v1/query endpoints.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the VictoriaMetrics client.

        Args:
            base_url: VictoriaMetrics base URL. Uses settings if not provided.
            timeout: Request timeout in seconds.
        """
        self.base_url = (base_url or settings.VMETRICS_BASE).rstrip("/")
        self.timeout = timeout

    async def query_instant(
        self,
        expr: str,
        time: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute an instant PromQL query.

        Args:
            expr: PromQL expression to evaluate.
            time: Optional evaluation timestamp (Unix seconds). Uses current time if not provided.

        Returns:
            Parsed JSON response from VictoriaMetrics API.
        """
        params: Dict[str, str] = {"query": expr}
        if time is not None:
            params["time"] = str(time)

        url = f"{self.base_url}/api/v1/query"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)

                if resp.status_code >= 400:
                    logger.error(
                        "VictoriaMetrics instant query failed: status=%s body=%s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    raise VictoriaMetricsQueryError(
                        f"Query failed: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                return resp.json()

        except httpx.TimeoutException:
            raise VictoriaMetricsQueryError("Query timed out", status_code=504)
        except httpx.RequestError as e:
            raise VictoriaMetricsQueryError(f"Request failed: {e}")

    async def query_range(
        self,
        expr: str,
        start: float,
        end: float,
        step: str,
    ) -> Dict[str, Any]:
        """
        Execute a range PromQL query.

        Args:
            expr: PromQL expression to evaluate.
            start: Start timestamp (Unix seconds).
            end: End timestamp (Unix seconds).
            step: Query resolution step (e.g., "15s", "1m").

        Returns:
            Parsed JSON response from VictoriaMetrics API.
        """
        params: Dict[str, str] = {
            "query": expr,
            "start": str(start),
            "end": str(end),
            "step": step,
        }

        url = f"{self.base_url}/api/v1/query_range"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)

                if resp.status_code >= 400:
                    logger.error(
                        "VictoriaMetrics range query failed: status=%s body=%s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    raise VictoriaMetricsQueryError(
                        f"Query failed: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                return resp.json()

        except httpx.TimeoutException:
            raise VictoriaMetricsQueryError("Query timed out", status_code=504)
        except httpx.RequestError as e:
            raise VictoriaMetricsQueryError(f"Request failed: {e}")

    def extract_scalar_value(self, response: Dict[str, Any]) -> Optional[float]:
        """
        Extract a single scalar value from a vector query result.

        Args:
            response: VictoriaMetrics API response.

        Returns:
            Float value if exactly one series with one value, None otherwise.
        """
        if response.get("status") != "success":
            return None

        data = response.get("data", {})
        result_type = data.get("resultType")
        result = data.get("result", [])

        # Handle scalar result type
        if result_type == "scalar":
            # Scalar format: [timestamp, "value"]
            if isinstance(result, list) and len(result) == 2:
                try:
                    return float(result[1])
                except (ValueError, TypeError):
                    return None

        # Handle vector result type
        if result_type == "vector":
            # Must have exactly one series for scalar extraction
            if len(result) != 1:
                return None

            series = result[0]
            value = series.get("value", [])

            # Value format: [timestamp, "value"]
            if isinstance(value, list) and len(value) == 2:
                try:
                    return float(value[1])
                except (ValueError, TypeError):
                    return None

        return None

    def extract_latest_value(self, response: Dict[str, Any]) -> Optional[float]:
        """
        Extract the latest value from an instant query result.

        Handles both vector and scalar result types. For vectors with multiple
        series, returns the first series value.

        Args:
            response: VictoriaMetrics API response from instant query.

        Returns:
            Float value if available, None otherwise.
        """
        if response.get("status") != "success":
            return None

        data = response.get("data", {})
        result_type = data.get("resultType")
        result = data.get("result", [])

        # Handle scalar result type
        if result_type == "scalar":
            if isinstance(result, list) and len(result) == 2:
                try:
                    return float(result[1])
                except (ValueError, TypeError):
                    return None

        # Handle vector result type
        if result_type == "vector":
            if not result:
                return None

            # Get first series value
            first_series = result[0]
            value = first_series.get("value", [])

            if isinstance(value, list) and len(value) == 2:
                try:
                    return float(value[1])
                except (ValueError, TypeError):
                    return None

        return None


# Singleton instance for app-wide use
victoria_metrics_client = VictoriaMetricsClient()


__all__ = [
    "VictoriaMetricsClient",
    "VictoriaMetricsQueryError",
    "victoria_metrics_client",
]
