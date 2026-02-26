from __future__ import annotations

import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent / "settings.json"


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    return {
        "theme_mode": "dark",
    }


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
