from __future__ import annotations

import os

# Configuration is validated lazily. Keep tests independent of a developer's
# local environment while still exercising the real Settings class.
os.environ.setdefault("APP_PASSWORD", "test-password")
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789")
os.environ.setdefault("AUDIT_RETENTION_DAYS", "0")
