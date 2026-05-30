"""CA trust material discovery helpers for agent bootstrap/install flows."""

from pathlib import Path

from app.core.config import settings

FINGERPRINT_FILENAME = "root_ca_fingerprint.txt"
ROOT_CA_FILENAME = "root_ca.crt"
DEFAULT_APPLIANCE_DATA_DIR = "/var/lib/unicron"


class CAFingerprintUnavailable(RuntimeError):
    def __init__(self, checked_paths: list[str]) -> None:
        self.checked_paths = checked_paths
        super().__init__("CA fingerprint unavailable")


class CARootUnavailable(RuntimeError):
    def __init__(self, checked_paths: list[str]) -> None:
        self.checked_paths = checked_paths
        super().__init__("Root CA unavailable")


def _append_unique(paths: list[str], candidate: str | Path) -> None:
    value = str(candidate)
    if value and value not in paths:
        paths.append(value)


def _data_root_candidates() -> list[Path]:
    candidates: list[Path] = []
    data_dir = str(settings.UNICRON_DATA_DIR or "").strip()
    if data_dir:
        data_path = Path(data_dir)
        candidates.append(data_path)
        if data_path.name == "backend":
            candidates.append(data_path.parent)
    candidates.append(Path(DEFAULT_APPLIANCE_DATA_DIR))
    return candidates


def root_ca_candidate_paths() -> list[str]:
    """Return candidate root CA certificate files in runtime preference order."""
    candidates: list[str] = []

    root_ca = str(settings.ROOT_CA or "").strip()
    if root_ca:
        _append_unique(candidates, root_ca)

    for data_root in _data_root_candidates():
        _append_unique(candidates, data_root / "pki" / "trust" / ROOT_CA_FILENAME)
        _append_unique(candidates, data_root / "pki" / "certs" / ROOT_CA_FILENAME)

    return candidates


def ca_fingerprint_candidate_paths() -> list[str]:
    """Return candidate fingerprint files in runtime preference order."""
    candidates: list[str] = []

    root_ca = str(settings.ROOT_CA or "").strip()
    if root_ca:
        root_path = Path(root_ca)
        _append_unique(candidates, root_path.with_name(f"{root_path.stem}_fingerprint.txt"))
        _append_unique(candidates, root_path.with_name(FINGERPRINT_FILENAME))

    for data_root in _data_root_candidates():
        _append_unique(candidates, data_root / "pki" / "trust" / FINGERPRINT_FILENAME)
        _append_unique(candidates, data_root / "pki" / "certs" / FINGERPRINT_FILENAME)

    return candidates


def _read_first_nonempty_text(checked_paths: list[str]) -> str | None:
    for candidate in checked_paths:
        path = Path(candidate)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return None


def read_root_ca_pem() -> str:
    checked_paths = root_ca_candidate_paths()
    value = _read_first_nonempty_text(checked_paths)
    if value:
        return value

    raise CARootUnavailable(checked_paths)


def read_ca_fingerprint() -> str:
    checked_paths = ca_fingerprint_candidate_paths()
    value = _read_first_nonempty_text(checked_paths)
    if value:
        return value

    raise CAFingerprintUnavailable(checked_paths)


__all__ = [
    "CAFingerprintUnavailable",
    "CARootUnavailable",
    "ca_fingerprint_candidate_paths",
    "read_ca_fingerprint",
    "read_root_ca_pem",
    "root_ca_candidate_paths",
]
