from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_current_user(session: Session, x_user_email: str | None) -> User:
    if not x_user_email:
        raise HTTPException(401, "Sign in is required (X-User-Email in this first-draft local mode).")
    user = session.scalar(select(User).where(User.email == x_user_email.lower()))
    if not user or not user.is_active:
        raise HTTPException(401, "Unknown or inactive user")
    return user


def current_user_dependency(x_user_email: str | None = Header(default=None, alias="X-User-Email")):
    return x_user_email
