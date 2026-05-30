"""PyInstaller entrypoint for the appliance notifier API."""

from __future__ import annotations

import os

import uvicorn

from app.main import app


def main() -> None:
    uvicorn.run(
        app,
        host=os.environ.get("NOTIFIER_HOST", "127.0.0.1"),
        port=int(os.environ.get("NOTIFIER_PORT", "8012")),
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
