"""Stage 2 — narration.

For each scene, synthesise Turkish speech with ElevenLabs and capture character-level
timestamps (so captions can be word-synced and clips timed to the real audio length).
Uses the REST `with-timestamps` endpoint, which is stable across SDK versions.

Without a key, scenes get no audio and fall back to their estimated duration, so the
rest of the pipeline still runs (silent gaps where narration would be).
"""

from __future__ import annotations

import base64
import hashlib

import requests

from historygen.config import SETTINGS
from historygen.ffmpeg_utils import have_ffmpeg, probe_duration
from historygen.manifest import Manifest

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"


def _words_from_chars(chars, starts, ends) -> list[dict]:
    """Group ElevenLabs character timings into word-level {word, start, end}."""
    words: list[dict] = []
    cur, cur_start = "", None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": cur_start, "end": prev_end})
                cur, cur_start = "", None
        else:
            if cur_start is None:
                cur_start = s
            cur += ch
            prev_end = e
    if cur:
        words.append({"word": cur, "start": cur_start, "end": prev_end})
    return words


def _synthesize(scene, voice: str, out_path) -> tuple[float, list[dict]]:
    resp = requests.post(
        API.format(voice=voice),
        headers={"xi-api-key": SETTINGS.elevenlabs_api_key},
        json={
            "text": scene.narration,
            "model_id": SETTINGS.models.elevenlabs_model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    out_path.write_bytes(base64.b64decode(data["audio_base64"]))
    align = data.get("alignment") or {}
    words = _words_from_chars(
        align.get("characters", []),
        align.get("character_start_times_seconds", []),
        align.get("character_end_times_seconds", []),
    )
    duration = probe_duration(out_path) if have_ffmpeg() else (
        words[-1]["end"] if words else scene.est_seconds
    )
    return duration, words


def run(manifest: Manifest) -> None:
    project = manifest.project
    if not project.scenes:
        print("  narration: no scenes yet — run script first")
        return

    if not SETTINGS.has("elevenlabs"):
        print("  narration: no ELEVENLABS_API_KEY — using estimated timings, no audio")
        for scene in project.scenes:
            scene.actual_seconds = scene.est_seconds
            scene.narration_audio = None
        manifest.save()
        return

    voice = SETTINGS.voice_id
    for scene in project.scenes:
        out = manifest.assets / f"narration_{scene.id:02d}.mp3"
        text_hash = hashlib.sha256(
            f"{scene.narration}|{voice}|{SETTINGS.models.elevenlabs_model}".encode()
        ).hexdigest()[:16]
        sidecar = out.with_suffix(".hash")
        if out.exists() and sidecar.exists() and sidecar.read_text() == text_hash:
            print(f"  narration: scene {scene.id} cached")
            continue
        print(f"  narration: scene {scene.id} synthesizing...")
        duration, words = _synthesize(scene, voice, out)
        scene.narration_audio = str(out)
        scene.actual_seconds = duration
        scene.word_timings = words
        sidecar.write_text(text_hash)
        manifest.save()
    print("  narration: done")
