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

## Creating a video (content-manager guide)

> **Making videos day-to-day?** See **[CONTENT_GUIDE.md](CONTENT_GUIDE.md)** — a
> non-technical, example-by-example walkthrough of every option. The section below is a
> condensed version.


Every video is made with the same two steps — **`new`** (generate + review the script) then
**`run`** (produce the video). **Any topic works — you don't have to categorise it.** By
default the script style is `auto`: the model reads your topic and picks the best way to
tell it (historical dates, modern photos, stat cards, maps — whatever fits). The only choice
you normally make is length/format:

- **Short** (default) — vertical, < 60s.
- **Video** — longer (`--minutes N`), any shape (`--orientation`).

If you want to *force* a style you can still pass `--genre historical` or `--genre
sociological`, but you never have to.

### The two steps

```bash
# 1. create the project and generate its script — then OPEN projects/<slug>/manifest.json
#    and review/edit the scene narration & visuals BEFORE spending money on generation
python -m historygen new "<topic>" [options]

# 2. produce narration, visuals, captions, music and assemble the final video (resumable)
python -m historygen run <slug>
```

`new` prints the `<slug>` it created. The finished video is `projects/<slug>/final.mp4` and the
title/description/hashtags are in `projects/<slug>/metadata.json`.

### Recipes

**Short, any topic** (the default; ~55s vertical 9:16 — auto style)
```bash
python -m historygen new "How coffee changed the world"
python -m historygen run <slug>
```

**Video, any topic** (longer; set the length with `--minutes`)
```bash
python -m historygen new "The history of the internet" --minutes 5
python -m historygen run <slug>
```

**Video, landscape 16:9** (e.g. for YouTube)
```bash
python -m historygen new "Why cities feel lonely" --minutes 8 --orientation horizontal
python -m historygen run <slug>
```

**English, male voice** (any recipe — override language & voice)
```bash
python -m historygen new "The fall of Constantinople" --language en --gender male
python -m historygen run <slug>
```

**Forcing a style** (optional — override `auto`)
```bash
python -m historygen new "Osmanlı'nın kuruluşu" --genre historical
python -m historygen new "Yalnızlık salgını" --genre sociological
```

### All `new` options

| Flag | Values | Default | Purpose |
|------|--------|---------|---------|
| `topic` (positional) | any string | — | The subject of the video (also seeds the slug) |
| `--genre` | `auto`, `historical`, `sociological` | `auto` | Leave off to let the model pick the style; set it only to force one |
| `--minutes` | number | `~0.9` (≈55s, a Short) | Target spoken length. Leave off for a Short; set it for a longer Video (drives scene count) |
| `--orientation` | `vertical`, `horizontal`, `square` | `vertical` | Frame shape: 9:16 Short, 16:9 landscape, or 1:1 |
| `--language` | code, e.g. `tr`, `en` | `tr` | Script + narration language |
| `--gender` | `male`, `female` | `female` | Narration voice gender |

> **Short vs. Video:** a *Short* is just the default — vertical and under a minute. Passing
> `--minutes` with a bigger number (and optionally `--orientation horizontal`) is what makes a
> longer, wide *Video*. Nothing else in the pipeline changes.

### Genre / style

- **auto** (default) — the model reads your topic and picks the best presentation, mixing any
  of the visual types below as they fit. Works for any subject; you rarely need anything else.
- **historical** — force step-by-step history with dates/places; visuals use AI images,
  archive paintings/maps, and tactical maps.
- **sociological** — force social-issue commentary (hook → tension → turn → takeaway). Visuals
  use photorealistic modern AI images plus **stat cards**: a `stat_card` visual type rendered
  locally with Pillow (big number + label, no image API needed).

Everything downstream (narration, captions, music, assembly, `translate`) is genre-agnostic
and works the same for all three.

### `run` and the other commands

```bash
python -m historygen run <slug>                    # full pipeline (resumable; re-run safely)
python -m historygen run <slug> --stage visuals    # re-run one stage only
                                                   #   (script|narration|visuals|captions|music|assemble)
python -m historygen run <slug> --force            # ignore cache, regenerate everything
python -m historygen run <slug> --gender male      # change voice gender, then re-run
python -m historygen run <slug> --language en      # change narration language, then re-run

python -m historygen status <slug>                 # topic, genre, format, stages done, keys configured
python -m historygen list                          # list all project slugs

# clone a finished project into another language, reusing its visuals as-is
python -m historygen translate <slug> "History of Christianity" --language English
```

Overriding `--gender`/`--language` on `run` re-picks the voice and re-runs affected stages.

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
