"""Conversão entre entidades de domínio (puras) e models ORM.

Mantém o domínio independente do SQLAlchemy: nenhuma entidade herda de Base.
"""

from __future__ import annotations

from nexusdata.domain.entities import (
    ApiKey,
    Document,
    ProcessingJob,
    Tenant,
    User,
    WebhookEndpoint,
)
from nexusdata.domain.value_objects.enums import (
    ApiKeyScope,
    DocumentType,
    JobStatus,
    Role,
    WebhookEventType,
)
from nexusdata.infrastructure.database.models import (
    ApiKeyModel,
    DocumentModel,
    ProcessingJobModel,
    TenantModel,
    UserModel,
    WebhookEndpointModel,
)


def tenant_to_entity(m: TenantModel) -> Tenant:
    return Tenant(
        id=m.id,
        name=m.name,
        slug=m.slug,
        is_active=m.is_active,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def tenant_to_model(e: Tenant) -> TenantModel:
    return TenantModel(id=e.id, name=e.name, slug=e.slug, is_active=e.is_active)


def user_to_entity(m: UserModel) -> User:
    return User(
        id=m.id,
        tenant_id=m.tenant_id,
        email=m.email,
        password_hash=m.password_hash,
        role=Role(m.role),
        is_active=m.is_active,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def user_to_model(e: User) -> UserModel:
    return UserModel(
        id=e.id,
        tenant_id=e.tenant_id,
        email=e.email,
        password_hash=e.password_hash,
        role=e.role.value,
        is_active=e.is_active,
    )


def api_key_to_entity(m: ApiKeyModel) -> ApiKey:
    return ApiKey(
        id=m.id,
        tenant_id=m.tenant_id,
        name=m.name,
        prefix=m.prefix,
        key_hash=m.key_hash,
        scopes=frozenset(ApiKeyScope(s) for s in m.scopes),
        is_active=m.is_active,
        last_used_at=m.last_used_at,
        expires_at=m.expires_at,
        created_at=m.created_at,
    )


def api_key_to_model(e: ApiKey) -> ApiKeyModel:
    return ApiKeyModel(
        id=e.id,
        tenant_id=e.tenant_id,
        name=e.name,
        prefix=e.prefix,
        key_hash=e.key_hash,
        scopes=sorted(s.value for s in e.scopes),
        is_active=e.is_active,
        last_used_at=e.last_used_at,
        expires_at=e.expires_at,
    )


def document_to_entity(m: DocumentModel) -> Document:
    return Document(
        id=m.id,
        tenant_id=m.tenant_id,
        submitted_by=m.submitted_by,
        doc_type=DocumentType(m.doc_type),
        filename=m.filename,
        content_type=m.content_type,
        size_bytes=m.size_bytes,
        checksum_sha256=m.checksum_sha256,
        storage_key=m.storage_key,
        raw_payload=m.raw_payload,
        created_at=m.created_at,
    )


def document_to_model(e: Document) -> DocumentModel:
    return DocumentModel(
        id=e.id,
        tenant_id=e.tenant_id,
        submitted_by=e.submitted_by,
        doc_type=e.doc_type.value,
        filename=e.filename,
        content_type=e.content_type,
        size_bytes=e.size_bytes,
        checksum_sha256=e.checksum_sha256,
        storage_key=e.storage_key,
        raw_payload=e.raw_payload,
    )


def job_to_entity(m: ProcessingJobModel) -> ProcessingJob:
    return ProcessingJob(
        id=m.id,
        tenant_id=m.tenant_id,
        document_id=m.document_id,
        status=JobStatus(m.status),
        attempts=m.attempts,
        max_attempts=m.max_attempts,
        result=m.result,
        error=m.error,
        idempotency_key=m.idempotency_key,
        created_at=m.created_at,
        started_at=m.started_at,
        finished_at=m.finished_at,
        updated_at=m.updated_at,
    )


def job_to_model(e: ProcessingJob) -> ProcessingJobModel:
    return ProcessingJobModel(
        id=e.id,
        tenant_id=e.tenant_id,
        document_id=e.document_id,
        status=e.status.value,
        attempts=e.attempts,
        max_attempts=e.max_attempts,
        result=e.result,
        error=e.error,
        idempotency_key=e.idempotency_key,
        started_at=e.started_at,
        finished_at=e.finished_at,
    )


def apply_job_entity_to_model(e: ProcessingJob, m: ProcessingJobModel) -> None:
    """Aplica o estado da entidade sobre um model já carregado (update)."""
    m.status = e.status.value
    m.attempts = e.attempts
    m.max_attempts = e.max_attempts
    m.result = e.result
    m.error = e.error
    m.started_at = e.started_at
    m.finished_at = e.finished_at


def webhook_to_entity(m: WebhookEndpointModel) -> WebhookEndpoint:
    return WebhookEndpoint(
        id=m.id,
        tenant_id=m.tenant_id,
        url=m.url,
        secret=m.secret,
        events=frozenset(WebhookEventType(ev) for ev in m.events),
        is_active=m.is_active,
        created_at=m.created_at,
    )


def webhook_to_model(e: WebhookEndpoint) -> WebhookEndpointModel:
    return WebhookEndpointModel(
        id=e.id,
        tenant_id=e.tenant_id,
        url=e.url,
        secret=e.secret,
        events=sorted(ev.value for ev in e.events),
        is_active=e.is_active,
    )
