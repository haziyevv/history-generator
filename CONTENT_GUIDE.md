# Content Manager Guide — Making Videos

This guide is for the person creating videos. **You do not need to know how the code
works.** You only need two commands and a handful of options. Everything below is a
copy-paste example with a plain explanation of what it does.

---

## The big picture

Every video is made in **two steps**:

1. **`new`** — writes the script and creates the project. Then you **review the script**.
2. **`run`** — turns the script into the finished video (voice, images, captions, music).

```bash
python -m historygen new "<your topic>"      # step 1: write the script
# ... open the script, read it, fix anything you want ...
python -m historygen run <slug>              # step 2: build the video
```

When step 1 finishes it prints a **`slug`** — a short name for the project (e.g.
`osmanli-devletinin-kurulusu`). You use that slug in every command after that.

The finished video is saved at `projects/<slug>/final.mp4`.
The title, description and hashtags are at `projects/<slug>/metadata.json`.

> **Why two steps?** Step 1 is cheap (just text). Step 2 costs money (voice + images).
> The pause between them lets you fix the script **before** paying to produce it. Always
> read the script first.

---

## Step 1: Just give it any topic

You don't have to categorise your idea. **Any topic works** — history, science, nature,
a social issue, a biography, a piece of technology, anything. By default the system reads
your topic and picks the best way to tell it (the right pacing, the right kind of visuals,
statistics where they help). So the simplest possible command is just:

```bash
python -m historygen new "How coffee changed the world"
```

The only choice you usually make is **how long / what shape** the video is:

| | What it is | How to make it |
|--|--|--|
| **Short** | Vertical, under 60 seconds (TikTok / Reels / YouTube Shorts) | Do nothing — this is the default |
| **Video** | Longer, any length, can be widescreen (YouTube) | Add `--minutes N` |

**Optional:** if you want to *force* a particular style you still can, with `--genre`
(see below) — but you never have to. Leaving it off lets the system decide.

---

## Every option, explained with an example

Below is every option you can add to the `new` command. Add as many as you want, in any
order.

### `--genre` — force a style (optional)

**Auto** (the default — you can leave it out): the system reads your topic and picks the
best style by itself, mixing historical visuals, modern photos and stat cards as they fit.
```bash
python -m historygen new "How coffee changed the world"
```
Use this for almost everything. Only reach for the options below if the auto result isn't
what you wanted and you want to pin it down.

**Historical** — force step-by-step history with dates and places (archive paintings, maps,
tactical maps):
```bash
python -m historygen new "Osmanlı Devleti'nin kuruluşu (1299)" --genre historical
```

**Sociological** — force social-issue commentary (hook → tension → turn → takeaway) using
modern photos and **stat cards** (big number + label on screen):
```bash
python -m historygen new "Yalnızlık salgını" --genre sociological
```

---

### `--minutes` — how long the video is

**Leave it out for a Short** (about 55 seconds):
```bash
python -m historygen new "Osmanlı Devleti'nin kuruluşu (1299)"
```

**Add it for a longer Video** — the number is the target length in minutes:
```bash
python -m historygen new "Osmanlı İmparatorluğu'nun yükselişi" --minutes 5
```
This makes a ~5-minute video. The system automatically adds more scenes to fill the time.
You can use decimals too (e.g. `--minutes 1.5`).

---

### `--orientation` — the shape of the frame

**Vertical** (the default — for Shorts, phones, TikTok/Reels):
```bash
python -m historygen new "Osmanlı'nın kuruluşu"
```

**Horizontal** (widescreen 16:9 — for YouTube):
```bash
python -m historygen new "Osmanlı İmparatorluğu'nun yükselişi" --minutes 8 --orientation horizontal
```

**Square** (1:1 — for feed posts):
```bash
python -m historygen new "Osmanlı'nın kuruluşu" --orientation square
```

---

### `--language` — the language of the narration

**Turkish** (the default — you can leave it out):
```bash
python -m historygen new "Osmanlı'nın kuruluşu"
```

**English** (use the language code `en`):
```bash
python -m historygen new "The fall of Constantinople" --language en
```
Common codes: `tr` = Turkish, `en` = English, `de` = German, `fr` = French, `es` = Spanish.

---

### `--gender` — the voice

**Female** (the default — you can leave it out):
```bash
python -m historygen new "Osmanlı'nın kuruluşu"
```

**Male:**
```bash
python -m historygen new "Osmanlı'nın kuruluşu" --gender male
```

---

## Full recipes (copy, paste, change the topic)

**Any topic, Short** — the everyday default (just give it an idea):
```bash
python -m historygen new "How coffee changed the world"
python -m historygen run <slug>
```

**Any topic, longer Video** (5 minutes):
```bash
python -m historygen new "The history of the internet" --minutes 5
python -m historygen run <slug>
```

**Video, widescreen for YouTube** (8 minutes):
```bash
python -m historygen new "Why cities feel lonely" --minutes 8 --orientation horizontal
python -m historygen run <slug>
```

**English video with a male voice** (options combine freely):
```bash
python -m historygen new "The fall of Constantinople" \
    --language en --gender male --minutes 4
python -m historygen run <slug>
```

**Forcing a style** (only if you want to override auto):
```bash
python -m historygen new "Osmanlı Devleti'nin kuruluşu (1299)" --genre historical
python -m historygen new "Yalnızlık salgını" --genre sociological
```

---

## Quick reference — all `new` options

| Option | Choices | Default | Meaning |
|--------|---------|---------|---------|
| `"topic"` | any text | — | The subject of the video (put it in quotes) |
| `--genre` | `auto`, `historical`, `sociological` | `auto` | Leave out to let the system pick the style; set it only to force one |
| `--minutes` | a number | ~0.9 (a Short) | Video length. Leave out for a Short; set it for a longer Video |
| `--orientation` | `vertical`, `horizontal`, `square` | `vertical` | Frame shape: phone 9:16, widescreen 16:9, or square 1:1 |
| `--language` | `tr`, `en`, ... | `tr` | Narration language |
| `--gender` | `male`, `female` | `female` | Voice |

---

## After `new`: reviewing and building

**1. Review the script.** Open the file printed by `new`:
```
projects/<slug>/manifest.json
```
Read the scene narration and visual descriptions. Edit anything you don't like. Save.

**2. Build the video:**
```bash
python -m historygen run <slug>
```
This is safe to re-run — it only redoes what changed.

**3. Find your video:**
```
projects/<slug>/final.mp4          ← the video
projects/<slug>/metadata.json      ← title, description, hashtags
```

---

## Handy extra commands

**See how a project is doing** (what's done, what's left, format, genre):
```bash
python -m historygen status <slug>
```

**List all your projects:**
```bash
python -m historygen list
```

**Rebuild only one part** — e.g. after you swap an image or edit the script, redo just the
images or just the final assembly instead of everything:
```bash
python -m historygen run <slug> --stage visuals
python -m historygen run <slug> --stage assemble
```
Stages, in order: `script`, `narration`, `visuals`, `captions`, `music`, `assemble`.

**Force a full regeneration** (ignore what's cached, redo everything from scratch):
```bash
python -m historygen run <slug> --force
```

**Change the voice or language of an existing project, then rebuild:**
```bash
python -m historygen run <slug> --gender male
python -m historygen run <slug> --language en
```

**Make the same video in another language, reusing the images** (no need to regenerate
pictures — great for translating a finished Turkish video into English):
```bash
python -m historygen translate <slug> "History of Christianity" --language English
```

---

## Replacing a wrong image

Sometimes an AI image is wrong (wrong flag, wrong building). To fix just that one:

1. Save your replacement picture over the wrong one at:
   ```
   projects/<slug>/assets/visual_NN.jpg
   ```
   where `NN` is the two-digit scene number (e.g. `visual_03.jpg`).
2. Rebuild just the final video:
   ```bash
   python -m historygen run <slug> --stage assemble
   ```
Your dropped-in image is picked up automatically.

---

## If something looks wrong or empty

The pipeline still runs without API keys — but visuals become plain placeholders and the
voice uses estimated timing. If your video has grey placeholder images or no narration,
the keys aren't set up. Check with:
```bash
python -m historygen status <slug>
```
The bottom of the output shows which service keys are configured. Ask whoever set up the
project to add the missing keys (see the main `README.md` → Setup).
