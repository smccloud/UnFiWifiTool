from __future__ import annotations

from pathlib import Path


def test_mit_license_exists():
    root = Path(__file__).resolve().parents[2]
    text = (root / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Permission is hereby granted" in text
    assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in text
