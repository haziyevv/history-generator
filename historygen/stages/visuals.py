"""Stage 3 — visuals.

Per scene, produce one visual asset chosen by `visual_type`:
  ai_image / ai_video  -> fal.ai (Flux Pro still; Kling image->video for motion)
  archive_painting/map -> Wikimedia Commons (real historical media)
  tactical_map         -> a base map + troop arrows drawn with Pillow

Each scene is cached by an input-hash sidecar, so re-runs only regenerate scenes whose
prompt/type changed. Anything that can't be produced (no FAL_KEY, no match) is left as
None and the assemble stage renders a labelled placeholder instead.

NOTE: Wikimedia results are not guaranteed public-domain. Review licences for anything
you publish; see README.
"""

from __future__ import annotations

import hashlib

import requests

from historygen.config import SETTINGS
from historygen.manifest import Manifest
from historygen.schemas import Scene, VisualType

WIKI_API = "https://commons.wikimedia.org/w/api.php"


# --- helpers ---------------------------------------------------------------

def _download(url: str, dest) -> bool:
    try:
        r = requests.get(url, timeout=120, headers={"User-Agent": "history-generator/0.1"})
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    download failed: {e}")
        return False


def _wikimedia_image(query: str, dest) -> bool:
    try:
        r = requests.get(
            WIKI_API,
            params={
                "action": "query", "generator": "search", "gsrsearch": query,
                "gsrnamespace": "6", "gsrlimit": "5", "prop": "imageinfo",
                "iiprop": "url|extmetadata", "iiurlwidth": str(SETTINGS.render.width),
                "format": "json",
            },
            timeout=60, headers={"User-Agent": "history-generator/0.1"},
        )
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            if url and url.lower().endswith((".jpg", ".jpeg", ".png")):
                return _download(url, dest)
    except Exception as e:  # noqa: BLE001
        print(f"    wikimedia failed: {e}")
    return False


def _fal_image(prompt: str, dest) -> bool:
    import fal_client

    result = fal_client.subscribe(
        SETTINGS.models.fal_image_model,
        arguments={"prompt": prompt, "aspect_ratio": "9:16"},
    )
    images = result.get("images") or []
    if images and images[0].get("url"):
        return _download(images[0]["url"], dest)
    return False


def _fal_video(prompt: str, image_path, dest) -> bool:
    import fal_client

    image_url = fal_client.upload_file(str(image_path))
    result = fal_client.subscribe(
        SETTINGS.models.fal_video_model,
        arguments={"prompt": prompt, "image_url": image_url, "duration": "5"},
    )
    video = result.get("video") or {}
    if video.get("url"):
        return _download(video["url"], dest)
    return False


def _tactical_map(scene: Scene, dest) -> bool:
    """Draw a base map with troop arrows/markers using Pillow (still; motion via Ken Burns)."""
    from PIL import Image, ImageDraw

    W, H = SETTINGS.render.width, SETTINGS.render.height
    base = dest.with_name(dest.stem + "_base.jpg")
    if _wikimedia_image(scene.visual_prompt + " historical map", base):
        img = Image.open(base).convert("RGB").resize((W, H))
    else:
        img = Image.new("RGB", (W, H), (222, 202, 162))  # parchment
    draw = ImageDraw.Draw(img, "RGBA")
    # A couple of stylised campaign arrows + an objective marker.
    arrows = [((W * 0.2, H * 0.7), (W * 0.6, H * 0.4)),
              ((W * 0.8, H * 0.75), (W * 0.62, H * 0.42))]
    for (x0, y0), (x1, y1) in arrows:
        draw.line([(x0, y0), (x1, y1)], fill=(180, 30, 30, 230), width=14)
        draw.ellipse([x1 - 18, y1 - 18, x1 + 18, y1 + 18], fill=(180, 30, 30, 230))
    draw.ellipse([W * 0.6 - 30, H * 0.4 - 30, W * 0.6 + 30, H * 0.4 + 30],
                 outline=(20, 20, 20, 255), width=8)
    img.save(dest, quality=90)
    return True


# --- stage -----------------------------------------------------------------

def _scene_hash(scene: Scene) -> str:
    return hashlib.sha256(
        f"{scene.visual_type}|{scene.visual_prompt}|"
        f"{SETTINGS.models.fal_image_model}|{SETTINGS.models.fal_video_model}".encode()
    ).hexdigest()[:16]


def run(manifest: Manifest) -> None:
    project = manifest.project
    if not project.scenes:
        print("  visuals: no scenes yet — run script first")
        return

    for scene in project.scenes:
        h = _scene_hash(scene)
        sidecar = manifest.assets / f"visual_{scene.id:02d}.hash"
        existing = scene.visual_asset
        if existing and sidecar.exists() and sidecar.read_text() == h:
            print(f"  visuals: scene {scene.id} cached ({scene.visual_type})")
            continue

        vt = scene.visual_type
        ok = False
        scene.visual_is_video = False

        if vt == VisualType.AI_VIDEO and SETTINGS.has("fal"):
            still = manifest.assets / f"visual_{scene.id:02d}_src.jpg"
            video = manifest.assets / f"visual_{scene.id:02d}.mp4"
            print(f"  visuals: scene {scene.id} ai_video via fal...")
            if _fal_image(scene.visual_prompt, still) and _fal_video(
                scene.visual_prompt, still, video
            ):
                scene.visual_asset, scene.visual_is_video, ok = str(video), True, True

        elif vt == VisualType.AI_IMAGE and SETTINGS.has("fal"):
            dest = manifest.assets / f"visual_{scene.id:02d}.jpg"
            print(f"  visuals: scene {scene.id} ai_image via fal...")
            ok = _fal_image(scene.visual_prompt, dest)
            if ok:
                scene.visual_asset = str(dest)

        elif vt in (VisualType.ARCHIVE_PAINTING, VisualType.ARCHIVE_MAP):
            dest = manifest.assets / f"visual_{scene.id:02d}.jpg"
            kind = "painting" if vt == VisualType.ARCHIVE_PAINTING else "map"
            print(f"  visuals: scene {scene.id} archive {kind} via Wikimedia...")
            ok = _wikimedia_image(f"{scene.visual_prompt} {kind}", dest)
            if ok:
                scene.visual_asset = str(dest)

        elif vt == VisualType.TACTICAL_MAP:
            dest = manifest.assets / f"visual_{scene.id:02d}.jpg"
            print(f"  visuals: scene {scene.id} tactical_map (Pillow)...")
            ok = _tactical_map(scene, dest)
            if ok:
                scene.visual_asset = str(dest)

        if not ok:
            # Fall back: try fal-less AI types as Wikimedia, else leave for placeholder.
            if vt in (VisualType.AI_IMAGE, VisualType.AI_VIDEO):
                dest = manifest.assets / f"visual_{scene.id:02d}.jpg"
                if _wikimedia_image(scene.visual_prompt, dest):
                    scene.visual_asset, scene.visual_is_video, ok = str(dest), False, True
        if not ok:
            print(f"  visuals: scene {scene.id} — no asset, will use placeholder")
            scene.visual_asset = None
        else:
            sidecar.write_text(h)
        manifest.save()
    print("  visuals: done")
