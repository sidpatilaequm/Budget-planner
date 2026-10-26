import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import ALL_PERMS, PERM_LABELS
from ..db import get_db
from ..models import Activity, Head, Role, User, UserHead
from ..security import hash_password, require
from ..services.budget import log

router = APIRouter(prefix="/api", tags=["admin"])
admin_only = require("manage_users")


class HeadRef(BaseModel):
    section: str
    code: str
    name: str


class UserIn(BaseModel):
    name: str
    username: str
    role_id: int
    password: str | None = None
    scope: str = "all"
    heads: list[HeadRef] = []
    active: bool = True


class PasswordReset(BaseModel):
    password: str


class RoleIn(BaseModel):
    name: str | None = None
    perms: dict[str, bool] | None = None


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "username": u.username, "role_id": u.role_id,
            "role": u.role.name if u.role else None, "scope": u.scope, "active": u.active,
            "heads": [{"section": h.section, "code": h.head_code, "name": h.head_name} for h in u.heads]}


def role_out(r: Role, count: int) -> dict:
    perms = {k: True for k in ALL_PERMS} if r.locked else {k: bool((r.perms or {}).get(k)) for k in ALL_PERMS}
    return {"id": r.id, "name": r.name, "locked": r.locked, "perms": perms, "users": count}


def active_admins(db: Session) -> list[User]:
    return [u for u in db.scalars(select(User).where(User.active.is_(True))) if u.role and u.role.locked]


# ---------- users ----------

@router.get("/users")
def list_users(db: Session = Depends(get_db), _=Depends(admin_only)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.name))]


def _validate(db: Session, body: UserIn, existing: User | None):
    name, username = body.name.strip(), body.username.strip().lower()
    if not name or not username:
        raise HTTPException(422, "Enter a full name and a username.")
    if not re.fullmatch(r"[a-z0-9._@-]+", username):
        raise HTTPException(422, "Usernames can use letters, numbers and . _ @ - only.")
    clash = db.scalar(select(User).where(User.username == username))
    if clash and clash is not existing:
        raise HTTPException(409, "That username is already taken.")
    if not db.get(Role, body.role_id):
        raise HTTPException(422, "Choose a role.")
    if (not existing or body.password) and len(body.password or "") < 8:
        raise HTTPException(422, "Use a password of at least 8 characters.")
    if body.scope == "some" and not body.heads:
        raise HTTPException(422, "Tick at least one head, or choose All heads.")
    return name, username


def _apply(u: User, body: UserIn, name: str, username: str):
    u.name, u.username, u.role_id, u.active = name, username, body.role_id, body.active
    u.scope = "some" if body.scope == "some" else "all"
    u.heads = [UserHead(section=h.section, head_code=h.code, head_name=h.name) for h in body.heads] if u.scope == "some" else []
    if body.password:
        u.password_hash = hash_password(body.password)


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    name, username = _validate(db, body, None)
    u = User(password_hash="")
    _apply(u, body, name, username)
    db.add(u)
    db.flush()
    db.refresh(u)
    log(db, me, f"Added user “{name}” with role {u.role.name}")
    db.commit()
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserIn, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "That user does not exist.")
    name, username = _validate(db, body, u)
    new_role = db.get(Role, body.role_id)
    if u.role.locked and u.active and (not new_role.locked or not body.active) and len(active_admins(db)) <= 1:
        raise HTTPException(409, "Keep at least one active administrator.")
    if u.id == me.id and not body.active:
        raise HTTPException(409, "You cannot deactivate your own account.")
    _apply(u, body, name, username)
    db.flush()
    db.refresh(u)
    log(db, me, f"Updated user “{name}” (role {u.role.name})")
    db.commit()
    return user_out(u)


@router.post("/users/{user_id}/password")
def reset_password(user_id: int, body: PasswordReset, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "That user does not exist.")
    if len(body.password) < 8:
        raise HTTPException(422, "Use a password of at least 8 characters.")
    u.password_hash = hash_password(body.password)
    log(db, me, f"Reset the password for “{u.name}”")
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "That user does not exist.")
    if u.id == me.id:
        raise HTTPException(409, "You cannot delete your own account.")
    if u.role.locked and u.active and len(active_admins(db)) <= 1:
        raise HTTPException(409, "Keep at least one active administrator.")
    log(db, me, f"Deleted user “{u.name}”")
    db.delete(u)
    db.commit()
    return {"ok": True}


# ---------- roles ----------

@router.get("/roles")
def list_roles(db: Session = Depends(get_db), _=Depends(require())):
    users = list(db.scalars(select(User)))
    return [role_out(r, sum(1 for u in users if u.role_id == r.id)) for r in db.scalars(select(Role).order_by(Role.id))]


@router.post("/roles")
def create_role(body: RoleIn, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    name = (body.name or "New role").strip()
    base, n = name, 2
    while db.scalar(select(Role).where(Role.name == name)):
        name, n = f"{base} {n}", n + 1
    r = Role(name=name, locked=False, perms={k: bool((body.perms or {}).get(k)) for k in ALL_PERMS})
    db.add(r)
    log(db, me, f"Added role “{name}”")
    db.commit()
    return role_out(r, 0)


@router.patch("/roles/{role_id}")
def update_role(role_id: int, body: RoleIn, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "That role does not exist.")
    if r.locked:
        raise HTTPException(409, "The Administrator role cannot be changed.")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Enter a role name.")
        clash = db.scalar(select(Role).where(Role.name == name))
        if clash and clash.id != r.id:
            raise HTTPException(409, "Another role already has that name.")
        if name != r.name:
            log(db, me, f"Renamed role “{r.name}” to “{name}”")
            r.name = name
    if body.perms is not None:
        perms = dict(r.perms or {})
        for k, v in body.perms.items():
            if k in ALL_PERMS and bool(perms.get(k)) != bool(v):
                perms[k] = bool(v)
                log(db, me, f"{'Gave' if v else 'Removed'} “{PERM_LABELS[k]}” {'to' if v else 'from'} role “{r.name}”")
        for sec in ("expense", "income"):  # editing implies viewing
            if perms.get(f"edit_{sec}"):
                perms[f"view_{sec}"] = True
        r.perms = perms
    db.commit()
    return role_out(r, db.query(User).filter(User.role_id == r.id).count())


@router.delete("/roles/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "That role does not exist.")
    if r.locked:
        raise HTTPException(409, "The Administrator role cannot be deleted.")
    n = db.query(User).filter(User.role_id == r.id).count()
    if n:
        raise HTTPException(409, f"Move the {n} user{'' if n == 1 else 's'} in “{r.name}” to another role first.")
    log(db, me, f"Deleted role “{r.name}”")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/head-catalog")
def head_catalog(year_id: int, db: Session = Depends(get_db), _=Depends(admin_only)):
    heads = db.scalars(select(Head).where(Head.year_id == year_id).order_by(Head.section, Head.sort_order))
    return [{"section": h.section, "code": h.code, "name": h.name} for h in heads]


# ---------- activity ----------

@router.get("/activity")
def activity(user_id: int | None = None, limit: int = 500, db: Session = Depends(get_db), _=Depends(require("view_log"))):
    q = select(Activity).order_by(Activity.ts.desc(), Activity.id.desc()).limit(min(max(limit, 1), 2000))
    if user_id:
        q = q.where(Activity.user_id == user_id)
    users = {u.id: u.name for u in db.scalars(select(User))}
    return [{"id": a.id, "ts": a.ts.isoformat() + "Z", "user_id": a.user_id,
             "user": users.get(a.user_id, a.user_name), "action": a.action} for a in db.scalars(q)]
