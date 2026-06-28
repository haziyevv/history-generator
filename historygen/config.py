"""Configuration: API keys, paths, and render settings.

All secrets come from environment variables (loaded from a local .env if present).
Nothing here raises if a key is missing — individual stages decide whether they can
run or must fall back to a labelled placeholder. This lets the whole pipeline run
end-to-end before every key/credit is in place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv not installed yet — env vars still work
    pass


# --- paths -----------------------------------------------------------------

# Repo root = the directory that contains the `historygen` package.
ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"


def project_dir(slug: str) -> Path:
    return PROJECTS_DIR / slug


def assets_dir(slug: str) -> Path:
    return project_dir(slug) / "assets"


# --- render settings (9:16 vertical Shorts) --------------------------------


@dataclass(frozen=True)
class RenderSettings:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    # Hard cap so we stay within Shorts/Reels limits.
    max_total_seconds: float = 58.0
    language: str = "tr"  # narration language (Turkish)


@dataclass(frozen=True)
class Models:
    # Anthropic — script + metadata. claude-opus-4-8 per the claude-api skill.
    anthropic_model: str = "claude-opus-4-8"
    # ElevenLabs — multilingual TTS that supports Turkish.
    elevenlabs_model: str = "eleven_multilingual_v2"
    # A sensible documentary-style default voice; override with ELEVENLABS_VOICE_ID.
    elevenlabs_default_voice: str = "JBFqnCBsd6RMkjVDRZzb"
    # fal.ai endpoints (best-quality image + image->video).
    fal_image_model: str = "fal-ai/flux-pro/v1.1-ultra"
    fal_video_model: str = "fal-ai/kling-video/v2/master/image-to-video"


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    elevenlabs_api_key: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_API_KEY", ""))
    elevenlabs_voice_id: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_VOICE_ID", ""))
    fal_key: str = field(default_factory=lambda: os.environ.get("FAL_KEY", ""))

    render: RenderSettings = field(default_factory=RenderSettings)
    models: Models = field(default_factory=Models)

    @property
    def voice_id(self) -> str:
        return self.elevenlabs_voice_id or self.models.elevenlabs_default_voice

    def has(self, service: str) -> bool:
        """Whether the key for a service is configured."""
        return {
            "anthropic": bool(self.anthropic_api_key),
            "elevenlabs": bool(self.elevenlabs_api_key),
            "fal": bool(self.fal_key),
        }.get(service, False)


SETTINGS = Settings()
