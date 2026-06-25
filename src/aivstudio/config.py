"""Config — providers (which skill impl per capability) and genre profiles
(scoring weights, role thresholds, platform rules). Profiles are data, so
adding a genre or platform is a JSON file, not code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_CONFIG_DIR = _HERE.parent.parent / "config"

DEFAULT_PROFILE: dict[str, Any] = {
    "profile": "general",
    "thresholds": {"high": 0.7, "mid": 0.45},
    "weights": {"semantic": 0.4, "emotion": 0.25, "usable": 0.2, "visual": 0.15},
    "platform_rules": {"reels": {"max_s": 90, "hook_window_s": 1.5},
                       "shorts": {"max_s": 60, "hook_window_s": 1.0},
                       "tiktok": {"max_s": 180, "hook_window_s": 1.0}},
    "music": "rising_cinematic",
}


def load_providers() -> dict[str, str]:
    p = _CONFIG_DIR / "providers.json"
    if p.exists():
        return json.loads(p.read_text()).get("skills", {})
    return {}


def load_profile(name: str) -> dict[str, Any]:
    p = _CONFIG_DIR / "profiles" / f"{name}.json"
    if p.exists():
        prof = dict(DEFAULT_PROFILE)
        prof.update(json.loads(p.read_text()))
        return prof
    return dict(DEFAULT_PROFILE)
