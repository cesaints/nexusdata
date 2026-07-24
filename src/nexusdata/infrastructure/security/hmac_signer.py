"""Assinatura HMAC-SHA256 dos webhooks (esquema estilo Stripe).

Cabeçalho enviado ao cliente:
    X-Nexus-Signature: t=<timestamp>,v1=<hex_hmac>

O cliente recomputa ``HMAC(secret, f"{t}.{raw_body}")`` e compara em tempo
constante. O `t` protege contra replay (o cliente rejeita timestamps antigos).
"""

from __future__ import annotations

import hashlib
import hmac


class HmacWebhookSigner:
    def sign(self, *, secret: str, payload: bytes, timestamp: str) -> str:
        message = timestamp.encode("utf-8") + b"." + payload
        return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def build_header(self, *, signature: str, timestamp: str) -> str:
        return f"t={timestamp},v1={signature}"
