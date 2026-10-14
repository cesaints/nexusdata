"""Error translation and session cleanup at both Unit of Work boundaries."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexusdata.domain.entities import ProcessingJob
from nexusdata.domain.exceptions import DuplicateEntityError
from nexusdata.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.unit


class PgConstraintError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("synthetic constraint violation")
        if sqlstate is not None:
            self.sqlstate = sqlstate


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def uow(session: AsyncMock) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(MagicMock(return_value=session))


@pytest.mark.parametrize("error_stage", ["flush", "commit"])
@pytest.mark.parametrize("sqlstate", ["23505", "23503", "23502", "23514", None])
async def test_integrity_error_translation_and_cleanup(
    session: AsyncMock,
    uow: SqlAlchemyUnitOfWork,
    error_stage: str,
    sqlstate: str | None,
) -> None:
    error = IntegrityError("INSERT", {}, PgConstraintError(sqlstate))
    getattr(session, error_stage).side_effect = error
    expected = DuplicateEntityError if sqlstate == "23505" else IntegrityError

    with pytest.raises(expected) as caught:
        async with uow:
            if error_stage == "flush":
                await uow.jobs.add(ProcessingJob(tenant_id=uuid4(), document_id=uuid4()))
            await uow.commit()

    if sqlstate == "23505":
        assert caught.value.__cause__ is error
    else:
        assert caught.value is error
    session.rollback.assert_awaited()
    session.close.assert_awaited_once()
    if error_stage == "flush":
        session.commit.assert_not_awaited()
    else:
        session.commit.assert_awaited_once()
    with pytest.raises(RuntimeError, match="fora do"):
        _ = uow.session


async def test_successful_commit_closes_without_rollback(
    session: AsyncMock, uow: SqlAlchemyUnitOfWork
) -> None:
    async with uow:
        await uow.commit()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()


async def test_caught_flush_error_is_not_translated_after_context(
    session: AsyncMock, uow: SqlAlchemyUnitOfWork
) -> None:
    error = IntegrityError("INSERT", {}, PgConstraintError("23505"))
    session.flush.side_effect = error
    async with uow:
        with pytest.raises(IntegrityError) as caught:
            await uow.jobs.add(ProcessingJob(tenant_id=uuid4(), document_id=uuid4()))
        assert caught.value is error
        await uow.rollback()
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
    session.commit.assert_not_awaited()


async def test_unrelated_error_is_preserved_and_closes(
    session: AsyncMock, uow: SqlAlchemyUnitOfWork
) -> None:
    error = ValueError("synthetic error")
    with pytest.raises(ValueError) as caught:
        async with uow:
            raise error
    assert caught.value is error
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
