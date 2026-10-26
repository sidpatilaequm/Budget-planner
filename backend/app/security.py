"""Password hashing, JWT tokens and permission checks. Every rule the UI shows is enforced here too."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .catalog import ALL_PERMS
from .db import JWT_HOURS, JWT_SECRET, get_db
from .models import Head, User

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_HOURS)
    return jwt.encode({"sub": str(user.id), "exp": exp}, JWT_SECRET, algorithm="HS256")


def current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if not cred:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    try:
        data = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    user = db.get(User, int(data["sub"]))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account is not active.")
    return user


def perms_of(user: User) -> dict:
    if user.role is None:
        return {k: False for k in ALL_PERMS}
    if user.role.locked:
        return {k: True for k in ALL_PERMS}
    return {k: bool((user.role.perms or {}).get(k)) for k in ALL_PERMS}


def can(user: User, perm: str) -> bool:
    return perms_of(user).get(perm, False)


def require(*perms: str):
    """Dependency: the signed-in user must hold every listed permission."""
    def dep(user: User = Depends(current_user)) -> User:
        missing = [p for p in perms if not can(user, p)]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not allow this.")
        return user
    return dep


def deny(msg="Your role does not allow this."):
    raise HTTPException(status.HTTP_403_FORBIDDEN, msg)


def in_scope(user: User, head: Head) -> bool:
    if user.scope != "some":
        return True
    return any(h.section == head.section and h.head_code == head.code for h in user.heads)


def can_edit_amounts(user: User, head: Head) -> bool:
    return can(user, f"edit_{head.section}") and in_scope(user, head)


def can_edit_lines(user: User, head: Head) -> bool:
    return can_edit_amounts(user, head) and can(user, "edit_lines")


def can_manage_heads(user: User) -> bool:
    return can(user, "manage_heads") and user.scope != "some"
