from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobEventLevel, JobStage, JobStatus, JobType, WorkerInstanceStatus
from app.db.base import utc_now
from app.db.models.operations import Job, JobEvent, WorkerInstance

type EventScalar = str | int | float | bool | None
type EventValue = EventScalar | list[EventValue] | dict[str, EventValue]

SENSITIVE_KEY_PARTS = (
    "password",
    "salt",
    "digest",
    "session",
    "csrf",
    "cookie",
    "authorization",
    "secret",
    "api_key",
    "apikey",
    "stackexchange_key",
    "stackexchangekey",
    "access_key",
    "accesskey",
    "private_key",
    "privatekey",
    "token",
)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(password|api[_-]?key|key|token|secret|authorization|cookie|csrf)"
    r"(\s*[:=]\s*)([^\s,;&#]+)"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EVENT_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,79}")


class JobQueueStateError(RuntimeError):
    """Raised when a durable queue transition cannot be applied safely."""


@dataclass(frozen=True, slots=True)
class StaleRecoveryResult:
    requeued_job_ids: tuple[UUID, ...]
    failed_job_ids: tuple[UUID, ...]
    cancelled_job_ids: tuple[UUID, ...]

    @property
    def recovered_count(self) -> int:
        return len(self.requeued_job_ids) + len(self.failed_job_ids) + len(self.cancelled_job_ids)


def sanitize_job_event_message(message: str, *, max_length: int = 1000) -> str:
    normalized = CONTROL_CHARACTER_PATTERN.sub("", message).strip()
    normalized = BEARER_PATTERN.sub("Bearer [REDACTED]", normalized)
    normalized = SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        normalized,
    )
    normalized = " ".join(normalized.split())
    return normalized[:max_length]


def sanitize_job_event_value(value: object) -> EventValue:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return sanitize_job_event_message(value, max_length=2000)
    if isinstance(value, datetime):
        return _require_aware_datetime(value).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, EventValue] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if _is_sensitive_event_key(key):
                continue
            result[key] = sanitize_job_event_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [sanitize_job_event_value(item) for item in value]
    return sanitize_job_event_message(str(value), max_length=2000)


def sanitize_job_event_metrics(metrics: Mapping[str, object] | None) -> dict[str, object]:
    if metrics is None:
        return {}
    sanitized = sanitize_job_event_value(metrics)
    if not isinstance(sanitized, dict):
        raise TypeError("Метрики события должны быть объектом")
    return dict(sanitized)


async def add_job_event(
    session: AsyncSession,
    *,
    job_id: UUID,
    level: JobEventLevel | str,
    stage: JobStage | str,
    code: str,
    message: str,
    metrics: Mapping[str, object] | None = None,
    now: datetime | None = None,
) -> JobEvent:
    normalized_code = _normalize_event_code(code)
    safe_message = sanitize_job_event_message(message) or normalized_code
    event = JobEvent(
        job_id=job_id,
        level=JobEventLevel(level).value,
        stage=JobStage(stage).value,
        code=normalized_code,
        message=safe_message,
        metrics=sanitize_job_event_metrics(metrics),
        created_at=_resolve_now(now),
    )
    session.add(event)
    await session.flush()
    return event


async def register_worker_instance(
    session: AsyncSession,
    *,
    name: str,
    instance_id: str,
    capabilities: Collection[str],
    version: str,
    hostname: str,
    pid: int,
    now: datetime | None = None,
) -> WorkerInstance:
    if pid <= 0:
        raise ValueError("PID worker должен быть положительным")
    moment = _resolve_now(now)
    normalized_instance_id = _require_text(instance_id, "instance_id", 200)
    worker = await session.scalar(
        select(WorkerInstance)
        .where(WorkerInstance.instance_id == normalized_instance_id)
        .with_for_update()
    )
    normalized_capabilities = sorted(
        {_require_text(item, "capability", 80) for item in capabilities}
    )
    if worker is None:
        worker = WorkerInstance(
            name=_require_text(name, "name", 200),
            instance_id=normalized_instance_id,
            capabilities=normalized_capabilities,
            version=_require_text(version, "version", 80),
            hostname=_require_text(hostname, "hostname", 255),
            pid=pid,
            status=WorkerInstanceStatus.RUNNING,
            started_at=moment,
            heartbeat_at=moment,
        )
        session.add(worker)
    else:
        worker.name = _require_text(name, "name", 200)
        worker.capabilities = normalized_capabilities
        worker.version = _require_text(version, "version", 80)
        worker.hostname = _require_text(hostname, "hostname", 255)
        worker.pid = pid
        worker.status = WorkerInstanceStatus.RUNNING
        worker.heartbeat_at = _later_datetime(worker.heartbeat_at, moment)
        worker.stopped_at = None
    await session.flush()
    return worker


async def heartbeat_worker_instance(
    session: AsyncSession,
    *,
    worker_id: UUID,
    now: datetime | None = None,
) -> WorkerInstance | None:
    worker = await _lock_worker(session, worker_id)
    if worker is None or worker.status == WorkerInstanceStatus.STOPPED:
        return None
    worker.heartbeat_at = _later_datetime(worker.heartbeat_at, _resolve_now(now))
    await session.flush()
    return worker


async def mark_worker_stopping(
    session: AsyncSession,
    *,
    worker_id: UUID,
    now: datetime | None = None,
) -> WorkerInstance | None:
    worker = await _lock_worker(session, worker_id)
    if worker is None:
        return None
    if worker.status != WorkerInstanceStatus.STOPPED:
        worker.status = WorkerInstanceStatus.STOPPING
        worker.heartbeat_at = _later_datetime(worker.heartbeat_at, _resolve_now(now))
        await session.flush()
    return worker


async def stop_worker_instance(
    session: AsyncSession,
    *,
    worker_id: UUID,
    now: datetime | None = None,
) -> WorkerInstance | None:
    worker = await _lock_worker(session, worker_id)
    if worker is None:
        return None
    if worker.status == WorkerInstanceStatus.STOPPED:
        return worker
    moment = _resolve_now(now)
    worker.status = WorkerInstanceStatus.STOPPED
    worker.heartbeat_at = _later_datetime(worker.heartbeat_at, moment)
    worker.stopped_at = _later_datetime(worker.stopped_at, moment)
    worker.current_job_id = None
    await session.flush()
    return worker


async def claim_next_job(
    session: AsyncSession,
    *,
    worker_id: UUID,
    supported_types: Collection[JobType | str],
    lease_seconds: int,
    now: datetime | None = None,
) -> Job | None:
    if lease_seconds <= 0:
        raise ValueError("Lease должен быть положительным")
    normalized_types = tuple(dict.fromkeys(JobType(item).value for item in supported_types))
    if not normalized_types:
        return None
    moment = _resolve_now(now)
    job = await session.scalar(
        select(Job)
        .where(
            Job.status == JobStatus.QUEUED,
            Job.type.in_(normalized_types),
            or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= moment),
            Job.cancellation_requested_at.is_(None),
            Job.attempt < Job.max_attempts,
        )
        .order_by(Job.created_at, Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    worker = await _lock_worker(session, worker_id)
    if worker is None:
        raise JobQueueStateError("Worker instance не зарегистрирован")
    if worker.status in {WorkerInstanceStatus.STOPPING, WorkerInstanceStatus.STOPPED}:
        return None
    if worker.current_job_id is not None and worker.current_job_id != job.id:
        return None

    job.status = JobStatus.RUNNING
    job.claimed_by = worker.id
    job.claimed_at = moment
    job.heartbeat_at = moment
    job.lease_expires_at = moment + timedelta(seconds=lease_seconds)
    job.attempt += 1
    job.next_attempt_at = None
    job.error_code = None
    job.error_message = None
    if job.started_at is None:
        job.started_at = moment
    worker.status = WorkerInstanceStatus.RUNNING
    worker.current_job_id = job.id
    worker.heartbeat_at = _later_datetime(worker.heartbeat_at, moment)
    worker.stopped_at = None
    await add_job_event(
        session,
        job_id=job.id,
        level=JobEventLevel.INFO,
        stage=job.stage,
        code="JOB_CLAIMED",
        message="Задание захвачено worker-процессом",
        metrics={"workerId": worker.id, "attempt": job.attempt},
        now=moment,
    )
    await session.flush()
    return job


async def heartbeat_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: UUID,
    lease_seconds: int,
    now: datetime | None = None,
) -> Job | None:
    if lease_seconds <= 0:
        raise ValueError("Lease должен быть положительным")
    job = await _lock_running_job_for_worker(session, job_id, worker_id)
    if job is None:
        return None
    moment = _resolve_now(now)
    job.heartbeat_at = _later_datetime(job.heartbeat_at, moment)
    job.lease_expires_at = _later_datetime(
        job.lease_expires_at,
        moment + timedelta(seconds=lease_seconds),
    )
    worker = await _lock_worker(session, worker_id)
    if worker is not None and worker.status != WorkerInstanceStatus.STOPPED:
        worker.heartbeat_at = _later_datetime(worker.heartbeat_at, moment)
        worker.current_job_id = job.id
    await session.flush()
    return job


async def update_job_progress(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: UUID,
    progress: int | None = None,
    processed_items: int | None = None,
    total_items: int | None = None,
    stage: JobStage | str | None = None,
    checkpoint: Mapping[str, object] | None = None,
    request_count_delta: int = 0,
    bytes_received_delta: int = 0,
) -> Job | None:
    if progress is not None and not 0 <= progress <= 100:
        raise ValueError("Progress должен находиться в диапазоне 0..100")
    for name, value in (
        ("processed_items", processed_items),
        ("total_items", total_items),
        ("request_count_delta", request_count_delta),
        ("bytes_received_delta", bytes_received_delta),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{name} не может быть отрицательным")
    job = await _lock_running_job_for_worker(session, job_id, worker_id)
    if job is None:
        return None
    if progress is not None:
        job.progress = max(job.progress, progress)
    if processed_items is not None:
        job.processed_items = max(job.processed_items, processed_items)
    if total_items is not None:
        job.total_items = max(job.total_items, total_items)
    if stage is not None:
        job.stage = JobStage(stage).value
    if checkpoint is not None:
        job.checkpoint = sanitize_job_event_metrics(checkpoint)
    job.request_count += request_count_delta
    job.bytes_received += bytes_received_delta
    await session.flush()
    return job


async def request_job_cancellation(
    session: AsyncSession,
    *,
    job_id: UUID,
    now: datetime | None = None,
) -> Job | None:
    job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        return None
    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
        return job
    if not job.cancellable:
        raise JobQueueStateError("Задание не поддерживает отмену")
    if job.cancellation_requested_at is not None:
        return job
    moment = _resolve_now(now)
    job.cancellation_requested_at = moment
    await add_job_event(
        session,
        job_id=job.id,
        level=JobEventLevel.INFO,
        stage=job.stage,
        code="CANCELLATION_REQUESTED",
        message="Запрошена отмена задания",
        now=moment,
    )
    if job.status == JobStatus.QUEUED or (
        job.status == JobStatus.RUNNING and job.claimed_by is None
    ):
        await _cancel_locked_job(session, job, now=moment)
    await session.flush()
    return job


async def complete_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: UUID,
    result: Mapping[str, object] | None = None,
    now: datetime | None = None,
) -> Job | None:
    job = await _lock_running_job_for_worker(session, job_id, worker_id)
    if job is None:
        return None
    moment = _resolve_now(now)
    job.status = JobStatus.COMPLETED
    job.stage = JobStage.FINALIZING
    job.progress = 100
    job.result = sanitize_job_event_metrics(result)
    job.error_code = None
    job.error_message = None
    job.finished_at = moment
    job.heartbeat_at = _later_datetime(job.heartbeat_at, moment)
    job.lease_expires_at = None
    job.next_attempt_at = None
    job.cancellable = False
    await _release_worker_job(session, worker_id, job.id, moment)
    await add_job_event(
        session,
        job_id=job.id,
        level=JobEventLevel.INFO,
        stage=job.stage,
        code="JOB_COMPLETED",
        message="Задание успешно завершено",
        metrics={"progress": job.progress},
        now=moment,
    )
    await session.flush()
    return job


async def fail_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: UUID,
    error_code: str,
    error_message: str,
    result: Mapping[str, object] | None = None,
    now: datetime | None = None,
) -> Job | None:
    job = await _lock_running_job_for_worker(session, job_id, worker_id)
    if job is None:
        return None
    moment = _resolve_now(now)
    await _fail_locked_job(
        session,
        job,
        worker_id=worker_id,
        error_code=error_code,
        error_message=error_message,
        result=result,
        now=moment,
    )
    await session.flush()
    return job


async def requeue_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: UUID,
    next_attempt_at: datetime,
    error_code: str,
    error_message: str,
    now: datetime | None = None,
) -> Job | None:
    job = await _lock_running_job_for_worker(session, job_id, worker_id)
    if job is None:
        return None
    moment = _resolve_now(now)
    retry_at = max(_require_aware_datetime(next_attempt_at), moment)
    if job.cancellation_requested_at is not None:
        await _cancel_locked_job(session, job, now=moment)
        await session.flush()
        return job
    if job.attempt >= job.max_attempts:
        await _fail_locked_job(
            session,
            job,
            worker_id=worker_id,
            error_code="MAX_ATTEMPTS_EXCEEDED",
            error_message="Исчерпаны попытки выполнения задания",
            result=None,
            now=moment,
        )
        await session.flush()
        return job

    job.status = JobStatus.QUEUED
    job.stage = JobStage.WAITING_BACKOFF if retry_at > moment else JobStage.PREPARING
    job.next_attempt_at = retry_at
    job.error_code = _normalize_event_code(error_code)
    job.error_message = sanitize_job_event_message(error_message)
    job.cancellable = True
    job.claimed_by = None
    job.claimed_at = None
    job.lease_expires_at = None
    job.heartbeat_at = None
    await _release_worker_job(session, worker_id, job.id, moment)
    await add_job_event(
        session,
        job_id=job.id,
        level=JobEventLevel.WARNING,
        stage=job.stage,
        code="RETRY_SCHEDULED",
        message="Повтор задания запланирован",
        metrics={"attempt": job.attempt, "nextAttemptAt": retry_at},
        now=moment,
    )
    await session.flush()
    return job


async def cancel_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: UUID | None = None,
    now: datetime | None = None,
) -> Job | None:
    job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        return None
    if job.status == JobStatus.CANCELLED:
        return job
    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
        raise JobQueueStateError("Завершённое задание нельзя отменить")
    if job.status == JobStatus.RUNNING and (worker_id is None or job.claimed_by != worker_id):
        return None
    await _cancel_locked_job(session, job, now=_resolve_now(now))
    await session.flush()
    return job


async def recover_stale_jobs(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    retry_delay_seconds: int = 0,
    limit: int = 100,
) -> StaleRecoveryResult:
    if retry_delay_seconds < 0:
        raise ValueError("Задержка retry не может быть отрицательной")
    if not 1 <= limit <= 1000:
        raise ValueError("Limit recovery должен находиться в диапазоне 1..1000")
    moment = _resolve_now(now)
    jobs = (
        await session.scalars(
            select(Job)
            .where(
                Job.status == JobStatus.RUNNING,
                or_(Job.lease_expires_at.is_(None), Job.lease_expires_at <= moment),
            )
            .order_by(Job.lease_expires_at.asc().nullsfirst(), Job.id)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
    ).all()
    requeued: list[UUID] = []
    failed: list[UUID] = []
    cancelled: list[UUID] = []
    for job in jobs:
        worker_id = job.claimed_by
        if job.cancellation_requested_at is not None:
            await _cancel_locked_job(session, job, now=moment)
            cancelled.append(job.id)
            continue
        if job.attempt < job.max_attempts:
            job.status = JobStatus.QUEUED
            job.stage = JobStage.WAITING_BACKOFF if retry_delay_seconds else JobStage.PREPARING
            job.next_attempt_at = moment + timedelta(seconds=retry_delay_seconds)
            job.error_code = "STALE_LEASE_RECOVERED"
            job.error_message = "Задание возвращено в очередь после истечения lease"
            job.claimed_by = None
            job.claimed_at = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            job.cancellable = True
            if worker_id is not None:
                await _release_worker_job(session, worker_id, job.id, moment)
            await add_job_event(
                session,
                job_id=job.id,
                level=JobEventLevel.WARNING,
                stage=job.stage,
                code="STALE_JOB_REQUEUED",
                message="Задание возвращено в очередь после истечения lease",
                metrics={"attempt": job.attempt},
                now=moment,
            )
            requeued.append(job.id)
        else:
            await _fail_locked_job(
                session,
                job,
                worker_id=worker_id,
                error_code="WORKER_LEASE_EXPIRED",
                error_message="Worker не продлил lease, попытки исчерпаны",
                result=None,
                now=moment,
            )
            failed.append(job.id)
    await session.flush()
    return StaleRecoveryResult(tuple(requeued), tuple(failed), tuple(cancelled))


async def _lock_worker(session: AsyncSession, worker_id: UUID) -> WorkerInstance | None:
    result = await session.execute(
        select(WorkerInstance).where(WorkerInstance.id == worker_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def _lock_running_job_for_worker(
    session: AsyncSession,
    job_id: UUID,
    worker_id: UUID,
) -> Job | None:
    result = await session.execute(
        select(Job)
        .where(
            Job.id == job_id,
            Job.status == JobStatus.RUNNING,
            Job.claimed_by == worker_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _release_worker_job(
    session: AsyncSession,
    worker_id: UUID,
    job_id: UUID,
    now: datetime,
) -> None:
    worker = await _lock_worker(session, worker_id)
    if worker is not None:
        worker.heartbeat_at = _later_datetime(worker.heartbeat_at, now)
        if worker.current_job_id == job_id:
            worker.current_job_id = None


async def _cancel_locked_job(
    session: AsyncSession,
    job: Job,
    *,
    now: datetime,
) -> None:
    worker_id = job.claimed_by
    job.status = JobStatus.CANCELLED
    job.finished_at = now
    job.cancellation_requested_at = job.cancellation_requested_at or now
    job.heartbeat_at = _later_datetime(job.heartbeat_at, now)
    job.lease_expires_at = None
    job.next_attempt_at = None
    job.cancellable = False
    if worker_id is not None:
        await _release_worker_job(session, worker_id, job.id, now)
    await add_job_event(
        session,
        job_id=job.id,
        level=JobEventLevel.INFO,
        stage=job.stage,
        code="JOB_CANCELLED",
        message="Задание отменено",
        now=now,
    )


async def _fail_locked_job(
    session: AsyncSession,
    job: Job,
    *,
    worker_id: UUID | None,
    error_code: str,
    error_message: str,
    result: Mapping[str, object] | None,
    now: datetime,
) -> None:
    normalized_code = _normalize_event_code(error_code)
    safe_message = sanitize_job_event_message(error_message) or normalized_code
    job.status = JobStatus.FAILED
    job.error_code = normalized_code
    job.error_message = safe_message
    job.result = sanitize_job_event_metrics(result)
    job.finished_at = now
    job.heartbeat_at = _later_datetime(job.heartbeat_at, now)
    job.lease_expires_at = None
    job.next_attempt_at = None
    job.cancellable = False
    if worker_id is not None:
        await _release_worker_job(session, worker_id, job.id, now)
    await add_job_event(
        session,
        job_id=job.id,
        level=JobEventLevel.ERROR,
        stage=job.stage,
        code="JOB_FAILED",
        message=safe_message,
        metrics={"errorCode": normalized_code, "attempt": job.attempt},
        now=now,
    )


def _resolve_now(value: datetime | None) -> datetime:
    return _require_aware_datetime(value or utc_now())


def _require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime должен содержать timezone")
    return value.astimezone(UTC)


def _later_datetime(current: datetime | None, candidate: datetime) -> datetime:
    normalized = _require_aware_datetime(candidate)
    if current is None:
        return normalized
    return max(_require_aware_datetime(current), normalized)


def _normalize_event_code(code: str) -> str:
    normalized = code.strip().upper()
    if EVENT_CODE_PATTERN.fullmatch(normalized) is None:
        raise ValueError("Код события должен состоять из A-Z, 0-9 и underscore")
    return normalized


def _is_sensitive_event_key(key: str) -> bool:
    normalized = key.casefold()
    compacted = re.sub(r"[^a-z0-9]", "", normalized)
    return compacted == "key" or any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _require_text(value: str, field: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"Поле {field} должно содержать от 1 до {maximum} символов")
    return normalized
