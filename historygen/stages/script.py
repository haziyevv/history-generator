"""Stage 1 — script.

Turns the project topic into a beat-by-beat scene list with Turkish narration, using
Claude in structured-output mode so the response matches `script_output_schema()`.
Without an Anthropic key it emits a small placeholder script so the rest of the
pipeline is still exercisable.
"""

from __future__ import annotations

import json

from historygen.config import SETTINGS
from historygen.manifest import Manifest, input_hash
from historygen.schemas import Scene, VisualType, script_output_schema

SYSTEM = (
    "You are a documentary scriptwriter for fast-paced vertical (9:16) short videos "
    "under 60 seconds for YouTube Shorts / Reels / TikTok. You write in TURKISH. "
    "Tell history step by step with concrete dates, numbers, names and places. "
    "Each scene is one short beat (3-6 seconds of narration). Keep the whole script "
    "under ~55 seconds of spoken Turkish total. Choose a visual_type per scene:\n"
    "- ai_image: atmosphere, portraits, landscapes, court scenes\n"
    "- ai_video: motion — battles, cavalry charges, fire, crowds\n"
    "- archive_painting: when a real historical painting fits\n"
    "- archive_map: a real historical map of the region/era\n"
    "- tactical_map: troop movements / arrows over a map (sieges, campaigns)\n"
    "visual_prompt must be in ENGLISH (image models prefer English). "
    "on_screen_text is a tiny overlay: a year, a number, or a place name."
)


def _placeholder_script(topic: str) -> dict:
    return {
        "title": f"{topic} — kısa tarih",
        "scenes": [
            {
                "narration": f"{topic}: her şey nasıl başladı?",
                "on_screen_text": "BÖLÜM 1",
                "visual_prompt": "epic cinematic establishing shot, historical setting, golden hour",
                "visual_type": VisualType.AI_IMAGE.value,
                "audio_cue": "rising tension",
                "est_seconds": 4.0,
            },
            {
                "narration": "1299 yılında Osman Bey'in yanında yaklaşık beş yüz savaşçı vardı.",
                "on_screen_text": "1299 • ~500",
                "visual_prompt": "small band of medieval Anatolian horsemen on a hill at dawn",
                "visual_type": VisualType.AI_IMAGE.value,
                "audio_cue": "lonely flute",
                "est_seconds": 5.0,
            },
            {
                "narration": "Bizans sınırındaki bu küçük beylik hızla büyüdü.",
                "on_screen_text": "BEYLİK",
                "visual_prompt": "historical map of northwest Anatolia around 1300, parchment style",
                "visual_type": VisualType.ARCHIVE_MAP.value,
                "audio_cue": "soft drums",
                "est_seconds": 4.0,
            },
            {
                "narration": "Akıncılar batıya doğru ilerledi ve kaleleri kuşattı.",
                "on_screen_text": "AKINLAR",
                "visual_prompt": "medieval cavalry charging toward a fortress, dust and banners",
                "visual_type": VisualType.AI_VIDEO.value,
                "audio_cue": "war drums",
                "est_seconds": 5.0,
            },
            {
                "narration": "Bursa'nın fethiyle beylik bir devlete dönüştü.",
                "on_screen_text": "1326 • BURSA",
                "visual_prompt": "troop movement arrows converging on a besieged medieval city on a map",
                "visual_type": VisualType.TACTICAL_MAP.value,
                "audio_cue": "triumphant low brass",
                "est_seconds": 5.0,
            },
            {
                "narration": "Ve böylece altı yüz yıl sürecek bir imparatorluk doğdu.",
                "on_screen_text": "İMPARATORLUK",
                "visual_prompt": "ottoman banners over a city skyline at sunset, cinematic",
                "visual_type": VisualType.ARCHIVE_PAINTING.value,
                "audio_cue": "epic finale",
                "est_seconds": 4.0,
            },
        ],
    }


def _generate_with_claude(topic: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
    resp = client.messages.create(
        model=SETTINGS.models.anthropic_model,
        max_tokens=8000,
        system=SYSTEM,
        output_config={
            "format": {"type": "json_schema", "schema": script_output_schema()}
        },
        messages=[
            {
                "role": "user",
                "content": (
                    f"Konu: {topic}\n\n"
                    "Bu konuyu adım adım anlatan, dakikadan kısa, dikey bir kısa video "
                    "için Türkçe senaryo üret. Tarihleri ve sayıları net ver."
                ),
            }
        ],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def run(manifest: Manifest) -> None:
    project = manifest.project
    h = input_hash("script", project.topic, SETTINGS.models.anthropic_model)
    if manifest.is_fresh("script", h) and project.scenes:
        print("  script: up to date, skipping")
        return

    if SETTINGS.has("anthropic"):
        print("  script: generating with Claude...")
        data = _generate_with_claude(project.topic)
    else:
        print("  script: no ANTHROPIC_API_KEY — using placeholder script")
        data = _placeholder_script(project.topic)

    project.title = data.get("title", project.topic)
    project.scenes = [
        Scene(id=i, **scene) for i, scene in enumerate(data["scenes"])
    ]
    manifest.mark_done("script", h)
    print(f"  script: {len(project.scenes)} scenes, title: {project.title!r}")
