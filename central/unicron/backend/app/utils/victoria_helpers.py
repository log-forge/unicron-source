import re
from typing import Optional

from app.base_schemas import ContainerSelector


# ----- Logs: Query (pipes allowed) -----
def build_logs_expr_for_query(
    sel: ContainerSelector, expr: Optional[str], where: Optional[str], pipes: Optional[str]
) -> str:
    base = sel.logs_predicate()

    if expr and expr.strip():
        expr = expr.strip()
        return f"{base} {expr}" if expr.startswith("|") else f"{base} and ({expr})"

    parts = [base]
    if where and where.strip():
        if "|" in where:
            raise ValueError("`where` must be boolean-only; pipes go into `pipes`.")
        parts.append(f"and ({where.strip()})")

    if pipes and pipes.strip():
        p = pipes.strip()
        parts.append(p if p.startswith("|") else f"| {p}")

    return " ".join(parts)


# ----- Logs: Tail (NO pipes) -----
_NO_PIPES = re.compile(r"\|")


def build_logs_filter_for_tail(sel: ContainerSelector, boolean_filter: Optional[str]) -> str:
    base = sel.logs_predicate()
    if boolean_filter and boolean_filter.strip():
        if _NO_PIPES.search(boolean_filter):
            raise ValueError("Pipes are not allowed for tail; provide a boolean-only filter.")
        return f"{base} and ({boolean_filter.strip()})"
    return base


def inject_container_into_metrics(expr: str, sel: ContainerSelector) -> str:
    """
    Strict policy: callers must include the placeholder `__C__` in the
    MetricsQL expression. The backend replaces it with the container matcher
    derived from `container_key`. This guarantees explicit container scoping.
    """
    matcher = sel.metrics_matcher()
    if matcher == "{}":
        raise ValueError("container_key is required")
    if "__C__" not in expr:
        raise ValueError(
            "Metrics expression must include __C__ to scope by container (e.g. sum by (container_key)(__C__))"
        )
    replaced = expr.replace("__C__", matcher)
    replaced = replaced.replace("{{", "{").replace("}}", "}")
    return replaced
