"""
Mock data generator for Herald and Herald_Token models.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.models.herald.herald_model import Herald
from app.models.herald.herald_token_model import Herald_Token

from unicron_shared import HeraldStatus


def random_herald_id():
    return str(uuid.uuid4())


def get_mock_herald(i):
    status_cycle = [HeraldStatus.healthy, HeraldStatus.unhealthy, HeraldStatus.unknown]
    status = status_cycle[i % len(status_cycle)]
    health_message = {
        HeraldStatus.healthy: "All systems nominal.",
        HeraldStatus.unhealthy: "Disk space low.",
        HeraldStatus.unknown: "No recent ping.",
    }[status]
    return Herald(
        id=random_herald_id(),
        herald_name=f"mock-herald-{i+1}",
        central_url=f"https://mock-herald-{i+1}.local/callback",
        registered_at=datetime.now(timezone.utc),
        health_status=status,
        last_ping=datetime.now(timezone.utc),
        health_message=health_message,
    )


def get_mock_herald_token(herald):
    # Add more token status variety
    i = int(herald.herald_name.split("-")[-1])
    if i % 5 == 0:
        status = "expired"
        reason = "Token expired"
        created_at = datetime(2022, 1, 1, tzinfo=timezone.utc)
    elif i % 7 == 0:
        status = "revoked"
        reason = "Token revoked by admin"
        created_at = datetime.now(timezone.utc)
    elif herald.health_status == HeraldStatus.healthy:
        status = "active"
        reason = None
        created_at = datetime.now(timezone.utc)
    elif herald.health_status == HeraldStatus.unhealthy:
        status = "pending"
        reason = "Failed health check"
        created_at = datetime.now(timezone.utc)
    else:
        status = "pending"
        reason = "No ping received"
        created_at = datetime.now(timezone.utc)
    return Herald_Token(
        id=herald.herald_id,
        herald_name=herald.herald_name,
        central_url=herald.central_url,
        status=status,
        reason=reason,
        created_at=created_at,
    )


async def main():
    async with SessionLocal() as session:
        heralds = []
        tokens = []
        for i in range(10):
            herald = get_mock_herald(i)
            token = get_mock_herald_token(herald)
            heralds.append(herald)
            tokens.append(token)
        session.add_all(heralds)
        await session.commit()
        print(f"Inserted {len(heralds)} Heralds.")
        session.add_all(tokens)
        await session.commit()
        print(f"Inserted {len(tokens)} Herald_Tokens.")


if __name__ == "__main__":
    asyncio.run(main())
