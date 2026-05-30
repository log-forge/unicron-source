"""PyInstaller entrypoint for the appliance Central backend API."""

from __future__ import annotations

import os

import uvicorn

from app.main import asgi_app


def main() -> None:
    uvicorn.run(
        asgi_app,
        host=os.environ.get("BACKEND_HOST", "127.0.0.1"),
        port=int(os.environ.get("BACKEND_PORT", "8000")),
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
