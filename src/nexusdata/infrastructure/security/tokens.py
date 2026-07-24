"""Emissão e validação de JWT (HS256), endurecida contra os erros clássicos.

Defesas:
  * Algoritmo FIXO na decodificação (`algorithms=[alg]`) — bloqueia "alg=none"
    e algorithm-confusion.
  * Claims obrigatórias exigidas na validação (exp, iat, nbf, sub, tid, type).
  * `jti` por token (permite revogação/denylist futura).
  * Segredo nunca sai de `SecretStr`.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from uuid import UUID, uuid4

import jwt
from pydantic import SecretStr

from nexusdata.application.ports import Clock
from nexusdata.application.ports.models import TokenClaims
from nexusdata.domain.exceptions import AuthenticationError
from nexusdata.domain.value_objects.enums import Role

_ISSUER = "nexusdata"
_AUDIENCE = "nexusdata-api"


class JwtTokenService:
    def __init__(
        self,
        *,
        secret_key: SecretStr,
        algorithm: str,
        access_ttl_minutes: int,
        refresh_ttl_days: int,
        clock: Clock,
    ) -> None:
        self._secret = secret_key
        self._alg = algorithm
        self._access_ttl = timedelta(minutes=access_ttl_minutes)
        self._refresh_ttl = timedelta(days=refresh_ttl_days)
        self._clock = clock

    def create_access_token(self, *, user_id: UUID, tenant_id: UUID, role: Role) -> str:
        return self._encode(
            sub=user_id,
            tid=tenant_id,
            role=role.value,
            token_type="access",
            ttl=self._access_ttl,  # noqa: S106 - tipo de token
        )

    def create_refresh_token(self, *, user_id: UUID, tenant_id: UUID) -> str:
        return self._encode(
            sub=user_id,
            tid=tenant_id,
            role=None,
            token_type="refresh",
            ttl=self._refresh_ttl,  # noqa: S106 - tipo de token
        )

    def decode(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret.get_secret_value(),
                algorithms=[self._alg],  # lista fixa: bloqueia alg confusion
                audience=_AUDIENCE,
                issuer=_ISSUER,
                options={
                    "require": ["exp", "iat", "nbf", "sub", "tid", "type"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except jwt.PyJWTError as err:
            raise AuthenticationError("token inválido ou expirado") from err

        try:
            token_type = str(payload["type"])
            role_value = payload.get("role")
            role = Role(role_value) if role_value is not None else Role.USER
            return TokenClaims(
                user_id=UUID(str(payload["sub"])),
                tenant_id=UUID(str(payload["tid"])),
                role=role,
                token_type=token_type,
                jti=str(payload.get("jti", "")),
            )
        except (KeyError, ValueError) as err:
            raise AuthenticationError("claims do token malformadas") from err

    def _encode(
        self,
        *,
        sub: UUID,
        tid: UUID,
        role: str | None,
        token_type: str,
        ttl: timedelta,
    ) -> str:
        now = self._clock.now().astimezone(UTC)
        payload: dict[str, object] = {
            "sub": str(sub),
            "tid": str(tid),
            "type": token_type,
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + ttl,
            "jti": uuid4().hex,
        }
        if role is not None:
            payload["role"] = role
        return jwt.encode(payload, self._secret.get_secret_value(), algorithm=self._alg)
