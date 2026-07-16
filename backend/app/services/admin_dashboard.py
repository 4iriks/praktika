from __future__ import annotations

from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AccountStatus, DocumentStatus, JobStatus, SearchView, UserRole
from app.db.base import utc_now
from app.db.models.content import Document, DocumentTag, Tag
from app.db.models.identity import Role, SearchHistory, User
from app.db.models.operations import Job, Source
from app.schemas.management import (
    AdminDashboardOut,
    DashboardStatusMetricOut,
    DashboardTagMetricOut,
    DashboardTimeSeriesOut,
)


async def admin_dashboard(db: AsyncSession) -> AdminDashboardOut:
    now = utc_now()
    last_day = now - timedelta(days=1)
    week_start = now - timedelta(days=6)

    user_rows = (
        await db.execute(
            select(Role.code, User.status, func.count(User.id))
            .join(Role, Role.id == User.role_id)
            .group_by(Role.code, User.status)
        )
    ).all()
    users_by_role = {role: 0 for role in UserRole}
    active_users = 0
    blocked_users = 0
    for role, status, count in user_rows:
        users_by_role[UserRole(role)] += count
        if status == AccountStatus.ACTIVE:
            active_users += count
        else:
            blocked_users += count

    document_rows = (
        await db.execute(select(Document.status, func.count(Document.id)).group_by(Document.status))
    ).all()
    document_statuses = [
        DashboardStatusMetricOut(status=DocumentStatus(status), count=count)
        for status, count in document_rows
    ]
    documents_count = sum(item.count for item in document_statuses)
    chunks_count = await db.scalar(select(func.coalesce(func.sum(Document.chunks_count), 0))) or 0

    history_metrics = (
        await db.execute(
            select(
                func.count().filter(SearchHistory.view == SearchView.DOCUMENTS),
                func.count().filter(SearchHistory.view == SearchView.ANSWER),
                func.avg(SearchHistory.took_ms).filter(SearchHistory.view == SearchView.DOCUMENTS),
                func.avg(SearchHistory.took_ms).filter(SearchHistory.view == SearchView.ANSWER),
            ).where(SearchHistory.created_at >= last_day)
        )
    ).one()
    searches_last_day, rag_last_day, average_search, average_rag = history_metrics

    job_metrics = (
        await db.execute(
            select(
                func.count(Job.id),
                func.sum(case((Job.status == JobStatus.COMPLETED, 1), else_=0)),
            ).where(Job.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]))
        )
    ).one()
    finished_jobs, completed_jobs = job_metrics
    success_rate = (completed_jobs or 0) / finished_jobs * 100 if finished_jobs else 0

    daily_rows = (
        await db.execute(
            select(
                func.date_trunc("day", SearchHistory.created_at).label("day"),
                func.count().filter(SearchHistory.view == SearchView.DOCUMENTS),
                func.count().filter(SearchHistory.view == SearchView.ANSWER),
            )
            .where(SearchHistory.created_at >= week_start)
            .group_by("day")
            .order_by("day")
        )
    ).all()
    by_date = {day.date().isoformat(): (searches, rag) for day, searches, rag in daily_rows}
    query_series = []
    for offset in range(7):
        date = (week_start + timedelta(days=offset)).date().isoformat()
        searches, rag = by_date.get(date, (0, 0))
        query_series.append(DashboardTimeSeriesOut(date=date, searches=searches, rag_requests=rag))

    tag_rows = (
        await db.execute(
            select(Tag.normalized_name, func.count(DocumentTag.document_id))
            .join(DocumentTag, DocumentTag.tag_id == Tag.id)
            .group_by(Tag.id, Tag.normalized_name)
            .order_by(func.count(DocumentTag.document_id).desc(), Tag.normalized_name)
            .limit(8)
        )
    ).all()
    last_sync = await db.scalar(select(func.max(Source.last_successful_sync_at)))
    return AdminDashboardOut(
        total_users=active_users + blocked_users,
        active_users=active_users,
        blocked_users=blocked_users,
        users_by_role=users_by_role,
        documents_count=documents_count,
        chunks_count=chunks_count,
        searches_last_day=searches_last_day,
        rag_last_day=rag_last_day,
        average_search_ms=round(float(average_search or 0), 1),
        average_rag_ms=round(float(average_rag or 0), 1),
        job_success_rate=round(success_rate, 1),
        index_size_gb=0,
        last_sync_at=last_sync,
        query_series=query_series,
        document_statuses=document_statuses,
        popular_tags=[DashboardTagMetricOut(tag=tag, count=count) for tag, count in tag_rows],
    )
