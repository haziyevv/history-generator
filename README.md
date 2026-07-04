# history-generator

Automated pipeline that turns a topic into a **vertical (9:16) historical
documentary short** (< 60s) — narrated step by step with dates/numbers on screen,
AI-generated atmosphere visuals, real archive paintings & maps, tactical maps,
captions, and music — plus ready-to-post title/description/hashtags. Narration
language defaults to Turkish but any project can be cloned into another language
(see `translate` below).

## How it works

A single `manifest.json` per project flows through ordered, **resumable** stages. Each
stage caches its work by an input-hash, so re-running only repeats what changed.

```
script → narration → visuals → captions → music → assemble (+ metadata)
```

| Stage | Service | Output |
|-------|---------|--------|
| script | Claude (`claude-opus-4-8`) | beat-by-beat scene list (narration spells out numbers as words) |
| narration | ElevenLabs Multilingual v2 | per-scene audio + word timings |
| visuals | OpenAI (DALL-E 3), Wikimedia | per-scene image (1024×1792, 9:16) |
| captions | (from narration timings) | word-synced captions (Pillow PNGs over `overlay`) |
| music | ElevenLabs Music | one ducked background track |
| assemble | ffmpeg | `final.mp4` (1080×1920) |
| metadata | Claude | `metadata.json` (title/desc/hashtags, matches narration language) |

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
(+ optional `ELEVENLABS_VOICE_ID`), `OPENAI_API_KEY`.

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

# clone a finished project into another language, reusing its visuals as-is
python -m historygen translate <slug> "History of Christianity" --language English
```

The finished video is `projects/<slug>/final.mp4`; metadata is `projects/<slug>/metadata.json`.

### Manually swapping a wrong image

Generated visuals aren't always right (wrong flag, wrong building, etc). To replace one:

1. Drop your replacement image at `projects/<slug>/assets/visual_NN.jpg` (the two-digit
   scene id), overwriting the generated one — or adding it if that scene never got one.
2. Re-run just the assemble stage to rebuild `final.mp4` with the new image:

   ```bash
   python -m historygen run <slug> --stage assemble
   ```

The assemble stage reads images straight from disk (no caching), and falls back to
`assets/visual_NN.jpg` even if the manifest has no asset recorded for that scene — so
a manual drop-in is always picked up.

## Notes

- **Review checkpoint:** `new` stops after the script so you can edit narration/visuals
  in the manifest *before* spending money on generation.
- **Licensing:** Wikimedia Commons results are not guaranteed public-domain — check the
  licence of any archive image before publishing.
- **Tactical maps** try Wikimedia for a real historical map first, falling back to a
  DALL-E generated one if no good match is found.
- **Text rendering** (on-screen dates/numbers + captions) is done with Pillow → PNG and
  composited via ffmpeg's `overlay` filter, so the pipeline works even on ffmpeg builds
  without freetype/libass (no `drawtext`/`ass` filters required). Uses DejaVu Sans Bold
  on Linux / Arial on macOS for full Turkish character support (ı, ğ, ş, ç, ö, ü).
- **Image framing:** stills are fit fully inside the 9:16 frame (never cropped) with a
  blurred copy of the same image filling the background, so no part of a generated or
  manually swapped image is ever cut off.
