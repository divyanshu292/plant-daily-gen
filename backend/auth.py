"""Sign-in helpers that need no database: password hashing, session tokens,
checking what people type, and a user as the API shows it.

Passwords are hashed with scrypt from the standard library, so there is no
extra package to install in Docker or on Vercel. main.py holds the routes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import re
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

SUPER_ADMIN, ADMIN, VIEWER = "super_admin", "admin", "viewer"
# The super admin can only hand out these; there is only ever one super admin.
ASSIGNABLE_ROLES = (ADMIN, VIEWER)
# Roles that may change plant data. A viewer only reads.
EDITOR_ROLES = (ADMIN, SUPER_ADMIN)

COOKIE = "ttps_session"
SESSION_DAYS = 30
SESSIONS_KEPT = 10       # newest sessions kept per user, i.e. devices signed in at once
ACTIVITY_KEPT = 200      # newest activity entries kept per user
MAX_FAILED_LOGINS = 5    # wrong passwords in a row that lock the account...
LOCK_MINUTES = 5         # ...for this long

PASSWORD_MIN, PASSWORD_MAX = 8, 128
NAME_MAX = 80
EMAIL_MAX = 254
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# About 50 ms and 16 MB per hash. The cost is stored with each hash, so it can
# be raised later without breaking existing passwords.
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 2 ** 14, 8, 1, 32
SALT_BYTES = 16

# The fields of a user the API ever sends: never the hash, sessions or lockout.
PUBLIC_FIELDS = ("id", "email", "name", "role", "createdAt", "lastLoginAt")


class Invalid(ValueError):
    """Something a person typed is not acceptable. The message is shown to them."""


# --- passwords ---------------------------------------------------------------------------

def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen)


def hash_password(password: str) -> str:
    """scrypt$N$r$p$<salt>$<hash>, salt and hash in base64. Slow on purpose:
    call it through asyncio.to_thread from a route."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def verify_password(password: str, stored: Optional[str]) -> bool:
    """Whether `password` matches the stored hash. With no stored hash (an
    unknown email) a dummy one is checked anyway, so that answer takes as long
    as a wrong password and does not tell who has an account."""
    if not stored:
        verify_password(password, _dummy_hash())
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest, validate=True)
        actual = _scrypt(password, base64.b64decode(salt, validate=True), int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):  # a malformed hash (binascii.Error is a ValueError)
        return False
    return scheme == "scrypt" and hmac.compare_digest(actual, expected)


# --- sessions ----------------------------------------------------------------------------

def iso(moment: datetime) -> str:
    """UTC time as stored everywhere in the user document. These strings sort
    in time order, so they can be compared directly, in Python and in queries."""
    return moment.isoformat(timespec="seconds")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """Only this is stored, so a copy of the database cannot be used to sign in."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session(hashed: str, now: datetime, user_agent: Optional[str]) -> dict:
    return {"hash": hashed, "createdAt": iso(now), "expiresAt": iso(now + timedelta(days=SESSION_DAYS)),
            "ua": (user_agent or "")[:200]}


def session_live(user: dict, hashed: str, now: datetime) -> bool:
    """Whether the user holds this session and it has not expired."""
    stamp = iso(now)
    return any(s.get("hash") == hashed and s.get("expiresAt", "") > stamp for s in user.get("sessions") or [])


def locked_minutes(user: dict, now: datetime) -> int:
    """Minutes left on a lockout, rounded up; 0 when the account is not locked."""
    until = user.get("lockedUntil")
    if not until:
        return 0
    left = (datetime.fromisoformat(until) - now).total_seconds()
    return math.ceil(left / 60) if left > 0 else 0


# --- what people type --------------------------------------------------------------------

def normalize_email(value) -> str:
    """Emails are stored and looked up lower-cased, so case never matters."""
    return value.strip().lower() if isinstance(value, str) else ""


def check_email(value) -> str:
    email = normalize_email(value)
    if not email or len(email) > EMAIL_MAX or not EMAIL_RE.match(email):
        raise Invalid("Enter a valid email address")
    return email


def check_name(value) -> str:
    name = value.strip() if isinstance(value, str) else ""
    if not name:
        raise Invalid("Enter a name")
    if len(name) > NAME_MAX:
        raise Invalid(f"Name must be at most {NAME_MAX} characters")
    return name


def check_password(value) -> str:
    if not isinstance(value, str) or len(value) < PASSWORD_MIN:
        raise Invalid(f"Password must be at least {PASSWORD_MIN} characters")
    if len(value) > PASSWORD_MAX:
        raise Invalid(f"Password must be at most {PASSWORD_MAX} characters")
    return value


def check_role(value) -> str:
    if value not in ASSIGNABLE_ROLES:
        raise Invalid("Access must be admin or viewer")
    return value


# --- users as the API shows them ---------------------------------------------------------

def public_user(doc: dict) -> dict:
    return {key: doc.get(key) for key in PUBLIC_FIELDS}


def activity_entry(action: str, text: str, now: datetime) -> dict:
    return {"at": iso(now), "action": action, "text": text}


def newest_first(activity: list, limit: int) -> list:
    """The stored list is oldest first (entries are appended)."""
    return list(reversed(activity or []))[:max(1, min(limit, ACTIVITY_KEPT))]
