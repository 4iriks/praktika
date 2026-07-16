from __future__ import annotations

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
    settings = get_settings()
    async with SessionFactory() as session:
        worker = await session.scalar(
            select(WorkerInstance).order_by(WorkerInstance.heartbeat_at.desc()).limit(1)
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
    }
    print(json.dumps(payload, ensure_ascii=False))
    await engine.dispose()
    if not healthy:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run())
