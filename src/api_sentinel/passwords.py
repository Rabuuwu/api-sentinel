"""Argon2id PHC storage via cryptography, with OWASP's 19 MiB / 2-pass profile."""

import secrets

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


class Passwords:
    def hash(self, password: str) -> str:
        return Argon2id(
            salt=secrets.token_bytes(16), length=32, iterations=2, lanes=1, memory_cost=19456
        ).derive_phc_encoded(password.encode())

    def verify(self, encoded: str, password: str) -> bool:
        try:
            Argon2id.verify_phc_encoded(password.encode(), encoded)
            return True
        except InvalidKey:
            return False

    def check_needs_rehash(self, encoded: str) -> bool:
        return not encoded.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
