"""Studio config: providers (which skill impl per capability) and edit styles
(scoring weights, role thresholds, platform rules). Styles are data, so adding a
genre or platform is a JSON file in config/styles/, not code.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import config_dir

DEFAULT_STYLE: dict[str, Any] = {
    "style": "general",
    "thresholds": {"high": 0.7, "mid": 0.45},
    "weights": {"semantic": 0.4, "emotion": 0.25, "usable": 0.2, "visual": 0.15},
    "platform_rules": {"reels": {"max_s": 90, "hook_window_s": 1.5},
                       "shorts": {"max_s": 60, "hook_window_s": 1.0},
                       "tiktok": {"max_s": 180, "hook_window_s": 1.0}},
    "music": "rising_cinematic",
}


def load_providers() -> dict[str, str]:
    p = config_dir() / "providers.json"
    if p.exists():
        return json.loads(p.read_text()).get("skills", {})
    return {}


def list_styles() -> list[str]:
    return sorted(p.stem for p in (config_dir() / "styles").glob("*.json"))


def load_style(name: str) -> dict[str, Any]:
    style = dict(DEFAULT_STYLE)
    p = config_dir() / "styles" / f"{name}.json"
    if p.exists():
        style.update(json.loads(p.read_text()))
    style["style"] = name if p.exists() else "general"
    return style
