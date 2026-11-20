from __future__ import annotations

import json
from pathlib import Path

from app import __version__


def test_application_version_is_consistent():
    root = Path(__file__).resolve().parents[2]
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert version

    # The backend reads VERSION (unless APP_VERSION overrides it).
    assert __version__ == version

    package = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == version

    env_lines = (root / ".env.example").read_text(encoding="utf-8").splitlines()
    image_version = next(
        line.split("=", 1)[1].strip()
        for line in env_lines
        if line.startswith("IMAGE_VERSION=")
    )
    assert image_version == version
