from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..catalog import DEFAULT_ROLES, PERMISSION_GROUPS
from ..db import get_db
from ..models import FiscalYear, Role, User
from ..security import current_user, hash_password, make_token, perms_of, verify_password
from ..services.budget import fill_template, log

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupIn(BaseModel):
    name: str
    username: str
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


def me_out(user: User) -> dict:
    return {
        "user": {"id": user.id, "name": user.name, "username": user.username, "scope": user.scope,
                 "role": user.role.name if user.role else None,
                 "heads": [{"section": h.section, "code": h.head_code, "name": h.head_name} for h in user.heads]},
        "perms": perms_of(user),
        "perm_groups": [{"group": g, "items": [{"key": k, "label": l} for k, l in items]} for g, items in PERMISSION_GROUPS],
    }


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {"needs_setup": db.scalar(select(func.count(User.id))) == 0}


@router.post("/setup")
def setup(body: SetupIn, db: Session = Depends(get_db)):
    """Creates the first administrator, the default roles and FY 2026-27. Only works on an empty database."""
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(409, "The administrator account already exists. Sign in instead.")
    name, username = body.name.strip(), body.username.strip().lower()
    if not name or not username:
        raise HTTPException(422, "Enter a full name and a username.")
    if len(body.password) < 8:
        raise HTTPException(422, "Use a password of at least 8 characters.")
    roles = {}
    for r in DEFAULT_ROLES:
        role = db.scalar(select(Role).where(Role.name == r["name"]))
        if not role:
            role = Role(name=r["name"], locked=r["locked"], perms=r["perms"])
            db.add(role)
        roles[r["name"]] = role
    db.flush()
    user = User(name=name, username=username, password_hash=hash_password(body.password),
                role_id=roles["Administrator"].id, scope="all", active=True)
    db.add(user)
    if not db.scalar(select(func.count(FiscalYear.id))):
        y = FiscalYear(start_year=2026)
        db.add(y)
        fill_template(db, y)
    db.flush()
    log(db, user, "Created the administrator account")
    db.commit()
    db.refresh(user)
    return {"token": make_token(user), **me_out(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Username or password is incorrect.")
    if not user.active:
        raise HTTPException(403, "This account is inactive. Ask an administrator to activate it.")
    log(db, user, "Signed in")
    db.commit()
    return {"token": make_token(user), **me_out(user)}


@router.post("/logout")
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    log(db, user, "Signed out")
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return me_out(user)


@router.post("/password")
def change_password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(422, "Your current password is not correct.")
    if len(body.new_password) < 8:
        raise HTTPException(422, "Use a password of at least 8 characters.")
    user.password_hash = hash_password(body.new_password)
    log(db, user, "Changed own password")
    db.commit()
    return {"ok": True}
