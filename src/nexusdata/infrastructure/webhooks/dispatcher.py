"""Entrega de webhooks assinada (HMAC) com defesa anti-SSRF.

Cada entrega leva:
  * `X-Nexus-Signature: t=<ts>,v1=<hmac>` — autenticidade + anti-replay.
  * `X-Nexus-Event` e um `id` de evento DETERMINÍSTICO — o cliente deduplica
    reentregas (a entrega é at-least-once).

Anti-SSRF: antes de conectar, o host é resolvido e QUALQUER IP privado,
loopback, link-local (inclui 169.254.169.254 — metadata de nuvem) ou reservado
é recusado.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
from urllib.parse import urlparse
from uuid import UUID

import httpx
import structlog

from nexusdata.application.ports import Clock, UnitOfWorkFactory, WebhookSigner
from nexusdata.domain.value_objects.enums import WebhookEventType

_log = structlog.get_logger(__name__)

_HTTP_ERROR_THRESHOLD = 400


class WebhookDeliveryError(Exception):
    """Uma ou mais entregas falharam — o worker deve reagendar (backoff)."""


class WebhookDispatcher:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        signer: WebhookSigner,
        clock: Clock,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._uow_factory = uow_factory
        self._signer = signer
        self._clock = clock
        self._timeout = timeout_seconds

    async def deliver(self, *, tenant_id: UUID, event: str, job_id: UUID) -> None:
        event_type = WebhookEventType(event)
        async with self._uow_factory() as uow:
            job = await uow.jobs.get(tenant_id, job_id)
            subscribers = await uow.webhooks.list_subscribers(tenant_id, event_type)

        if job is None or not subscribers:
            return

        event_id = self._deterministic_event_id(job_id, event)
        body = json.dumps(
            {
                "id": event_id,
                "type": event,
                "created_at": self._clock.now().isoformat(),
                "data": {
                    "job_id": str(job.id),
                    "document_id": str(job.document_id),
                    "status": job.status.value,
                    "result": job.result,
                    "error": job.error,
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")

        failures: list[str] = []
        timestamp = str(int(self._clock.now().timestamp()))

        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            for endpoint in subscribers:
                try:
                    self._assert_public_url(endpoint.url)
                    signature = self._signer.sign(
                        secret=endpoint.secret, payload=body, timestamp=timestamp
                    )
                    resp = await client.post(
                        endpoint.url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "NexusData-Webhook/1.0",
                            "X-Nexus-Event": event,
                            "X-Nexus-Event-Id": event_id,
                            "X-Nexus-Signature": f"t={timestamp},v1={signature}",
                        },
                    )
                    if resp.status_code >= _HTTP_ERROR_THRESHOLD:
                        failures.append(f"{endpoint.id}:{resp.status_code}")
                except (httpx.HTTPError, WebhookDeliveryError, OSError) as exc:
                    _log.warning(
                        "webhook.delivery_failed",
                        endpoint_id=str(endpoint.id),
                        error=str(exc),
                    )
                    failures.append(f"{endpoint.id}:error")

        if failures:
            raise WebhookDeliveryError(f"falhas de entrega: {failures}")

    @staticmethod
    def _deterministic_event_id(job_id: UUID, event: str) -> str:
        digest = hashlib.sha256(f"{job_id}:{event}".encode()).hexdigest()
        return f"evt_{digest[:32]}"

    @staticmethod
    def _assert_public_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise WebhookDeliveryError("apenas HTTPS é permitido")
        host = parsed.hostname
        if not host:
            raise WebhookDeliveryError("host ausente")
        try:
            infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise WebhookDeliveryError(f"falha de DNS: {host}") from exc

        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global or ip.is_multicast:
                raise WebhookDeliveryError(f"destino não permitido (IP não público): {ip}")
