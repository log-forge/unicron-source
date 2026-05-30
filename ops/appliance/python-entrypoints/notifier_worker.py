"""PyInstaller entrypoint for the appliance notifier Celery worker."""

from __future__ import annotations

import os

from celery_app import celery_app


def main() -> None:
    celery_app.worker_main(
        [
            "worker",
            "--loglevel=info",
            "--pool=prefork",
            f"--concurrency={os.environ.get('NOTIFIER_WORKER_CONCURRENCY', '4')}",
        ]
    )


if __name__ == "__main__":
    main()
