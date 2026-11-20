from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from functools import lru_cache

from fastapi import HTTPException, Request, status

from app.config import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@lru_cache
def _configured_hash() -> str:
    settings = get_settings()
    if settings.app_password_hash:
        return settings.app_password_hash
    return hash_password(settings.app_password)


def verify_credentials(username: str, password: str) -> bool:
    settings = get_settings()
    if settings.auth_disabled:
        return True
    if not secrets.compare_digest(username, settings.app_username):
        # Still spend time hashing so failed usernames are not cheaper than
        # failed passwords.
        verify_password(password, _configured_hash())
        return False
    return verify_password(password, _configured_hash())


class LoginRateLimiter:
    """Small in-process limiter. Replace with Redis for multi-replica setups."""

    def __init__(self, max_attempts: int, window_seconds: int, lockout_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, deque[float]] = {}
        self._locked: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            locked_until = self._locked.get(key, 0)
            if locked_until > now:
                retry = max(1, int(locked_until - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many login attempts. Try again in {retry}s.",
                    headers={"Retry-After": str(retry)},
                )
            if locked_until:
                self._locked.pop(key, None)
            bucket = self._failures.get(key)
            if not bucket:
                return
            while bucket and bucket[0] < now - self.window_seconds:
                bucket.popleft()
            if not bucket:
                self._failures.pop(key, None)

    def fail(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._failures.setdefault(key, deque())
            bucket.append(now)
            if len(bucket) >= self.max_attempts:
                self._locked[key] = now + self.lockout_seconds
                self._failures.pop(key, None)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked.pop(key, None)


def login_key(request: Request) -> str:
    settings = get_settings()
    host = request.client.host if request.client else "unknown"
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            host = forwarded.split(",", 1)[0].strip()
    return f"{host}:{request.headers.get('user-agent', '')[:80]}"


def require_user(request: Request) -> str:
    settings = get_settings()
    if settings.auth_disabled:
        return "dev"
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return str(user)


def csrf_guard(request: Request) -> None:
    if request.method in SAFE_METHODS or get_settings().auth_disabled:
        return
    expected = request.session.get("csrf")
    supplied = request.headers.get("x-csrf-token", "")
    if not expected or not supplied or not secrets.compare_digest(str(expected), supplied):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing CSRF token",
        )


def issue_session(request: Request, username: str) -> str:
    csrf = secrets.token_urlsafe(32)
    request.session.clear()
    request.session["user"] = username
    request.session["csrf"] = csrf
    return csrf


def clear_session(request: Request) -> None:
    request.session.clear()
