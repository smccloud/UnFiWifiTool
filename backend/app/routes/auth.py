from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import audit
from app.auth import (
    LoginRateLimiter,
    clear_session,
    issue_session,
    login_key,
    require_user,
    verify_credentials,
)
from app.config import get_settings
from app.db import get_db
from app.schemas import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

_limiter: LoginRateLimiter | None = None


def _get_limiter() -> LoginRateLimiter:
    global _limiter
    if _limiter is None:
        settings = get_settings()
        _limiter = LoginRateLimiter(
            max_attempts=settings.login_max_attempts,
            window_seconds=settings.login_window_seconds,
            lockout_seconds=settings.login_lockout_seconds,
        )
    return _limiter


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    limiter = _get_limiter()
    key = login_key(request)
    limiter.check(key)
    request_id = getattr(request.state, "request_id", None)

    if not verify_credentials(payload.username, payload.password):
        limiter.fail(key)
        audit.record(
            db,
            actor=payload.username[:64] or "unknown",
            action="login",
            result="failure",
            detail={"reason": "invalid credentials"},
            request_id=request_id,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    limiter.reset(key)
    csrf = issue_session(request, payload.username)
    audit.record(
        db,
        actor=payload.username[:64],
        action="login",
        result="success",
        request_id=request_id,
    )
    db.commit()
    return LoginResponse(username=payload.username, csrf_token=csrf)


@router.post("/logout")
def logout(request: Request, _user: str = Depends(require_user)):
    actor = request.session.get("user", "unknown")
    clear_session(request)
    return {"ok": True, "actor": actor}


@router.get("/me", response_model=MeResponse)
def me(request: Request, user: str = Depends(require_user)):
    settings = get_settings()
    csrf = str(request.session.get("csrf", ""))
    return MeResponse(
        username=user,
        csrf_token=csrf,
        auth_disabled=settings.auth_disabled,
        app_name=settings.app_name,
        version="0.1.0",
    )
