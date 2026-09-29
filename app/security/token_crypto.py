from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY must be configured before connecting Google accounts")
    return Fernet(key.encode("ascii"))


def encrypt_token(token_json: str) -> str:
    return _fernet().encrypt(token_json.encode("utf-8")).decode("ascii")


def decrypt_token(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")
