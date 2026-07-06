"""Single source of truth for per-scene timing.

Both the captions stage and the assemble stage must agree, to the millisecond, on how
long each scene runs — otherwise the caption timeline drifts from the audio. Everything
that needs a scene's duration goes through here.

Two adjustments live here:
- voice_speed: narration is time-stretched with ffmpeg `atempo` at assembly (pitch
  preserved). A speed < 1.0 makes the audio longer, so durations and word timings scale
  by 1/voice_speed.
- scene_pause: a silent beat held after each scene's narration.

Durations are frame-aligned (rounded to a whole video frame) so each scene clip's video
and audio lengths match exactly and concatenation stays in sync.
"""

from __future__ import annotations

from historygen.config import SETTINGS


def stretch() -> float:
    """Audio-duration multiplier from the voice speed (speed 0.9 -> 1.11x longer)."""
    return 1.0 / (SETTINGS.render.voice_speed or 1.0)


def base_audio_seconds(scene) -> float:
    """Narration length after time-stretch (no pause)."""
    raw = float(scene.actual_seconds or scene.est_seconds or 4.0)
    return raw * stretch()


def scene_seconds(scene) -> float:
    """Full on-screen length of a scene: stretched narration + pause, frame-aligned."""
    base = base_audio_seconds(scene) + SETTINGS.render.scene_pause
    fps = SETTINGS.render.fps
    return round(base * fps) / fps


def scaled_word_timings(scene) -> list[dict]:
    """Scene word timings scaled to the stretched audio."""
    st = stretch()
    return [
        {"word": w["word"], "start": w["start"] * st, "end": w["end"] * st}
        for w in (scene.word_timings or [])
    ]
