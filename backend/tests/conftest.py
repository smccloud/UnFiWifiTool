from __future__ import annotations

import os
import secrets

# Configuration is validated lazily. Generate ephemeral values so tests stay
# independent of a developer's environment without embedding secrets in source.
os.environ.setdefault("APP_PASSWORD", secrets.token_urlsafe(24))
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
os.environ.setdefault("AUDIT_RETENTION_DAYS", "0")
