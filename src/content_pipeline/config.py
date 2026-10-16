"""Paths and settings.

Settings come from environment variables, loaded from a `.env` file at the repo
root. A *channel profile* is a folder under `profiles/` holding everything that is
specific to one channel: voice guide, prompt, theme bank, pillars and the scripts
written for it. `config/` holds the studio's edit styles and skill providers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DEFAULT_PROFILE = "thahrav"


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def profiles_dir() -> Path:
    return Path(env("ACP_PROFILES_DIR") or REPO_ROOT / "profiles").resolve()


def config_dir() -> Path:
    return Path(env("ACP_CONFIG_DIR") or REPO_ROOT / "config").resolve()


@dataclass(frozen=True)
class Paths:
    """Files of one channel profile."""

    root: Path

    @property
    def channel_file(self) -> Path:
        return self.root / "channel.json"

    @property
    def prompt(self) -> Path:
        return self.root / "prompt.md"

    @property
    def voice_guide(self) -> Path:
        return self.root / "voice-guide.md"

    @property
    def theme_bank(self) -> Path:
        return self.root / "theme-bank.md"

    @property
    def script_template(self) -> Path:
        return self.root / "script-template.md"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "scripts"

    @property
    def compare_dir(self) -> Path:
        return self.root / "compare"


def profile_paths(name: str | None = None) -> Paths:
    """The profile folder. ACP_PROFILE picks the default; a path also works."""
    name = name or env("ACP_PROFILE", DEFAULT_PROFILE)
    candidate = Path(name)
    if candidate.is_dir():
        return Paths(candidate.resolve())
    return Paths(profiles_dir() / name)
