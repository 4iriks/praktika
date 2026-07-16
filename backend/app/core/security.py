from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings, get_settings

PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$", re.DOTALL)


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str) -> None:
    if not PASSWORD_PATTERN.match(password):
        raise PasswordPolicyError(
            "Пароль должен содержать минимум 8 символов, строчную и заглавную буквы и цифру"
        )


@dataclass(slots=True)
class PasswordService:
    hasher: PasswordHasher

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> PasswordService:
        value = settings or get_settings()
        return cls(
            PasswordHasher(
                time_cost=value.argon2_time_cost,
                memory_cost=value.argon2_memory_cost,
                parallelism=value.argon2_parallelism,
            )
        )

    def hash(self, password: str) -> str:
        validate_password(password)
        return self.hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self.hasher.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self.hasher.check_needs_rehash(password_hash)


def generate_opaque_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
