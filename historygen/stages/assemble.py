"""Stage 6 — assemble (final render) + metadata.

Builds one clip per scene at the narration's exact length (Ken Burns on stills, fill
crop on videos, labelled placeholder when no asset), overlays the on-screen text,
attaches narration (or silence), concatenates, burns captions, mixes ducked music, and
writes final.mp4. Then generates the publish metadata (title/description/hashtags).
"""

from __future__ import annotations

import json
from pathlib import Path

from historygen import ffmpeg_utils as ff
from historygen import textimg
from historygen.config import SETTINGS
from historygen.manifest import Manifest
from historygen.schemas import Scene


def _scene_seconds(scene: Scene) -> float:
    return float(scene.actual_seconds or scene.est_seconds or 4.0)


def _build_scene_clip(manifest: Manifest, scene: Scene) -> Path:
    assets = manifest.assets
    seconds = _scene_seconds(scene)
    base = assets / f"clip_{scene.id:02d}_base.mp4"
    asset = scene.visual_asset
    if not asset or not Path(asset).exists():
        candidate = assets / f"visual_{scene.id:02d}.jpg"
        if candidate.exists():
            asset = str(candidate)

    if asset and scene.visual_is_video and Path(asset).exists():
        ff.video_to_clip(Path(asset), base, seconds)
    elif asset and Path(asset).exists():
        ff.still_to_clip(Path(asset), base, seconds, zoom_in=(scene.id % 2 == 0))
    else:
        label = f"[{scene.visual_type.value}]\n{scene.on_screen_text or scene.narration[:40]}"
        png = textimg.placeholder_image(assets / f"placeholder_{scene.id:02d}.png", label)
        ff.static_clip(png, base, seconds)

    # On-screen date/number overlay (static PNG, held over the whole scene).
    text_png = None
    if scene.on_screen_text.strip():
        text_png = textimg.transparent_text(
            assets / f"ostext_{scene.id:02d}.png", scene.on_screen_text,
            size=92, target_y_frac=0.14,
        )
    titled = assets / f"clip_{scene.id:02d}_text.mp4"
    ff.overlay_image(base, text_png, titled)

    audio = Path(scene.narration_audio) if scene.narration_audio else None
    final = assets / f"clip_{scene.id:02d}.mp4"
    ff.attach_audio(titled, audio, final, seconds)
    return final


def _render_captions(manifest: Manifest) -> list[tuple[Path, float, float]]:
    """Render each caption event to a PNG; return (png, start, end) overlay items."""
    cap_path = manifest.project.captions_file
    if not cap_path or not Path(cap_path).exists():
        return []
    events = json.loads(Path(cap_path).read_text(encoding="utf-8"))
    items: list[tuple[Path, float, float]] = []
    for i, ev in enumerate(events):
        png = textimg.transparent_text(
            manifest.assets / f"caption_{i:03d}.png", ev["text"],
            size=72, target_y_frac=0.74,
        )
        items.append((png, float(ev["start"]), float(ev["end"])))
    return items


def _generate_metadata(manifest: Manifest) -> None:
    project = manifest.project
    if not SETTINGS.has("anthropic"):
        project.description = (
            f"{project.title}\n\n{project.topic} hakkında kısa bir tarih videosu."
        )
        project.hashtags = ["#tarih", "#belgesel", "#shorts", "#osmanlı"]
        manifest.save()
        return
    import anthropic

    client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "description", "hashtags"],
    }
    narration = " ".join(s.narration for s in project.scenes)
    resp = client.messages.create(
        model=SETTINGS.models.anthropic_model,
        max_tokens=1500,
        system=(
            "You write YouTube Shorts metadata (title, description, hashtags) in the "
            "SAME LANGUAGE as the narration you're given. Be punchy and SEO-aware."
        ),
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content":
            f"Topic: {project.topic}\nNarration: {narration}\n\n"
            "Generate a title, description, and 5-8 hashtags, matching the narration's language."}],
    )
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    project.title = data.get("title", project.title)
    project.description = data.get("description", "")
    project.hashtags = data.get("hashtags", [])
    manifest.save()


def run(manifest: Manifest) -> None:
    project = manifest.project
    if not project.scenes:
        print("  assemble: no scenes yet")
        return
    if not ff.have_ffmpeg():
        print("  assemble: ffmpeg/ffprobe not found on PATH — install it (brew install ffmpeg)")
        return

    print(f"  assemble: building {len(project.scenes)} scene clips...")
    clips = [_build_scene_clip(manifest, s) for s in project.scenes]

    body = manifest.assets / "body.mp4"
    ff.concat(clips, body)

    current = body
    caption_items = _render_captions(manifest)
    if caption_items:
        capped = manifest.assets / "body_captioned.mp4"
        ff.overlay_timed(current, caption_items, capped)
        current = capped

    final = manifest.dir / "final.mp4"
    if project.music_asset and Path(project.music_asset).exists():
        ff.mix_music(current, Path(project.music_asset), final)
    else:
        # No music: just move the captioned/body file to final.
        ff._run(["ffmpeg", "-y", "-i", str(current), "-c", "copy", str(final)])

    project.final_video = str(final)
    manifest.save()
    print(f"  assemble: wrote {final}")

    print("  metadata: generating title/description/hashtags...")
    _generate_metadata(manifest)
    (manifest.dir / "metadata.json").write_text(
        json.dumps(
            {
                "title": project.title,
                "description": project.description,
                "hashtags": project.hashtags,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  metadata: title -> {project.title!r}")
