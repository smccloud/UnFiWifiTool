from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    actor: str,
    action: str,
    target_mac: str | None = None,
    result: str = "success",
    detail: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        target_mac=target_mac,
        result=result,
        detail=json.dumps(detail, separators=(",", ":"), default=str) if detail else None,
        request_id=request_id,
    )
    db.add(entry)
    return entry
