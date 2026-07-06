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
from historygen import textimg, timing
from historygen.config import SETTINGS
from historygen.manifest import Manifest
from historygen.schemas import Genre, Scene, VisualType


def _scene_seconds(scene: Scene) -> float:
    # Frame-aligned narration (time-stretched) + trailing pause. Shared with the
    # captions stage via `timing` so the caption timeline can't drift from the audio.
    return timing.scene_seconds(scene)


def _build_scene_clip(manifest: Manifest, scene: Scene) -> Path:
    assets = manifest.assets
    seconds = _scene_seconds(scene)
    base = assets / f"clip_{scene.id:02d}_base.mp4"
    asset = scene.visual_asset
    if not asset or not Path(asset).exists():
        candidate = assets / f"visual_{scene.id:02d}.jpg"
        if candidate.exists():
            asset = str(candidate)

    is_stat_card = scene.visual_type == VisualType.STAT_CARD
    if asset and scene.visual_is_video and Path(asset).exists():
        ff.video_to_clip(Path(asset), base, seconds)
    elif asset and is_stat_card and Path(asset).exists():
        # Stat cards are full-frame text; hold them still (no Ken Burns pan/blur).
        ff.static_clip(Path(asset), base, seconds)
    elif asset and Path(asset).exists():
        ff.still_to_clip(Path(asset), base, seconds, zoom_in=(scene.id % 2 == 0))
    else:
        label = f"[{scene.visual_type.value}]\n{scene.on_screen_text or scene.narration[:40]}"
        png = textimg.placeholder_image(assets / f"placeholder_{scene.id:02d}.png", label)
        ff.static_clip(png, base, seconds)

    # On-screen date/number overlay (static PNG, held over the whole scene).
    # Stat cards already carry their own text, so skip the overlay for them.
    text_png = None
    if scene.on_screen_text.strip() and not is_stat_card:
        text_png = textimg.transparent_text(
            assets / f"ostext_{scene.id:02d}.png", scene.on_screen_text,
            size=92, target_y_frac=0.14,
        )
    titled = assets / f"clip_{scene.id:02d}_text.mp4"
    ff.overlay_image(base, text_png, titled)

    # Video only — the narration is assembled separately as one continuous PCM
    # track (see run()), so no per-scene AAC encode can shift the voice timeline.
    return titled


def _load_caption_events(manifest: Manifest) -> list[dict]:
    cap_path = manifest.project.captions_file
    if not cap_path or not Path(cap_path).exists():
        return []
    return json.loads(Path(cap_path).read_text(encoding="utf-8"))


def _scene_caption_items(
    manifest: Manifest, scene: Scene, events: list[dict], t0: float, seconds: float,
) -> list[tuple[Path, float, float]]:
    """Caption overlay items for ONE scene, with times shifted to scene-relative.

    Burning captions per scene (instead of one pass over the whole video) keeps each
    ffmpeg call to a handful of overlay inputs, so long videos with hundreds of caption
    chunks stay fast and within ffmpeg's input limits.
    """
    items: list[tuple[Path, float, float]] = []
    idx = 0
    for ev in events:
        s, e = float(ev["start"]), float(ev["end"])
        if e <= t0 or s >= t0 + seconds:  # not in this scene's window
            continue
        rs, re = max(0.0, s - t0), min(seconds, e - t0)
        if re <= rs:
            continue
        png = textimg.transparent_text(
            manifest.assets / f"caption_{scene.id:02d}_{idx:03d}.png", ev["text"],
            size=72, target_y_frac=0.74,
        )
        items.append((png, rs, re))
        idx += 1
    return items


def _generate_metadata(manifest: Manifest) -> None:
    project = manifest.project
    if not SETTINGS.has("anthropic"):
        if project.genre == Genre.SOCIOLOGICAL:
            project.description = (
                f"{project.title}\n\n{project.topic} üzerine kısa bir toplum videosu."
            )
            project.hashtags = ["#toplum", "#sosyoloji", "#shorts", "#psikoloji"]
        else:
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
    cap_events = _load_caption_events(manifest)
    clips: list[Path] = []
    wavs: list[Path] = []
    t_cursor = 0.0
    for scene in project.scenes:
        seconds = _scene_seconds(scene)
        clip = _build_scene_clip(manifest, scene)
        items = _scene_caption_items(manifest, scene, cap_events, t_cursor, seconds)
        if items:
            capped = manifest.assets / f"clip_{scene.id:02d}_cap.mp4"
            ff.overlay_timed(clip, items, capped)
            clip = capped
        clips.append(clip)
        # Exact-length PCM narration for this scene (slowed via atempo, end-padded).
        wav = manifest.assets / f"voice_{scene.id:02d}.wav"
        audio = Path(scene.narration_audio) if scene.narration_audio else None
        ff.scene_voice_wav(audio, wav, seconds, atempo=SETTINGS.render.voice_speed)
        wavs.append(wav)
        t_cursor += seconds

    # Video and voice are assembled independently, then muxed with ONE audio encode —
    # per-clip AAC encoding used to add ~20ms priming per scene, drifting the voice
    # further behind the captions with every scene boundary.
    body_video = manifest.assets / "body_video.mp4"
    ff.concat(clips, body_video)
    voice = manifest.assets / "voice.wav"
    ff.concat_wavs(wavs, voice)
    body = manifest.assets / "body.mp4"
    ff.mux(body_video, voice, body)

    final = manifest.dir / "final.mp4"
    if project.music_asset and Path(project.music_asset).exists():
        ff.mix_music(body, Path(project.music_asset), final)
    else:
        # No music: just move the body file to final.
        ff._run(["ffmpeg", "-y", "-i", str(body), "-c", "copy", str(final)])

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
