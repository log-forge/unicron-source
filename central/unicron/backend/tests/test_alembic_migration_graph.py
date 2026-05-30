from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_HEAD = "0001_public_baseline"
VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"
EXPECTED_BASELINE_FILE = "0001_public_baseline.py"
FORBIDDEN_VERSION_TERMS = {
    "acti" + "vation",
    "deployment" + "_key",
    "entitle" + "ment",
    "lic" + "ens",
    "lic" + "ensingconfig",
    "lic" + "ensingstate",
    "lic" + "ensingtoken",
    "pre" + "mium",
    "senti" + "nel",
    "subscription" + "_status",
}


def _literal_assignment(module: ast.Module, name: str) -> Any:
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return ast.literal_eval(node.value)

    raise AssertionError(f"Missing {name!r} assignment")


def _down_revisions(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        assert all(isinstance(item, str) for item in value), value
        return tuple(value)

    raise AssertionError(f"Unsupported down_revision value: {value!r}")


def _migration_graph() -> list[tuple[Path, str, tuple[str, ...]]]:
    graph: list[tuple[Path, str, tuple[str, ...]]] = []

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue

        module = ast.parse(path.read_text(), filename=str(path))
        revision = _literal_assignment(module, "revision")
        down_revision = _literal_assignment(module, "down_revision")

        assert isinstance(revision, str), path
        graph.append((path, revision, _down_revisions(down_revision)))

    return graph


def test_alembic_migration_graph_has_one_valid_head() -> None:
    graph = _migration_graph()
    assert [path.name for path, _, _ in graph] == [EXPECTED_BASELINE_FILE]

    revision_counts = Counter(revision for _, revision, _ in graph)
    duplicate_revisions = {
        revision: [path.name for path, candidate, _ in graph if candidate == revision]
        for revision, count in revision_counts.items()
        if count > 1
    }

    assert duplicate_revisions == {}

    revisions = set(revision_counts)
    missing_down_revisions = {
        (path.name, down_revision)
        for path, _, down_revisions in graph
        for down_revision in down_revisions
        if down_revision not in revisions
    }

    assert missing_down_revisions == set()

    referenced_revisions = {
        down_revision
        for _, _, down_revisions in graph
        for down_revision in down_revisions
    }
    heads = revisions - referenced_revisions

    assert heads == {EXPECTED_HEAD}


def test_alembic_versions_do_not_reference_removed_schema_terms() -> None:
    offenders: dict[str, list[str]] = {}

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue

        text = path.read_text(encoding="utf-8").lower()
        matches = sorted(term for term in FORBIDDEN_VERSION_TERMS if term in text)
        if matches:
            offenders[path.name] = matches

    assert offenders == {}
