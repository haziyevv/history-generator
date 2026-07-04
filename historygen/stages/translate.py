"""Clone a finished project into a new language, reusing all visual assets.

Only the spoken/overlay text (title, narration, on_screen_text) is translated via
Claude; visual_prompt, visual_type, audio_cue, and est_seconds are copied verbatim
since the images/videos themselves are reused unchanged. Existing visual assets and
their cache sidecars are copied into the new project so the visuals stage skips
regeneration. Narration audio is NOT copied (it must be resynthesized in the new
language) — run narration/captions/music/assemble next.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from historygen.config import SETTINGS
from historygen.manifest import Manifest
from historygen.schemas import Scene


def _translate_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "scenes": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "narration": {"type": "string"},
                        "on_screen_text": {"type": "string"},
                    },
                    "required": ["narration", "on_screen_text"],
                },
            },
        },
        "required": ["title", "scenes"],
    }


def _translate_with_claude(title: str, scenes: list[Scene], language: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
    payload = {
        "title": title,
        "scenes": [
            {"narration": s.narration, "on_screen_text": s.on_screen_text}
            for s in scenes
        ],
    }
    resp = client.messages.create(
        model=SETTINGS.models.anthropic_model,
        max_tokens=4000,
        system=(
            f"You translate short documentary video scripts into {language}. "
            "Keep the narration natural, spoken, and roughly the same length/pacing "
            "as the original (it will be read aloud by a TTS voice). Keep on_screen_text "
            "very short (a date, number, or 1-3 words), translating place/people names "
            "to their standard English exonyms where one exists. Preserve the scene order "
            "exactly — same number of scenes in, same number out."
        ),
        output_config={
            "format": {"type": "json_schema", "schema": _translate_schema()}
        },
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def clone_translated(source_slug: str, new_topic: str, language: str = "English") -> Manifest:
    from historygen.manifest import slugify

    src = Manifest.load(source_slug)
    if not src.project.scenes:
        raise ValueError(f"Project '{source_slug}' has no scenes to translate")

    # `slugify` strips non-ASCII characters, so a topic that differs only in accents/
    # diacritics (e.g. retranslating into the language the topic was already in) can
    # collapse to the same slug as the source project. Disambiguate with the language.
    if slugify(new_topic) == source_slug:
        new_topic = f"{new_topic} ({language})"

    dst = Manifest.create(new_topic)
    if dst.slug == source_slug:
        raise ValueError(
            f"New project slug '{dst.slug}' collides with the source project. "
            "Pick a topic that produces a distinct slug."
        )
    dst.assets.mkdir(parents=True, exist_ok=True)

    print(f"  translate: asking Claude for {language} text...")
    data = _translate_with_claude(src.project.title, src.project.scenes, language)
    translated_scenes = data["scenes"]
    if len(translated_scenes) != len(src.project.scenes):
        raise ValueError(
            f"Translation returned {len(translated_scenes)} scenes, "
            f"expected {len(src.project.scenes)}"
        )

    new_scenes: list[Scene] = []
    for src_scene, tr in zip(src.project.scenes, translated_scenes):
        new_scene = src_scene.model_copy(deep=True)
        new_scene.narration = tr["narration"]
        new_scene.on_screen_text = tr["on_screen_text"]
        # Visual assets are reused as-is; narration/captions are stage outputs, reset them.
        new_scene.narration_audio = None
        new_scene.actual_seconds = None
        new_scene.word_timings = []

        if src_scene.visual_asset:
            src_file = Path(src_scene.visual_asset)
            if src_file.exists():
                dst_file = dst.assets / src_file.name
                shutil.copyfile(src_file, dst_file)
                new_scene.visual_asset = str(dst_file)
                # Copy the cache sidecar too, so the visuals stage treats it as fresh
                # (visual_type/visual_prompt/model are unchanged across languages).
                sidecar = src.assets / f"visual_{src_scene.id:02d}.hash"
                if sidecar.exists():
                    shutil.copyfile(sidecar, dst.assets / sidecar.name)

        new_scenes.append(new_scene)

    dst.project.title = data.get("title", new_topic)
    dst.project.scenes = new_scenes
    dst.save()
    print(f"  translate: cloned {len(new_scenes)} scenes into '{dst.slug}'")
    return dst
