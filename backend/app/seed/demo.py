from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import (
    AccountStatus,
    AuditAction,
    AuditEntityType,
    AuditOutcome,
    DeduplicationStatus,
    DocumentStatus,
    IndexStatus,
    JobStage,
    JobStatus,
    JobType,
    ProcessingStatus,
    UserRole,
)
from app.core.security import PasswordService
from app.db.base import utc_now
from app.db.models.content import Answer, Document, DocumentChunk, DocumentTag, Tag
from app.db.models.identity import (
    Feedback,
    Role,
    SavedDocument,
    SearchHistory,
    User,
    UserPreference,
)
from app.db.models.operations import AuditEvent, Job, Source
from app.db.repositories.users import normalize_email
from app.processing.chunking import stable_chunk_key
from app.seed.bootstrap import bootstrap_all

DEMO_PASSWORD = "Demo123!"
DEMO_USERS = (
    ("user@pyanswer.local", "Демонстрационный пользователь", UserRole.USER, AccountStatus.ACTIVE),
    ("editor@pyanswer.local", "Демонстрационный редактор", UserRole.EDITOR, AccountStatus.ACTIVE),
    (
        "admin@pyanswer.local",
        "Демонстрационный администратор",
        UserRole.ADMIN,
        AccountStatus.ACTIVE,
    ),
)
TOPICS = (
    ("Удаление дубликатов из списка", "lists", "list(dict.fromkeys(values))"),
    ("Безопасное объединение словарей", "dict", "merged = first | second"),
    ("Запуск нескольких async задач", "asyncio", "await asyncio.gather(*tasks)"),
    ("Разница gather и create_task", "asyncio", "task = asyncio.create_task(work())"),
    ("Чтение большого CSV через pandas", "pandas", "pd.read_csv(path, chunksize=10000)"),
    ("Оптимизация Django queryset", "django", "Book.objects.select_related('author')"),
    ("Обработка JSON во Flask", "flask", "payload = request.get_json()"),
    ("Dependency injection в FastAPI", "fastapi", "Depends(get_service)"),
    ("Ожидание элемента Selenium", "selenium", "WebDriverWait(driver, 10)"),
    ("Векторизация NumPy", "numpy", "result = array * 2"),
    ("Timeout и retry в requests", "requests", "requests.get(url, timeout=5)"),
    ("classmethod и staticmethod", "classes", "@classmethod"),
    ("Декоратор с аргументами", "decorators", "@wraps(function)"),
    ("Собственные исключения", "exceptions", "class DomainError(Exception): pass"),
    ("Причины ModuleNotFoundError", "imports", "python -m package.module"),
    ("Создание виртуального окружения", "venv", "python -m venv .venv"),
    ("AsyncSession в SQLAlchemy", "sqlalchemy", "async with session.begin():"),
    ("Параметризация pytest", "pytest", "@pytest.mark.parametrize"),
    ("Контекстный менеджер", "python", "with open(path) as stream:"),
    ("Сопоставление структур pattern matching", "python", "match value:"),
)


async def ensure_demo_user(
    db: AsyncSession,
    roles: dict[UserRole, Role],
    password_hash: str,
    email: str,
    name: str,
    role: UserRole,
    status: AccountStatus,
    offset: int,
) -> User:
    existing = await db.scalar(select(User).where(User.normalized_email == normalize_email(email)))
    if existing is not None:
        return existing
    now = utc_now()
    user = User(
        role=roles[role],
        name=name,
        email=email,
        normalized_email=normalize_email(email),
        password_hash=password_hash,
        status=status,
        account_version=1,
        registered_at=now - timedelta(days=offset * 17),
        last_active_at=now - timedelta(hours=offset * 7),
        preferences=UserPreference(),
    )
    db.add(user)
    await db.flush()
    return user


async def seed_users(db: AsyncSession, settings: Settings) -> dict[str, User]:
    roles = {UserRole(role.code): role for role in (await db.scalars(select(Role))).all()}
    password_hash = PasswordService.from_settings(settings).hash(DEMO_PASSWORD)
    users: dict[str, User] = {}
    for offset, (email, name, role, status) in enumerate(DEMO_USERS, start=1):
        users[email] = await ensure_demo_user(
            db, roles, password_hash, email, name, role, status, offset
        )
    for index in range(1, 11):
        email = f"developer{index}@pyanswer.local"
        role = UserRole.EDITOR if index in {7, 8} else UserRole.USER
        if index == 10:
            role = UserRole.ADMIN
        status = AccountStatus.BLOCKED if index in {4, 9} else AccountStatus.ACTIVE
        users[email] = await ensure_demo_user(
            db,
            roles,
            password_hash,
            email,
            f"Python разработчик {index}",
            role,
            status,
            index + 3,
        )
    return users


async def seed_documents(db: AsyncSession, source: Source) -> list[Document]:
    existing = (await db.scalars(select(Document).where(Document.source_id == source.id))).all()
    if existing:
        return list(existing)
    tags: dict[str, Tag] = {}
    documents: list[Document] = []
    now = utc_now()
    statuses = [DocumentStatus.ACTIVE] * 14 + [
        DocumentStatus.OUTDATED,
        DocumentStatus.HIDDEN,
        DocumentStatus.PENDING,
        DocumentStatus.FAILED,
        DocumentStatus.ACTIVE,
        DocumentStatus.ACTIVE,
    ]
    for index, (title, tag_name, code) in enumerate(TOPICS, start=1):
        document = Document(
            source_id=source.id,
            external_id=f"stage4-{1000 + index}",
            source_url=f"https://ru.stackoverflow.com/questions/{1000 + index}",
            original_title=title,
            normalized_title=title,
            question_text=(
                f"Как правильно решить задачу «{title.lower()}» в Python?\n\n```python\n{code}\n```"
            ),
            author_name=f"Автор {index}",
            published_at=now - timedelta(days=index * 21),
            source_updated_at=now - timedelta(days=index),
            score=3 + index * 2,
            views_count=500 + index * 183,
            answers_count=2,
            accepted_answer_external_id=f"answer-{index}-1" if index % 4 else None,
            has_code=True,
            status=statuses[index - 1],
            bm25_status=IndexStatus.NOT_INDEXED,
            vector_status=IndexStatus.NOT_INDEXED,
            chunks_count=1,
            content_hash=hashlib.sha256(f"document-{index}".encode()).hexdigest(),
            canonical_text=(
                f"# {title}\n\nТеги: python, {tag_name}\n\n## Вопрос\n\n"
                f"Как правильно решить задачу «{title.lower()}» в Python?\n\n"
                f"## Принятый ответ\n\nИспользуйте стандартные средства Python.\n\n"
                f"```python\n{code}\n```"
            ),
            metadata_hash=hashlib.sha256(f"metadata-{index}".encode()).hexdigest(),
            processing_status=(
                ProcessingStatus.FAILED
                if statuses[index - 1] == DocumentStatus.FAILED
                else ProcessingStatus.CHUNKED
            ),
            deduplication_status=DeduplicationStatus.UNIQUE,
            processing_error=(
                "Ошибка подготовки" if statuses[index - 1] == DocumentStatus.FAILED else None
            ),
            editorial_note="",
            hidden_reason="Проверка модерации"
            if statuses[index - 1] == DocumentStatus.HIDDEN
            else None,
            failure_reason="Ошибка подготовки"
            if statuses[index - 1] == DocumentStatus.FAILED
            else None,
            last_indexed_at=None,
            last_synced_at=now - timedelta(hours=index * 3),
            version=1,
        )
        db.add(document)
        await db.flush()
        tag = tags.get(tag_name)
        if tag is None:
            tag = Tag(normalized_name=tag_name, display_name=tag_name)
            db.add(tag)
            await db.flush()
            tags[tag_name] = tag
        python_tag = tags.get("python")
        if python_tag is None:
            python_tag = Tag(normalized_name="python", display_name="python")
            db.add(python_tag)
            await db.flush()
            tags["python"] = python_tag
        document_tags = {
            python_tag.id: DocumentTag(document_id=document.id, tag_id=python_tag.id),
            tag.id: DocumentTag(document_id=document.id, tag_id=tag.id),
        }
        db.add_all(
            [
                *document_tags.values(),
                Answer(
                    document_id=document.id,
                    external_id=f"answer-{index}-1",
                    author_name=f"Эксперт {index}",
                    body_text=f"Используйте стандартные средства Python.\n\n```python\n{code}\n```",
                    score=10 + index,
                    is_accepted=index % 4 != 0,
                    published_at=document.published_at + timedelta(hours=2),
                ),
                Answer(
                    document_id=document.id,
                    external_id=f"answer-{index}-2",
                    author_name=f"Участник {index}",
                    body_text="Альтернативный вариант с проверкой входных данных.",
                    score=index,
                    is_accepted=False,
                    published_at=document.published_at + timedelta(hours=5),
                ),
            ]
        )
        chunk_text = (
            f"Как правильно решить задачу «{title.lower()}» в Python?\n\n"
            f"Используйте стандартные средства Python.\n\n```python\n{code}\n```"
        )
        chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
        db.add(
            DocumentChunk(
                chunk_key=stable_chunk_key(document.id, 1, 1, chunk_hash),
                document_id=document.id,
                document_version=1,
                ordinal=1,
                section_type="MIXED",
                text=chunk_text,
                contextual_text=(
                    f"# {title}\nТеги: python, {tag_name}\nРаздел: Смешанный фрагмент\n\n"
                    f"{chunk_text}"
                ),
                content_hash=chunk_hash,
                token_count=len(chunk_text.split()),
                character_count=len(chunk_text),
                has_code=True,
                language="python",
            )
        )
        documents.append(document)
    source.documents_count = len(documents)
    await db.flush()
    return documents


async def seed_activity(
    db: AsyncSession,
    users: dict[str, User],
    documents: list[Document],
    source: Source,
) -> None:
    user = users["user@pyanswer.local"]
    admin = users["admin@pyanswer.local"]
    if not await db.scalar(select(SearchHistory.id).limit(1)):
        for index in range(8):
            db.add(
                SearchHistory(
                    user_id=user.id,
                    query=TOPICS[index][0],
                    view="answer" if index % 3 == 0 else "documents",
                    mode="hybrid",
                    filters={
                        "tags": [TOPICS[index][1]],
                        "minScore": 0,
                        "acceptedOnly": False,
                        "hasCodeOnly": False,
                    },
                    sort="relevance",
                    page_size=10,
                    result_count=5 + index,
                    took_ms=90 + index * 30,
                    answer_preview="Краткий демонстрационный ответ" if index % 3 == 0 else None,
                    insufficient_context=False if index % 3 == 0 else None,
                    created_at=utc_now() - timedelta(hours=index * 9),
                )
            )
    if not await db.scalar(select(SavedDocument.user_id).limit(1)):
        db.add_all(
            [SavedDocument(user_id=user.id, document_id=document.id) for document in documents[:3]]
        )
    if not await db.scalar(select(Feedback.id).limit(1)):
        db.add(
            Feedback(
                user_id=user.id,
                response_id="seed-response-1",
                value="positive",
                question="Как удалить дубликаты?",
            )
        )
    if not await db.scalar(select(Job.id).limit(1)):
        now = utc_now()
        jobs = [
            Job(
                type=JobType.SOURCE_SYNC,
                status=JobStatus.RUNNING,
                stage=JobStage.CRAWLING,
                progress=37,
                processed_items=9250,
                total_items=25000,
                source_id=source.id,
                created_by=admin.id,
                cancellable=True,
                started_at=now - timedelta(minutes=12),
            ),
            Job(
                type=JobType.DOCUMENT_REINDEX,
                status=JobStatus.QUEUED,
                stage=JobStage.PREPARING,
                progress=0,
                total_items=1,
                document_id=documents[0].id,
                source_id=source.id,
                created_by=admin.id,
                cancellable=True,
            ),
            Job(
                type=JobType.FULL_REINDEX,
                status=JobStatus.COMPLETED,
                stage=JobStage.FINALIZING,
                progress=100,
                processed_items=20,
                total_items=20,
                created_by=admin.id,
                cancellable=False,
                started_at=now - timedelta(days=2),
                finished_at=now - timedelta(days=2, minutes=-4),
            ),
            Job(
                type=JobType.SOURCE_SYNC,
                status=JobStatus.FAILED,
                stage=JobStage.CRAWLING,
                progress=18,
                processed_items=4500,
                total_items=25000,
                source_id=source.id,
                created_by=admin.id,
                cancellable=False,
                error_code="SOURCE_UNAVAILABLE",
                error_message="Демонстрационная ошибка источника",
                started_at=now - timedelta(days=3),
                finished_at=now - timedelta(days=3, minutes=-2),
            ),
            Job(
                type=JobType.HEALTH_CHECK,
                status=JobStatus.CANCELLED,
                stage=JobStage.PREPARING,
                progress=0,
                created_by=admin.id,
                cancellable=False,
                finished_at=now - timedelta(days=4),
            ),
        ]
        db.add_all(jobs)
        await db.flush()
        source.current_job_id = jobs[0].id
        source.status = "SYNCING"
    if not await db.scalar(select(AuditEvent.id).limit(1)):
        db.add(
            AuditEvent(
                actor_user_id=admin.id,
                actor_name=admin.name,
                actor_role=UserRole.ADMIN,
                action=AuditAction.START_SOURCE_SYNC,
                entity_type=AuditEntityType.SOURCE,
                entity_id=str(source.id),
                entity_label=source.name,
                outcome=AuditOutcome.SUCCESS,
                ip_address="127.0.0.1",
                request_id="seed-stage4",
                summary="Создано демонстрационное задание синхронизации",
                metadata_json={"seed": True},
            )
        )
    await db.flush()


async def seed_demo_data(db: AsyncSession, settings: Settings) -> None:
    if settings.app_env == "production":
        raise RuntimeError("Demo seed запрещён в production")
    await bootstrap_all(db, settings)
    users = await seed_users(db, settings)
    source = await db.scalar(select(Source).where(Source.name == "Stack Overflow на русском"))
    if source is None:
        raise RuntimeError("Основной источник не создан")
    documents = await seed_documents(db, source)
    await seed_activity(db, users, documents, source)
