"""PyInstaller entrypoint for the appliance alert-engine API."""

from __future__ import annotations

import os

import uvicorn

from app.main import app


def main() -> None:
    uvicorn.run(
        app,
        host=os.environ.get("ALERT_ENGINE_HOST", "127.0.0.1"),
        port=int(os.environ.get("ALERT_ENGINE_PORT", "8011")),
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
