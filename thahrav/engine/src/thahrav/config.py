"""Paths and settings. Settings come from environment variables, loaded from engine/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENGINE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ENGINE_DIR / ".env")


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def voice_guide(self) -> Path:
        return self.root / "docs" / "03-voice-and-style-guide.md"

    @property
    def theme_bank(self) -> Path:
        return self.root / "content" / "theme-bank.md"

    @property
    def script_template(self) -> Path:
        return self.root / "content" / "script-template.md"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "content" / "scripts"

    @property
    def compare_dir(self) -> Path:
        return self.root / "content" / "compare"


def project_paths() -> Paths:
    """The Thahrav project root (the folder holding docs/ and content/).

    THAHRAV_ROOT overrides it, which is handy for trying the engine on a copy.
    """
    return Paths(Path(os.getenv("THAHRAV_ROOT", ENGINE_DIR.parent)).resolve())


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def hindi_verb_form() -> str:
    form = env("THAHRAV_HINDI_VERB_FORM", "masculine").lower()
    if form not in ("masculine", "feminine"):
        raise ValueError("THAHRAV_HINDI_VERB_FORM must be 'masculine' or 'feminine'")
    return form
