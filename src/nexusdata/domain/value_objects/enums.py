"""Enumerações do domínio (value objects imutáveis)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Papéis para RBAC (Role-Based Access Control)."""

    ADMIN = "admin"
    """Administrador do tenant: gerencia usuários, API keys e webhooks."""
    USER = "user"
    """Usuário comum: ingere documentos e consulta seus próprios jobs."""


class ApiKeyScope(StrEnum):
    """Escopos de permissão de uma API Key (privilégio mínimo)."""

    DOCUMENTS_WRITE = "documents:write"
    DOCUMENTS_READ = "documents:read"
    JOBS_READ = "jobs:read"
    WEBHOOKS_WRITE = "webhooks:write"


class JobStatus(StrEnum):
    """Estados do ciclo de vida de um job de processamento.

    Transições válidas:
        PENDING    -> PROCESSING | FAILED
        PROCESSING -> COMPLETED | FAILED | RETRYING
        RETRYING   -> PROCESSING | FAILED
        (COMPLETED e FAILED são estados terminais)
    """

    PENDING = "pending"
    PROCESSING = "processing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {JobStatus.COMPLETED, JobStatus.FAILED}


class DocumentType(StrEnum):
    """Tipos de documento não estruturado suportados."""

    CONTRACT = "contract"
    INVOICE = "invoice"
    SUPPORT_TICKET = "support_ticket"
    GENERIC = "generic"


class WebhookEventType(StrEnum):
    """Eventos que disparam entrega de webhook."""

    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
