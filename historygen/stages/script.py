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
from historygen.schemas import Genre, Scene, VisualType, script_output_schema

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
    Genre.HISTORICAL: {
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
    },
    Genre.SOCIOLOGICAL: {
        "tr": lambda topic: (
            f"Konu: {topic}\n\n"
            "Bu toplumsal olguyu ele alan, dakikadan kısa, dikey bir kısa video için "
            "Türkçe senaryo üret. Çarpıcı bir kancayla başla; günlük hayattan örnekler ve "
            "birkaç güçlü istatistik kullan; kök nedeni gösteren bir dönüş yap; düşündüren "
            "bir kapanışla bitir."
        ),
        "en": lambda topic: (
            f"Topic: {topic}\n\n"
            "Write an English script for a fast-paced vertical sociology short (under 60s). "
            "Open with a provocative hook; build with everyday examples and a couple of "
            "striking statistics; reveal the root cause; end on a reflective takeaway."
        ),
    },
}


def _user_prompt(topic: str, language: str, genre: Genre) -> str:
    by_lang = _USER_PROMPTS.get(genre, _USER_PROMPTS[Genre.HISTORICAL])
    fn = by_lang.get(language) or by_lang["en"]
    return fn(topic)


_COMMON_TAIL = (
    "on_screen_text is a tiny overlay: a year, a number, or a place name "
    "(leave empty for stat_card scenes — the card already shows its text). "
    "Leave stat_value and stat_label empty ('') for every non stat_card scene. "
    "For each scene also set visual_difficulty: "
    "'easy' for atmosphere/landscape/crowd/stadium shots (fast local model); "
    "'medium' for character scenes, costumes, buildings, portraits (mid-tier model); "
    "'hard' for precise action shots, specific poses, controversial moments, "
    "multi-character interactions requiring exact composition (best model). "
)


def _historical_system(lang_name: str, number_rule: str, length_rule: str) -> str:
    return (
        f"You are a documentary scriptwriter for vertical/horizontal short-form and "
        f"long-form videos for YouTube / Reels / TikTok. You write in {lang_name}. "
        "Tell history step by step with concrete dates, numbers, names and places. "
        + number_rule + length_rule + " "
        "Choose a visual_type per scene:\n"
        "- ai_image: atmosphere, portraits, landscapes, court scenes, battles, crowds\n"
        "- archive_painting: when a real historical painting fits\n"
        "- archive_map: a real historical map of the region/era\n"
        "- tactical_map: troop movements / arrows over a map (sieges, campaigns)\n"
        "visual_prompt must be in ENGLISH (image models prefer English). "
        "Be historically precise in visual_prompt: name the exact flag, banner, uniform, or emblem "
        "(e.g. 'red Ottoman banner with white crescent and star', 'Byzantine double-headed eagle banner', "
        "'Mongol blue felt standard'). Never say just 'banner' or 'flag' without specifying its design. "
        + _COMMON_TAIL
    )


def _sociological_system(lang_name: str, number_rule: str, length_rule: str) -> str:
    return (
        f"You are a scriptwriter for thought-provoking sociology videos "
        f"for YouTube / Reels / TikTok. "
        f"You write in {lang_name}. The style is SOCIAL-ISSUE COMMENTARY on a modern "
        "phenomenon (loneliness, social media, inequality, urban isolation, burnout, "
        "declining birth rates, etc.). Build a clear arc across the scenes:\n"
        "1) a provocative HOOK — a question or unsettling observation;\n"
        "2) TENSION — relatable everyday examples plus striking statistics;\n"
        "3) a TURN — the insight or root cause most people miss;\n"
        "4) a reflective TAKEAWAY that leaves the viewer thinking.\n"
        "(For a long-form video, expand each of these into multiple scenes.)\n"
        + number_rule + length_rule + " "
        "Choose a visual_type per scene:\n"
        "- ai_image: photorealistic MODERN candid documentary scenes — a person alone on a "
        "phone, a crowded commuter train of strangers, an empty dinner table, glowing screens "
        "in a dark room, a busy city street. Emotive, cinematic, present-day (NO historical/period imagery).\n"
        "- stat_card: whenever a beat is built around a number. Put the number in stat_value "
        "(short, e.g. '%73', '3×', '1/2') and a few words in stat_label (e.g. 'yalnız hisseden gençler'). "
        "Still write the spoken sentence in narration.\n"
        "Use ai_image and stat_card only — do NOT use archive_painting, archive_map, or tactical_map. "
        "visual_prompt must be in ENGLISH (image models prefer English), describing a modern, "
        "photorealistic, emotionally resonant scene. "
        + _COMMON_TAIL
    )


def _length_guidance(target_seconds: int, lang_name: str) -> str:
    if target_seconds <= 75:
        return (
            "Each scene is one short beat (3-6 seconds of narration). "
            f"Keep the whole script under ~{target_seconds} seconds of spoken {lang_name} total."
        )
    minutes = target_seconds / 60
    scenes = max(8, round(target_seconds / 9))
    return (
        f"This is a LONG-FORM video: aim for about {minutes:.0f} minutes "
        f"(~{target_seconds} seconds) of spoken {lang_name} in total, across roughly "
        f"{scenes} scenes. Each scene is 6-12 seconds of narration (2-4 sentences). "
        "Let it breathe like a documentary — a clear opening, steady development, and a "
        "reflective conclusion — not a rapid montage."
    )


def _build_system(language: str, genre: Genre, target_seconds: int) -> str:
    lang_name = _LANGUAGE_NAMES.get(language, language.upper())
    number_rule = _NUMBER_RULES.get(language, "")
    length_rule = _length_guidance(target_seconds, lang_name)
    if genre == Genre.SOCIOLOGICAL:
        return _sociological_system(lang_name, number_rule, length_rule)
    return _historical_system(lang_name, number_rule, length_rule)


def _placeholder_script(topic: str, genre: Genre) -> dict:
    if genre == Genre.SOCIOLOGICAL:
        return _sociological_placeholder(topic)
    return _historical_placeholder(topic)


def _historical_placeholder(topic: str) -> dict:
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


def _sociological_placeholder(topic: str) -> dict:
    return {
        "title": f"{topic}: kimse konuşmuyor",
        "scenes": [
            {
                "narration": "Hiç bu kadar bağlantıda olup bu kadar yalnız hissetmemiştik.",
                "on_screen_text": "",
                "visual_prompt": "a young person alone at night lit only by a phone screen, cinematic, moody",
                "visual_type": VisualType.AI_IMAGE.value,
                "stat_value": "", "stat_label": "",
                "audio_cue": "soft melancholic piano",
                "est_seconds": 4.0,
            },
            {
                "narration": "Gençlerin neredeyse dörtte üçü kendini düzenli olarak yalnız hissettiğini söylüyor.",
                "on_screen_text": "",
                "visual_prompt": "",
                "visual_type": VisualType.STAT_CARD.value,
                "stat_value": "%73", "stat_label": "yalnız hisseden gençler",
                "audio_cue": "single low tone",
                "est_seconds": 5.0,
            },
            {
                "narration": "Aynı vagonda yüzlerce insan var ama kimse birbirine bakmıyor.",
                "on_screen_text": "",
                "visual_prompt": "crowded subway car full of strangers all looking at phones, nobody making eye contact",
                "visual_type": VisualType.AI_IMAGE.value,
                "stat_value": "", "stat_label": "",
                "audio_cue": "muffled city ambience",
                "est_seconds": 5.0,
            },
            {
                "narration": "Yakın arkadaş sayısı otuz yılda yarı yarıya düştü.",
                "on_screen_text": "",
                "visual_prompt": "",
                "visual_type": VisualType.STAT_CARD.value,
                "stat_value": "½", "stat_label": "otuz yılda yakın arkadaş sayısı",
                "audio_cue": "tense swell",
                "est_seconds": 4.0,
            },
            {
                "narration": "Sorun sadece ekranlar değil; buluşacak yerlerimizi ve zamanımızı kaybettik.",
                "on_screen_text": "",
                "visual_prompt": "empty community park bench at dusk, warm nostalgic light, quiet emptiness",
                "visual_type": VisualType.AI_IMAGE.value,
                "stat_value": "", "stat_label": "",
                "audio_cue": "reflective strings",
                "est_seconds": 5.0,
            },
            {
                "narration": "Belki de ilk adım, bir sonraki mesajı değil, bir sonraki buluşmayı planlamaktır.",
                "on_screen_text": "",
                "visual_prompt": "two friends laughing together at a small cafe table, warm genuine connection",
                "visual_type": VisualType.AI_IMAGE.value,
                "stat_value": "", "stat_label": "",
                "audio_cue": "hopeful warm resolve",
                "est_seconds": 5.0,
            },
        ],
    }


def _generate_with_claude(topic: str, language: str, genre: Genre, target_seconds: int) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
    # Long-form scripts are many scenes of JSON — give the model room. Large max_tokens
    # requires streaming (the SDK refuses long non-streaming requests).
    max_tokens = 32000 if target_seconds > 120 else 8000
    with client.messages.stream(
        model=SETTINGS.models.anthropic_model,
        max_tokens=max_tokens,
        system=_build_system(language, genre, target_seconds),
        output_config={
            "format": {"type": "json_schema", "schema": script_output_schema()}
        },
        messages=[{"role": "user", "content": _user_prompt(topic, language, genre)}],
    ) as stream:
        resp = stream.get_final_message()
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def run(manifest: Manifest) -> None:
    project = manifest.project
    language = project.language
    genre = project.genre
    target = project.target_seconds
    h = input_hash(
        "script", project.topic, SETTINGS.models.anthropic_model, language, genre.value, target
    )
    if manifest.is_fresh("script", h) and project.scenes:
        print("  script: up to date, skipping")
        return

    if SETTINGS.has("anthropic"):
        print(f"  script: generating with Claude ({language}, {genre.value}, ~{target}s)...")
        data = _generate_with_claude(project.topic, language, genre, target)
    else:
        print(f"  script: no ANTHROPIC_API_KEY — using placeholder script ({genre.value})")
        data = _placeholder_script(project.topic, genre)

    project.title = data.get("title", project.topic)
    project.scenes = [
        Scene(id=i, **scene) for i, scene in enumerate(data["scenes"])
    ]
    manifest.mark_done("script", h)
    print(f"  script: {len(project.scenes)} scenes, title: {project.title!r}")
