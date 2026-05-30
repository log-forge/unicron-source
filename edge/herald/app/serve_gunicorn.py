"""Gunicorn wrapper that mirrors the current CLI behaviour for Herald.

PyInstaller will freeze this module into a single binary while preserving the
zero-downtime certificate reload flow driven by ``reload-herald.sh``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from gunicorn.app.base import BaseApplication


class HeraldGunicornApplication(BaseApplication):
    """Run the FastAPI app under Gunicorn with Uvicorn workers."""

    def __init__(self, app: Any, options: Dict[str, Any]) -> None:
        self._options = options
        self._application = app
        super().__init__()

    def load_config(self) -> None:  # pragma: no cover - gunicorn hook
        config = {key: value for key, value in self._options.items() if value is not None}
        for key, value in config.items():
            self.cfg.set(key, value)

    def load(self) -> Any:  # pragma: no cover - gunicorn hook
        return self._application


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} must be set")
    return value


def _validate_path(path_str: str, name: str) -> str:
    path = Path(path_str).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{name} not found at {path}")
    return str(path)


def create_options() -> Dict[str, Any]:
    host = os.getenv("HERALD_HOST", "0.0.0.0")
    port = int(os.getenv("HERALD_PORT", "9443"))
    certfile = _validate_path(_require_env("HERALD_CERT"), "HERALD_CERT")
    keyfile = _validate_path(_require_env("HERALD_KEY"), "HERALD_KEY")

    return {
        "bind": f"{host}:{port}",
        "workers": int(os.getenv("HERALD_GUNICORN_WORKERS", "2")),
        "worker_class": "uvicorn.workers.UvicornWorker",
        "certfile": certfile,
        "keyfile": keyfile,
        "pidfile": "/var/run/gunicorn.pid",
        "graceful_timeout": int(os.getenv("HERALD_GUNICORN_GRACEFUL_TIMEOUT", "30")),
        "timeout": int(os.getenv("HERALD_GUNICORN_TIMEOUT", "120")),
        "accesslog": "-",
        "errorlog": "-",
        "loglevel": os.getenv("HERALD_GUNICORN_LOG_LEVEL", "info"),
        # Preload keeps parity with current CLI
        "preload_app": True,
    }


def main() -> None:
    from .main import app

    options = create_options()
    HeraldGunicornApplication(app, options).run()


if __name__ == "__main__":  # pragma: no cover
    main()
