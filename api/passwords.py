import hashlib
import hmac
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type


_PASSWORD_HASHER = PasswordHasher(type=Type.ID)
_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def is_legacy_sha256_hash(stored_hash: str) -> bool:
    return isinstance(stored_hash, str) and bool(
        _SHA256_HEX_PATTERN.fullmatch(stored_hash)
    )


def verify_password(password: str, stored_hash: str) -> bool:
    if not isinstance(password, str) or not isinstance(stored_hash, str):
        return False

    if is_legacy_sha256_hash(stored_hash):
        candidate_hash = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(candidate_hash, stored_hash.lower())

    try:
        return _PASSWORD_HASHER.verify(stored_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_needs_upgrade(stored_hash: str) -> bool:
    if is_legacy_sha256_hash(stored_hash):
        return True
    if not isinstance(stored_hash, str):
        return False

    try:
        return _PASSWORD_HASHER.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return False
