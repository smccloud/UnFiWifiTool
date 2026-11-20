from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (ValueError, TypeError):
        return default


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    encoded = json.dumps(value, separators=(",", ":"), default=str)
    if row is None:
        db.add(Setting(key=key, value=encoded))
    else:
        row.value = encoded
