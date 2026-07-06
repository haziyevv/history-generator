"""Data models for a project and its scenes.

`Scene` is the unit the whole pipeline revolves around: the script stage produces a
list of scenes; every later stage attaches assets/timing to each scene by its `id`.

`script_output_schema()` is the JSON Schema handed to Claude's structured-output mode
so the model returns exactly this shape (no prose, no markdown fences).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Genre(str, Enum):
    HISTORICAL = "historical"        # step-by-step history with dates/places
    SOCIOLOGICAL = "sociological"    # social-issue commentary, anchored by stats


class VisualType(str, Enum):
    AI_IMAGE = "ai_image"            # generate a still (Flux) — atmosphere, portraits
    AI_VIDEO = "ai_video"           # generate motion (image->video) — battle action
    ARCHIVE_PAINTING = "archive_painting"  # public-domain painting via Wikimedia
    ARCHIVE_MAP = "archive_map"     # historical map via Wikimedia
    TACTICAL_MAP = "tactical_map"   # base map + animated troop arrows
    STAT_CARD = "stat_card"         # locally-rendered data card (big number + label)


class VisualDifficulty(str, Enum):
    EASY = "easy"      # atmosphere, landscape, crowd, stadium → ComfyUI
    MEDIUM = "medium"  # character scenes, period costumes, buildings → fal.ai
    HARD = "hard"      # precise action shots, multi-character compositions → gpt-image-2


class Scene(BaseModel):
    id: int
    # Turkish narration spoken in this scene.
    narration: str
    # Short on-screen text (date, number, place) — e.g. "1299" or "~500 savaşçı".
    on_screen_text: str = ""
    # English prompt describing the desired visual (prompts work best in English
    # even when the narration is Turkish).
    visual_prompt: str
    visual_type: VisualType
    visual_difficulty: VisualDifficulty = VisualDifficulty.EASY
    # Stat-card only: the big number and its short caption (e.g. "%73", "yalnız hisseden gençler").
    stat_value: str = ""
    stat_label: str = ""
    # Optional cue describing the desired SFX / music mood for this beat.
    audio_cue: str = ""
    # Script's estimate; replaced by the real narration length after TTS.
    est_seconds: float = 4.0

    # --- filled in by later stages (not produced by the script model) ---
    narration_audio: Optional[str] = None     # path to scene voice wav/mp3
    actual_seconds: Optional[float] = None     # measured narration duration
    word_timings: list[dict[str, Any]] = Field(default_factory=list)
    visual_asset: Optional[str] = None         # path to image/video for this scene
    visual_is_video: bool = False


class Project(BaseModel):
    slug: str
    topic: str
    title: str = ""
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    voice_id: Optional[str] = None       # locked in on first narration run
    voice_gender: str = "female"          # male | female
    language: str = "tr"                  # ISO 639-1 — drives both script and voice
    genre: Genre = Genre.HISTORICAL       # drives the script style + visual palette
    orientation: str = "vertical"         # vertical (9:16) | horizontal (16:9) | square
    target_seconds: int = 55              # desired total spoken length (drives scene count)
    music_asset: Optional[str] = None
    captions_file: Optional[str] = None
    final_video: Optional[str] = None


def script_output_schema() -> dict[str, Any]:
    """JSON Schema for the script stage's structured output."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "description": "Catchy Turkish title for the short."},
            "scenes": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "narration": {
                            "type": "string",
                            "description": "One beat of Turkish narration, 1-2 short sentences.",
                        },
                        "on_screen_text": {
                            "type": "string",
                            "description": "Very short on-screen overlay: a date, number, or place.",
                        },
                        "visual_prompt": {
                            "type": "string",
                            "description": "English description of the ideal visual for this beat.",
                        },
                        "visual_type": {
                            "type": "string",
                            "enum": [v.value for v in VisualType],
                        },
                        "stat_value": {
                            "type": "string",
                            "description": "stat_card only: the big number, e.g. '%73' or '3×'. Empty otherwise.",
                        },
                        "stat_label": {
                            "type": "string",
                            "description": "stat_card only: a few words under the number. Empty otherwise.",
                        },
                        "visual_difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                            "description": (
                                "easy: atmosphere/landscape/crowd/stadium (ComfyUI); "
                                "medium: characters, costumes, buildings (fal.ai); "
                                "hard: precise action shots, specific poses, multi-character interactions (gpt-image-2)."
                            ),
                        },
                        "audio_cue": {
                            "type": "string",
                            "description": "Short mood/SFX cue, e.g. 'tense war drums'.",
                        },
                        "est_seconds": {
                            "type": "number",
                            "description": "Estimated spoken length in seconds (3-6).",
                        },
                    },
                    "required": [
                        "narration",
                        "on_screen_text",
                        "visual_prompt",
                        "visual_type",
                        "stat_value",
                        "stat_label",
                        "visual_difficulty",
                        "audio_cue",
                        "est_seconds",
                    ],
                },
            },
        },
        "required": ["title", "scenes"],
    }
