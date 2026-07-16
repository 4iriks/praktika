from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies import DB, CurrentUser
from app.schemas.content import FeedbackOut, FeedbackRequest
from app.services.user import delete_feedback, get_feedback, upsert_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackOut,
    summary="Создать или обновить оценку ответа",
    operation_id="sendFeedback",
)
async def send(payload: FeedbackRequest, db: DB, user: CurrentUser) -> FeedbackOut:
    return await upsert_feedback(db, user, payload)


@router.get(
    "/by-response/{response_id}",
    response_model=FeedbackOut | None,
    summary="Получить собственную оценку ответа",
    operation_id="getFeedbackForResponse",
)
async def by_response(response_id: str, db: DB, user: CurrentUser) -> FeedbackOut | None:
    return await get_feedback(db, user, response_id)


@router.delete(
    "/{feedback_id}",
    status_code=204,
    summary="Удалить собственную оценку",
    operation_id="deleteFeedback",
)
async def remove(feedback_id: UUID, db: DB, user: CurrentUser) -> Response:
    await delete_feedback(db, user, feedback_id)
    return Response(status_code=204)
