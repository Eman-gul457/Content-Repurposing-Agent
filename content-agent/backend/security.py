import base64
import os
from cryptography.fernet import Fernet

from config.settings import settings


def _get_fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is required")

    # Accept raw 32-byte secrets too and normalize to Fernet format.
    if len(key) == 32 and key.isascii():
        key = base64.urlsafe_b64encode(key.encode("utf-8")).decode("utf-8")

    return Fernet(key.encode("utf-8"))


def encrypt_text(value: str) -> str:
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str) -> str:
    return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def generate_random_secret() -> str:
    return os.urandom(32).hex()