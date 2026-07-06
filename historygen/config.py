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


# Mutable (not frozen): `apply_project_render()` sets these per project at run time,
# so a project can be vertical Shorts or a 16:9 long-form video.
@dataclass
class RenderSettings:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    # Cap used to size/loop the background music. Raised for long-form.
    max_total_seconds: float = 58.0
    language: str = "tr"  # narration language (Turkish)
    # Silent beat held on each scene AFTER its narration, before the next scene —
    # so the video doesn't cut the instant a sentence ends.
    scene_pause: float = 0.8
    # Narration speed applied at assembly via ffmpeg atempo (pitch preserved).
    # 1.0 = as spoken; < 1.0 = slower/calmer. Applied without re-generating TTS.
    voice_speed: float = 0.9


@dataclass(frozen=True)
class Models:
    # Anthropic — script + metadata. claude-opus-4-8 per the claude-api skill.
    anthropic_model: str = "claude-opus-4-8"
    # ElevenLabs — multilingual v2: supports Turkish and returns RELIABLE per-character
    # timestamps. (eleven_v3's alignment is approximate, which desyncs karaoke captions
    # from the voice — do not use v3 while captions depend on word timings.)
    elevenlabs_model: str = "eleven_multilingual_v2"
    # Fallback voice if none picked yet; override with ELEVENLABS_VOICE_ID.
    elevenlabs_default_voice: str = "mBUB5zYuPwfVE6DTcEjf"  # Eda Atlas (Turkish female)
    # Voice pools by language and gender.
    elevenlabs_voices: dict = field(default_factory=lambda: {
        "tr": {
            "male":   ["fXhoW006nc5Wf8xkGVSy"],        # Turkish male
            "female": ["mBUB5zYuPwfVE6DTcEjf"],        # Eda Atlas
        },
        "en": {
            "male":   ["JBFqnCBsd6RMkjVDRZzb",         # George
                       "onwK4e9ZLuTAKqWW03F9",         # Daniel
                       "TxGEqnHWrfWFTfGW9XjX"],        # Josh
            "female": ["EXAVITQu4vr4xnSDxMaL",         # Sarah
                       "XB0fDUnXU5powFXDhCwa"],        # Charlotte
        },
    })
    # OpenAI — image generation.
    openai_image_model: str = "gpt-image-2"


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    elevenlabs_api_key: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_API_KEY", ""))
    elevenlabs_voice_id: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_VOICE_ID", ""))
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    fal_key: str = field(default_factory=lambda: os.environ.get("FAL_KEY", ""))
    comfyui_url: str = field(default_factory=lambda: os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"))
    comfyui_checkpoint: str = field(default_factory=lambda: os.environ.get("COMFYUI_CHECKPOINT", "dreamshaper_7.safetensors"))
    comfyui_output_dir: str = field(default_factory=lambda: os.environ.get("COMFYUI_OUTPUT_DIR", "/mnt/c/Users/ferid/ComfyUI-Shared/output"))

    render: RenderSettings = field(default_factory=RenderSettings)
    models: Models = field(default_factory=Models)

    @property
    def voice_id(self) -> str:
        return self.elevenlabs_voice_id or self.models.elevenlabs_default_voice

    def voice_for(self, gender: str, language: str) -> str:
        """Return the first configured voice for a given gender and language."""
        if self.elevenlabs_voice_id:
            return self.elevenlabs_voice_id
        pool = self.models.elevenlabs_voices.get(language, {}).get(gender, [])
        if pool:
            return pool[0]
        return self.models.elevenlabs_default_voice

    def has(self, service: str) -> bool:
        """Whether the key for a service is configured."""
        return {
            "anthropic": bool(self.anthropic_api_key),
            "elevenlabs": bool(self.elevenlabs_api_key),
            "openai": bool(self.openai_api_key),
            "fal": bool(self.fal_key),
            "comfyui": bool(self.comfyui_url),
        }.get(service, False)


SETTINGS = Settings()


_ORIENTATION_DIMS = {
    "vertical": (1080, 1920),    # 9:16 Shorts/Reels
    "horizontal": (1920, 1080),  # 16:9 long-form
    "square": (1080, 1080),      # 1:1
}


def apply_project_render(orientation: str, target_seconds: int) -> None:
    """Set the global render dimensions + music cap for the current project.

    `RenderSettings` is a shared mutable object, so mutating its attributes here is
    picked up by ffmpeg_utils (which holds a reference) and by textimg (which reads
    the dimensions at call time). Call this once before any render stage.
    """
    w, h = _ORIENTATION_DIMS.get(orientation, _ORIENTATION_DIMS["vertical"])
    SETTINGS.render.width = w
    SETTINGS.render.height = h
    SETTINGS.render.max_total_seconds = float(max(58, target_seconds + 20))
