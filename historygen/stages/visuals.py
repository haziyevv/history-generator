"""Stage 3 — visuals.

Per scene, produce one visual asset:
  ai_image / ai_video      -> fal-ai/flux-2-pro
  archive_painting/map     -> Wikimedia Commons (real historical media)
  tactical_map             -> Wikimedia first, fal fallback

Each scene is cached by an input-hash sidecar, so re-runs only regenerate scenes whose
prompt/type changed.

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
FAL_MODEL = "fal-ai/flux-2-pro"


# --- helpers ---------------------------------------------------------------

def _download(url: str, dest) -> bool:
    try:
        r = requests.get(url, timeout=120, headers={"User-Agent": "history-generator/0.1"})
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
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
    except Exception as e:
        print(f"    wikimedia failed: {e}")
    return False


def _fal_image_size() -> str:
    """Map the current canvas orientation to a fal image_size enum."""
    w, h = SETTINGS.render.width, SETTINGS.render.height
    if w > h:
        return "landscape_16_9"
    if h > w:
        return "portrait_16_9"
    return "square_hd"


def _fal_image(prompt: str, dest) -> bool:
    try:
        import fal_client
        result = fal_client.subscribe(
            FAL_MODEL,
            arguments={"prompt": prompt, "image_size": _fal_image_size()},
        )
        url = result["images"][0]["url"]
        return _download(url, dest)
    except Exception as e:
        print(f"    fal image failed: {e}")
        return False


# --- stage -----------------------------------------------------------------

def _scene_hash(scene: Scene) -> str:
    return hashlib.sha256(
        f"{scene.visual_type}|{scene.visual_prompt}|{scene.stat_value}|"
        f"{scene.stat_label}|{FAL_MODEL}".encode()
    ).hexdigest()[:16]


def run(manifest: Manifest) -> None:
    project = manifest.project
    if not project.scenes:
        print("  visuals: no scenes yet — run script first")
        return

    for scene in project.scenes:
        pinned = manifest.assets / f"visual_{scene.id:02d}.pinned"
        if pinned.exists():
            print(f"  visuals: scene {scene.id} pinned — skipping")
            continue

        h = _scene_hash(scene)
        sidecar = manifest.assets / f"visual_{scene.id:02d}.hash"
        existing = scene.visual_asset
        if existing and sidecar.exists() and sidecar.read_text() == h:
            print(f"  visuals: scene {scene.id} cached ({scene.visual_type})")
            continue

        vt = scene.visual_type
        ok = False
        scene.visual_is_video = False
        dest = manifest.assets / f"visual_{scene.id:02d}.jpg"

        if vt == VisualType.STAT_CARD:
            from historygen import textimg
            value = scene.stat_value or scene.on_screen_text or ""
            label = scene.stat_label or (scene.visual_prompt[:40] if not scene.stat_value else "")
            print(f"  visuals: scene {scene.id} stat_card '{value}' (local render)...")
            textimg.stat_card(dest, value, label)
            scene.visual_asset = str(dest)
            ok = True

        elif vt in (VisualType.AI_IMAGE, VisualType.AI_VIDEO):
            print(f"  visuals: scene {scene.id} → {FAL_MODEL}...")
            ok = _fal_image(scene.visual_prompt, dest)
            if ok:
                scene.visual_asset = str(dest)

        elif vt in (VisualType.ARCHIVE_PAINTING, VisualType.ARCHIVE_MAP):
            kind = "painting" if vt == VisualType.ARCHIVE_PAINTING else "map"
            print(f"  visuals: scene {scene.id} archive {kind} via Wikimedia...")
            ok = _wikimedia_image(f"{scene.visual_prompt} {kind}", dest)
            if ok:
                scene.visual_asset = str(dest)

        elif vt == VisualType.TACTICAL_MAP:
            print(f"  visuals: scene {scene.id} tactical_map via Wikimedia...")
            ok = _wikimedia_image(scene.visual_prompt + " historical map", dest)
            if not ok:
                print(f"  visuals: scene {scene.id} tactical_map fallback → {FAL_MODEL}...")
                ok = _fal_image(scene.visual_prompt, dest)
            if ok:
                scene.visual_asset = str(dest)

        if not ok:
            print(f"  visuals: scene {scene.id} — no asset, will use placeholder")
            scene.visual_asset = None
        else:
            sidecar.write_text(h)
        manifest.save()
    print("  visuals: done")
