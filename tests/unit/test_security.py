"""Testes de segurança: Argon2, JWT (hardening), API keys, HMAC."""

from __future__ import annotations

import jwt
import pytest
from pydantic import SecretStr

from nexusdata.domain.exceptions import AuthenticationError
from nexusdata.infrastructure.security import (
    ApiKeyServiceImpl,
    Argon2PasswordHasher,
    HmacWebhookSigner,
    JwtTokenService,
)
from nexusdata.domain.value_objects.enums import Role
from tests.fakes import FakeClock

pytestmark = pytest.mark.unit


# ---------------- Argon2 ----------------
def test_argon2_roundtrip() -> None:
    h = Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    hashed = h.hash("s3nha-forte")
    assert h.verify("s3nha-forte", hashed) is True
    assert h.verify("errada", hashed) is False
    assert h.needs_rehash(hashed) is False


def test_argon2_verify_handles_garbage() -> None:
    h = Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    assert h.verify("x", "not-a-valid-hash") is False


# ---------------- JWT ----------------
def _tokens() -> JwtTokenService:
    return JwtTokenService(
        secret_key=SecretStr("k" * 40),
        algorithm="HS256",
        access_ttl_minutes=15,
        refresh_ttl_days=7,
        clock=FakeClock(),
    )


def test_jwt_roundtrip() -> None:
    from uuid import uuid4

    svc = _tokens()
    uid, tid = uuid4(), uuid4()
    token = svc.create_access_token(user_id=uid, tenant_id=tid, role=Role.ADMIN)
    claims = svc.decode(token)
    assert claims.user_id == uid
    assert claims.tenant_id == tid
    assert claims.role is Role.ADMIN
    assert claims.token_type == "access"


def test_jwt_rejects_alg_none() -> None:
    # Ataque clássico: token não assinado (alg=none) deve ser recusado.
    from uuid import uuid4

    svc = _tokens()
    forged = jwt.encode(
        {
            "sub": str(uuid4()),
            "tid": str(uuid4()),
            "type": "access",
            "iss": "nexusdata",
            "aud": "nexusdata-api",
            "iat": 0,
            "nbf": 0,
            "exp": 9999999999,
        },
        key=None,
        algorithm="none",
    )
    with pytest.raises(AuthenticationError):
        svc.decode(forged)


def test_jwt_rejects_wrong_secret() -> None:
    from uuid import uuid4

    svc = _tokens()
    token = svc.create_access_token(user_id=uuid4(), tenant_id=uuid4(), role=Role.USER)
    other = JwtTokenService(
        secret_key=SecretStr("DIFERENTE" * 5),
        algorithm="HS256",
        access_ttl_minutes=15,
        refresh_ttl_days=7,
        clock=FakeClock(),
    )
    with pytest.raises(AuthenticationError):
        other.decode(token)


def test_jwt_expired() -> None:
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    # Emite com o relógio 1h no passado → exp já vencido no tempo real.
    past = FakeClock(datetime.now(UTC) - timedelta(hours=1))
    svc = JwtTokenService(
        secret_key=SecretStr("k" * 40),
        algorithm="HS256",
        access_ttl_minutes=15,
        refresh_ttl_days=7,
        clock=past,
    )
    token = svc.create_access_token(user_id=uuid4(), tenant_id=uuid4(), role=Role.USER)
    with pytest.raises(AuthenticationError):
        svc.decode(token)


# ---------------- API keys ----------------
def test_api_key_generate_verify() -> None:
    svc = ApiKeyServiceImpl()
    gen = svc.generate()
    prefix, secret = svc.split(gen.full_key)
    assert prefix == gen.prefix
    assert svc.verify(secret, gen.secret_hash) is True
    assert svc.verify("errado", gen.secret_hash) is False


def test_api_key_malformed_raises() -> None:
    svc = ApiKeyServiceImpl()
    with pytest.raises(AuthenticationError):
        svc.split("sem-ponto-nem-prefixo")


# ---------------- HMAC ----------------
def test_hmac_deterministic_and_secret_sensitive() -> None:
    signer = HmacWebhookSigner()
    a = signer.sign(secret="s1", payload=b"body", timestamp="100")
    b = signer.sign(secret="s1", payload=b"body", timestamp="100")
    c = signer.sign(secret="s2", payload=b"body", timestamp="100")
    assert a == b
    assert a != c
