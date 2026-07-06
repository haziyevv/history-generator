"""Stage 5 — music.

Generate one background track sized to the whole short, prompted from the scenes'
audio cues, via the ElevenLabs Music API. Music is optional: any failure (or no key)
leaves `music_asset` unset and the assemble stage simply renders voice-only.
"""

from __future__ import annotations

import requests

from historygen.config import SETTINGS
from historygen.manifest import Manifest, input_hash
from historygen.schemas import Genre

MUSIC_API = "https://api.elevenlabs.io/v1/music"
# ElevenLabs Music accepts 10-300s. For long-form we generate a shorter bed and let
# the assemble stage loop it (mix_music uses -stream_loop -1) — cheaper and faster.
MUSIC_MAX_MS = 120_000
MUSIC_MIN_MS = 10_000


def _length_ms(manifest: Manifest) -> int:
    total = sum((s.actual_seconds or s.est_seconds) for s in manifest.project.scenes)
    ms = int(total * 1000)
    return max(MUSIC_MIN_MS, min(ms, MUSIC_MAX_MS))


def run(manifest: Manifest) -> None:
    project = manifest.project
    if not project.scenes:
        print("  music: no scenes yet")
        return
    if not SETTINGS.has("elevenlabs"):
        print("  music: no ELEVENLABS_API_KEY — skipping (voice-only)")
        project.music_asset = None
        manifest.save()
        return

    cues = ", ".join(s.audio_cue for s in project.scenes if s.audio_cue)
    if project.genre == Genre.SOCIOLOGICAL:
        prompt = (
            f"Instrumental, reflective, slightly melancholic ambient score for a "
            f"documentary about: {project.topic}. Mood arc: {cues or 'contemplative, hopeful'}. "
            "Sparse piano and soft pads, no vocals, understated and emotional."
        )
    else:
        prompt = (
            f"Instrumental cinematic documentary score for a video about: {project.topic}. "
            f"Mood arc: {cues or 'epic history'}. No vocals, builds to a triumphant finale."
        )
    length_ms = _length_ms(manifest)
    h = input_hash("music", prompt, length_ms)
    out = manifest.assets / "music.mp3"
    if manifest.is_fresh("music", h) and out.exists():
        print("  music: cached")
        project.music_asset = str(out)
        manifest.save()
        return

    print("  music: generating with ElevenLabs Music...")
    try:
        r = requests.post(
            MUSIC_API,
            headers={"xi-api-key": SETTINGS.elevenlabs_api_key},
            json={"prompt": prompt, "music_length_ms": length_ms},
            timeout=300,
        )
        r.raise_for_status()
        out.write_bytes(r.content)
        project.music_asset = str(out)
        manifest.mark_done("music", h)
        print(f"  music: saved {out.name}")
    except Exception as e:  # noqa: BLE001
        print(f"  music: generation failed ({e}); continuing voice-only")
        project.music_asset = None
    manifest.save()
