"""Composition Root — cria e conecta TODAS as dependências (DI manual).

Um único lugar decide quais implementações concretas satisfazem os ports. A
API monta o container no lifespan; o worker monta no boot do processo. Trocar
uma tecnologia (ex.: outro broker) é uma mudança pontual aqui.
"""

from __future__ import annotations

from nexusdata.application.services import (
    ApiKeyManagementService,
    AuthService,
    DocumentIngestionService,
    DocumentProcessingService,
    JobQueryService,
    WebhookManagementService,
)
from nexusdata.infrastructure.ai.factory import build_processor
from nexusdata.infrastructure.cache import (
    IdempotencyStore,
    RedisRateLimiter,
    create_redis,
)
from nexusdata.infrastructure.clock import SystemClock
from nexusdata.infrastructure.config import Settings
from nexusdata.infrastructure.database.engine import (
    create_engine,
    create_session_factory,
)
from nexusdata.infrastructure.database.unit_of_work import (
    SqlAlchemyUnitOfWorkFactory,
)
from nexusdata.infrastructure.messaging import (
    CeleryEventPublisher,
    RedisJobNotifier,
)
from nexusdata.infrastructure.security import (
    ApiKeyServiceImpl,
    Argon2PasswordHasher,
    HmacWebhookSigner,
    JwtTokenService,
)
from nexusdata.infrastructure.webhooks import WebhookDispatcher


class Container:
    """Container de dependências do processo (API ou worker)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.clock = SystemClock()

        # --- Persistência ---
        self.engine = create_engine(settings)
        self.session_factory = create_session_factory(self.engine)
        self.uow_factory = SqlAlchemyUnitOfWorkFactory(self.session_factory)

        # --- Estado / cache (Redis) ---
        self.redis = create_redis(settings)
        self.rate_limiter = RedisRateLimiter(self.redis)
        self.idempotency = IdempotencyStore(self.redis)
        self.notifier = RedisJobNotifier(self.redis)

        # --- Segurança ---
        self.password_hasher = Argon2PasswordHasher()
        self.api_key_service = ApiKeyServiceImpl()
        self.hmac_signer = HmacWebhookSigner()
        self.token_service = JwtTokenService(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            access_ttl_minutes=settings.access_token_expire_minutes,
            refresh_ttl_days=settings.refresh_token_expire_days,
            clock=self.clock,
        )

        # --- Mensageria (import tardio evita ciclo com o worker) ---
        from nexusdata.worker.celery_app import celery_app

        self.publisher = CeleryEventPublisher(celery_app)

        # --- Processamento (IA plugável, já resiliente) ---
        self.processor = build_processor(settings)
        self.webhook_dispatcher = WebhookDispatcher(
            uow_factory=self.uow_factory,
            signer=self.hmac_signer,
            clock=self.clock,
            timeout_seconds=settings.webhook_timeout_seconds,
        )

        # --- Casos de uso (Application) ---
        self.auth_service = AuthService(
            uow_factory=self.uow_factory,
            hasher=self.password_hasher,
            tokens=self.token_service,
            clock=self.clock,
            access_ttl_seconds=settings.access_token_expire_minutes * 60,
        )
        self.document_service = DocumentIngestionService(
            uow_factory=self.uow_factory,
            publisher=self.publisher,
            clock=self.clock,
        )
        self.job_service = JobQueryService(uow_factory=self.uow_factory)
        self.api_key_management = ApiKeyManagementService(
            uow_factory=self.uow_factory,
            api_keys=self.api_key_service,
            clock=self.clock,
        )
        self.webhook_management = WebhookManagementService(
            uow_factory=self.uow_factory, clock=self.clock
        )
        self.processing_service = DocumentProcessingService(
            uow_factory=self.uow_factory,
            processor=self.processor,
            publisher=self.publisher,
            notifier=self.notifier,
            clock=self.clock,
        )

    async def aclose(self) -> None:
        await self.engine.dispose()
        await self.redis.aclose()
