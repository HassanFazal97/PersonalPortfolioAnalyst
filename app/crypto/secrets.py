"""Encrypt/decrypt broker secrets at rest (SnapTrade userSecret).

Uses Fernet (symmetric AES) with a key from ``BROKER_SECRETS_KEY``. Generate
one with ``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class SecretsError(RuntimeError):
    """Encryption key missing or ciphertext invalid."""


def _fernet(key: str) -> Fernet:
    if not key:
        raise SecretsError("BROKER_SECRETS_KEY is not configured")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise SecretsError("BROKER_SECRETS_KEY is not a valid Fernet key") from exc


def encrypt_secret(key: str, plaintext: str) -> bytes:
    return _fernet(key).encrypt(plaintext.encode())


def decrypt_secret(key: str, ciphertext: bytes) -> str:
    try:
        return _fernet(key).decrypt(ciphertext).decode()
    except InvalidToken as exc:
        raise SecretsError("failed to decrypt broker secret") from exc
