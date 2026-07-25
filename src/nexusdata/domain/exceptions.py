"""Exceções de domínio — independentes de framework/HTTP.

A camada de apresentação traduz estas exceções em respostas HTTP.
Mensagens aqui NUNCA devem vazar detalhes internos sensíveis.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base para todos os erros de domínio."""

    code: str = "domain_error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__


class EntityNotFoundError(DomainError):
    """Entidade solicitada não existe (ou não pertence ao tenant)."""

    code = "not_found"


class InvalidStateTransitionError(DomainError):
    """Transição de estado inválida em uma máquina de estados do domínio."""

    code = "invalid_state_transition"


class BusinessRuleViolationError(DomainError):
    """Uma regra de negócio foi violada."""

    code = "business_rule_violation"


class AuthenticationError(DomainError):
    """Credenciais inválidas ou ausentes."""

    code = "authentication_failed"


class AuthorizationError(DomainError):
    """Autenticado, porém sem permissão para o recurso/ação."""

    code = "authorization_failed"


class TenantIsolationError(AuthorizationError):
    """Tentativa de acessar recurso de outro tenant (violação de isolamento)."""

    code = "tenant_isolation_violation"


class DuplicateEntityError(DomainError):
    """Conflito de unicidade (ex.: e-mail já cadastrado no tenant)."""

    code = "duplicate_entity"


class RateLimitExceededError(DomainError):
    """Limite de requisições excedido."""

    code = "rate_limit_exceeded"
