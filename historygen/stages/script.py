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

_LANGUAGE_NAMES = {
    "tr": "TURKISH",
    "en": "ENGLISH",
    "az": "AZERBAIJANI",
    "de": "GERMAN",
    "fr": "FRENCH",
    "es": "SPANISH",
    "ar": "ARABIC",
}

_NUMBER_RULES = {
    "tr": (
        "IMPORTANT: In the narration field, write ALL numbers as Turkish words — never use digits. "
        "For example: write 'bin iki yüz seksen bir' instead of '1281', "
        "'on dört' instead of '14', 'iki yüz bin' instead of '200.000'. "
    ),
    "en": (
        "IMPORTANT: In the narration field, write ALL numbers as English words — never use digits. "
        "For example: write 'twelve eighty-one' instead of '1281', 'fourteen' instead of '14'. "
    ),
}

_USER_PROMPTS = {
    "tr": lambda topic: (
        f"Konu: {topic}\n\n"
        "Bu konuyu adım adım anlatan, dakikadan kısa, dikey bir kısa video "
        "için Türkçe senaryo üret. Tarihleri ve sayıları net ver."
    ),
    "en": lambda topic: (
        f"Topic: {topic}\n\n"
        "Write an English script for a fast-paced vertical short video under 60 seconds. "
        "Tell the story step by step with concrete dates, numbers, names and places."
    ),
}


def _build_system(language: str) -> str:
    lang_name = _LANGUAGE_NAMES.get(language, language.upper())
    number_rule = _NUMBER_RULES.get(language, "")
    return (
        f"You are a documentary scriptwriter for fast-paced vertical (9:16) short videos "
        f"under 60 seconds for YouTube Shorts / Reels / TikTok. You write in {lang_name}. "
        "Tell history step by step with concrete dates, numbers, names and places. "
        + number_rule +
        "Each scene is one short beat (3-6 seconds of narration). Keep the whole script "
        f"under ~55 seconds of spoken {lang_name} total. Choose a visual_type per scene:\n"
        "- ai_image: atmosphere, portraits, landscapes, court scenes, battles, crowds\n"
        "- archive_painting: when a real historical painting fits\n"
        "- archive_map: a real historical map of the region/era\n"
        "- tactical_map: troop movements / arrows over a map (sieges, campaigns)\n"
        "visual_prompt must be in ENGLISH (image models prefer English). "
        "Be historically precise in visual_prompt: name the exact flag, banner, uniform, or emblem "
        "(e.g. 'red Ottoman banner with white crescent and star', 'Byzantine double-headed eagle banner', "
        "'Mongol blue felt standard'). Never say just 'banner' or 'flag' without specifying its design. "
        "on_screen_text is a tiny overlay: a year, a number, or a place name. "
        "For each scene also set visual_difficulty: "
        "'easy' for atmosphere/landscape/crowd/stadium shots (fast local model); "
        "'medium' for character scenes, period costumes, buildings, portraits (mid-tier model); "
        "'hard' for precise action shots, specific poses, controversial moments, "
        "multi-character interactions requiring exact composition (best model). "
        ""
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


def _generate_with_claude(topic: str, language: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
    user_prompt = _USER_PROMPTS.get(language, _USER_PROMPTS["en"])(topic)
    resp = client.messages.create(
        model=SETTINGS.models.anthropic_model,
        max_tokens=8000,
        system=_build_system(language),
        output_config={
            "format": {"type": "json_schema", "schema": script_output_schema()}
        },
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def run(manifest: Manifest) -> None:
    project = manifest.project
    language = project.language
    h = input_hash("script", project.topic, SETTINGS.models.anthropic_model, language)
    if manifest.is_fresh("script", h) and project.scenes:
        print("  script: up to date, skipping")
        return

    if SETTINGS.has("anthropic"):
        print(f"  script: generating with Claude ({language})...")
        data = _generate_with_claude(project.topic, language)
    else:
        print("  script: no ANTHROPIC_API_KEY — using placeholder script")
        data = _placeholder_script(project.topic)

    project.title = data.get("title", project.topic)
    project.scenes = [
        Scene(id=i, **scene) for i, scene in enumerate(data["scenes"])
    ]
    manifest.mark_done("script", h)
    print(f"  script: {len(project.scenes)} scenes, title: {project.title!r}")
