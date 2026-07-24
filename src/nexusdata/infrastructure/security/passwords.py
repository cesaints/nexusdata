"""Hashing de senha com Argon2id (vencedor da Password Hashing Competition).

Argon2id resiste a ataques de GPU e de canal lateral. A verificação é em tempo
constante (a própria lib), e `needs_rehash` permite migrar o custo com o tempo
sem invalidar sessões existentes.
"""

from __future__ import annotations

from argon2 import PasswordHasher as _Argon2
from argon2 import Type
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)


class Argon2PasswordHasher:
    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost: int = 65_536,  # 64 MiB
        parallelism: int = 4,
    ) -> None:
        self._ph = _Argon2(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            type=Type.ID,  # argon2id
        )

    def hash(self, plain: str) -> str:
        return self._ph.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        try:
            return self._ph.verify(hashed, plain)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, hashed: str) -> bool:
        try:
            return self._ph.check_needs_rehash(hashed)
        except InvalidHashError:
            return True
