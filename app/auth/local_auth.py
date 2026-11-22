import base64
import hashlib
import hmac
import json
import secrets
import time
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"pbkdf2:sha256:100000${salt}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plain password against the stored PBKDF2 hash."""
    if not hashed or "$" not in hashed:
        return False
    try:
        method, salt, key_hex = hashed.split("$")
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return secrets.compare_digest(key.hex(), key_hex)
    except Exception:
        return False


def create_access_token(email: str, expires_in_seconds: int = 86400) -> str:
    """Generate a signed, tamper-proof session token with expiry."""
    secret = get_settings().secret_key.encode("utf-8")
    payload = {
        "sub": email.lower().strip(),
        "exp": int(time.time()) + expires_in_seconds
    }
    b64_data = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(secret, b64_data.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_data}.{sig}"


def decode_access_token(token: str) -> str | None:
    """Verify signature and expiration, returning user email if valid."""
    if not token or "." not in token:
        return None
    try:
        secret = get_settings().secret_key.encode("utf-8")
        b64_data, sig = token.split(".", 1)
        expected_sig = hmac.new(secret, b64_data.encode("utf-8"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected_sig):
            return None
        # Add padding back if necessary
        padded = b64_data + "=" * (-len(b64_data) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None  # Token expired
        return payload.get("sub")
    except Exception:
        return None


def validate_domain(email: str) -> None:
    """Strictly enforce institutional domain restrictions."""
    settings = get_settings()
    domain = settings.allowed_email_domain.strip().lower()
    if domain:
        norm_email = email.strip().lower()
        if not norm_email.endswith(f"@{domain}"):
            raise HTTPException(403, f"Strict institutional access: Only '@{domain}' accounts are authorized.")


def resolve_user(session: Session, authorization: str | None = None, x_user_email: str | None = None) -> User:
    """
    Authenticate user using Bearer token or development X-User-Email header.
    Bearer tokens take precedence and provide production-grade authentication.
    """
    email: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        email = decode_access_token(token)
        if not email:
            raise HTTPException(401, "Invalid or expired authorization token")
    elif x_user_email:
        email = x_user_email.strip().lower()
    else:
        raise HTTPException(401, "Authentication required. Provide 'Authorization: Bearer <token>' or 'X-User-Email'")

    validate_domain(email)
    user = session.scalar(select(User).where(User.email == email.lower()))
    if not user or not user.is_active:
        raise HTTPException(401, "Unknown or inactive user")
    return user
