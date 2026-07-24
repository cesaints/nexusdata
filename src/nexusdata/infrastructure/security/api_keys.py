"""Geração e verificação de API keys.

Formato: ``nxk_<prefix>.<secret>``
  * `nxk_<prefix>` (público) localiza a chave no banco — não é secreto.
  * `<secret>` (256 bits de entropia) é o segredo.

Como o segredo já é aleatório de alta entropia, um KDF lento (Argon2) é
desnecessário e prejudicaria a performance (verificação a cada request).
Usa-se SHA-256 + comparação em tempo constante. Apenas o hash é persistido —
o segredo em claro é exibido uma única vez.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from nexusdata.application.ports.models import GeneratedApiKey
from nexusdata.domain.exceptions import AuthenticationError

_KEY_NAMESPACE = "nxk"
_PREFIX_BYTES = 4  # -> 8 chars hex
_SECRET_BYTES = 32  # 256 bits


class ApiKeyServiceImpl:
    def generate(self) -> GeneratedApiKey:
        prefix = f"{_KEY_NAMESPACE}_{secrets.token_hex(_PREFIX_BYTES)}"
        secret = secrets.token_urlsafe(_SECRET_BYTES)
        full_key = f"{prefix}.{secret}"
        return GeneratedApiKey(
            full_key=full_key,
            prefix=prefix,
            secret_hash=self.hash_secret(secret),
        )

    def hash_secret(self, secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def verify(self, secret: str, hashed: str) -> bool:
        computed = self.hash_secret(secret)
        return hmac.compare_digest(computed, hashed)

    def prefix_of(self, full_key: str) -> str:
        return self.split(full_key)[0]

    def split(self, full_key: str) -> tuple[str, str]:
        prefix, sep, secret = full_key.partition(".")
        if not sep or not prefix.startswith(f"{_KEY_NAMESPACE}_") or not secret:
            raise AuthenticationError("formato de API key inválido")
        return prefix, secret
