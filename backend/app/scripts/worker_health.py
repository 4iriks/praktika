from __future__ import annotations

import argparse
import asyncio
import json
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import WorkerInstanceStatus
from app.db.base import utc_now
from app.db.models.operations import WorkerInstance
from app.db.session import SessionFactory, engine


async def run() -> None:
    parser = argparse.ArgumentParser(description="Check PyAnswer worker heartbeat")
    parser.add_argument("--capability")
    args = parser.parse_args()
    settings = get_settings()
    async with SessionFactory() as session:
        statement = select(WorkerInstance)
        if args.capability:
            statement = statement.where(WorkerInstance.capabilities.contains([args.capability]))
        worker = await session.scalar(
            statement.order_by(WorkerInstance.heartbeat_at.desc()).limit(1)
        )
    healthy = bool(
        worker
        and worker.status == WorkerInstanceStatus.RUNNING
        and utc_now() - worker.heartbeat_at
        <= timedelta(seconds=settings.worker_heartbeat_seconds * 2)
    )
    payload = {
        "status": "ONLINE" if healthy else "OFFLINE",
        "instanceId": worker.instance_id if worker else None,
        "heartbeatAt": worker.heartbeat_at.isoformat() if worker else None,
        "currentJobId": str(worker.current_job_id) if worker and worker.current_job_id else None,
        "capability": args.capability,
    }
    print(json.dumps(payload, ensure_ascii=False))
    await engine.dispose()
    if not healthy:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run())
