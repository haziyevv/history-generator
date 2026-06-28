# history-generator

Automated pipeline that turns a topic into a **vertical (9:16) Turkish historical
documentary short** (< 60s) — narrated step by step with dates/numbers on screen,
AI-generated battle/atmosphere visuals, real archive paintings & maps, animated
tactical maps, captions, and music — plus ready-to-post title/description/hashtags.

## How it works

A single `manifest.json` per project flows through ordered, **resumable** stages. Each
stage caches its work by an input-hash, so re-running only repeats what changed.

```
script → narration → visuals → captions → music → assemble (+ metadata)
```

| Stage | Service | Output |
|-------|---------|--------|
| script | Claude (`claude-opus-4-8`) | beat-by-beat Turkish scene list |
| narration | ElevenLabs Multilingual v2 | per-scene Turkish audio + word timings |
| visuals | fal.ai (Flux Pro / Kling), Wikimedia, Pillow | per-scene image/video/map |
| captions | (from narration timings) | word-synced captions (Pillow PNGs over `overlay`) |
| music | ElevenLabs Music | one ducked background track |
| assemble | ffmpeg | `final.mp4` (1080×1920) |
| metadata | Claude | `metadata.json` (title/desc/hashtags) |

**Graceful degradation:** every stage runs without its key — missing visuals become
labelled placeholders, missing narration falls back to estimated timing — so you can
test the whole pipeline before adding keys/credits, then fill them in one at a time.

## Setup

```bash
brew install ffmpeg                       # one system dependency
python -m pip install -r requirements.txt
cp .env.example .env                       # then add your keys (optional to start)
```

Keys (all optional; add as you go): `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`
(+ optional `ELEVENLABS_VOICE_ID`), `FAL_KEY`.

## Usage

```bash
# 1. create a project + generate the script, then REVIEW projects/<slug>/manifest.json
python -m historygen new "Osmanlı Devleti'nin kuruluşu (1299)"

# 2. run the rest of the pipeline (resumable; re-run safely)
python -m historygen run <slug>

# handy:
python -m historygen run <slug> --stage visuals   # one stage only
python -m historygen run <slug> --force            # ignore cache, regenerate
python -m historygen status <slug>
python -m historygen list
```

The finished video is `projects/<slug>/final.mp4`; metadata is `projects/<slug>/metadata.json`.

## Notes

- **Review checkpoint:** `new` stops after the script so you can edit narration/visuals
  in the manifest *before* spending money on generation.
- **Licensing:** Wikimedia Commons results are not guaranteed public-domain — check the
  licence of any archive image before publishing.
- **Tactical maps** are currently a base map + drawn arrows shown as a still (motion via
  Ken Burns). Animated arrow growth is a planned enhancement.
- **Text rendering** (on-screen dates/numbers + captions) is done with Pillow → PNG and
  composited via ffmpeg's `overlay` filter, so the pipeline works even on ffmpeg builds
  without freetype/libass (no `drawtext`/`ass` filters required).
