import asyncio
import subprocess
import sys

from app.core.database import engine


async def _prepare_schema() -> None:
    async with engine.begin() as conn:
        await conn.exec_driver_sql("SELECT 1")
    await engine.dispose()


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> int:
    try:
        asyncio.run(_prepare_schema())
        print("Running alembic upgrade head...")
        _run(["alembic", "upgrade", "head"])
        return 0
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    except Exception as exc:  # pragma: no cover - defensive path for container startup logs
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
