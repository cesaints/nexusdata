"""Testes da máquina de estados do domínio (ProcessingJob)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nexusdata.domain.entities import ProcessingJob
from nexusdata.domain.exceptions import InvalidStateTransitionError
from nexusdata.domain.value_objects.enums import JobStatus

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _job(**kw: object) -> ProcessingJob:
    return ProcessingJob(tenant_id=uuid4(), document_id=uuid4(), **kw)


def test_happy_path_pending_to_completed() -> None:
    job = _job()
    assert job.status is JobStatus.PENDING
    job.mark_processing(now=NOW)
    assert job.status is JobStatus.PROCESSING
    assert job.attempts == 1
    job.mark_completed(now=NOW, result={"ok": True})
    assert job.status is JobStatus.COMPLETED
    assert job.is_terminal
    assert job.result == {"ok": True}


def test_retry_flow() -> None:
    job = _job()
    job.mark_processing(now=NOW)
    job.mark_retrying(now=NOW, reason="boom")
    assert job.status is JobStatus.RETRYING
    job.mark_processing(now=NOW)
    assert job.attempts == 2


def test_invalid_transition_raises() -> None:
    job = _job()
    job.mark_processing(now=NOW)
    job.mark_completed(now=NOW, result={})
    with pytest.raises(InvalidStateTransitionError):
        job.mark_processing(now=NOW)  # terminal → processing é inválido


def test_cannot_complete_from_pending() -> None:
    job = _job()
    with pytest.raises(InvalidStateTransitionError):
        job.mark_completed(now=NOW, result={})


@pytest.mark.parametrize(
    ("attempts", "maxa", "expected"),
    [(0, 3, True), (2, 3, True), (3, 3, False)],
)
def test_can_retry(attempts: int, maxa: int, expected: bool) -> None:
    job = _job(attempts=attempts, max_attempts=maxa)
    assert job.can_retry is expected
