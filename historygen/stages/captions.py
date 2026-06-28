"""Stage 4 — captions.

Produce a list of time-windowed caption events ({start, end, text}) on the global
timeline, synced to narration word-timings where available (grouped into short chunks),
or one line per scene when there are no timings. The assemble stage renders each event
to a PNG and overlays it (this ffmpeg build has no subtitle filter).
"""

from __future__ import annotations

import json

from historygen.manifest import Manifest

CHUNK = 3  # words shown together


def run(manifest: Manifest) -> None:
    project = manifest.project
    if not project.scenes:
        print("  captions: no scenes yet")
        return

    events: list[dict] = []
    t0 = 0.0  # running start of the current scene on the global timeline
    for scene in project.scenes:
        dur = scene.actual_seconds or scene.est_seconds
        words = scene.word_timings
        if words:
            for i in range(0, len(words), CHUNK):
                chunk = words[i : i + CHUNK]
                events.append({
                    "start": round(t0 + chunk[0]["start"], 3),
                    "end": round(t0 + chunk[-1]["end"], 3),
                    "text": " ".join(w["word"] for w in chunk),
                })
        else:
            events.append({
                "start": round(t0, 3),
                "end": round(t0 + dur, 3),
                "text": scene.narration,
            })
        t0 += dur

    out = manifest.assets / "captions.json"
    out.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    project.captions_file = str(out)
    manifest.save()
    print(f"  captions: {len(events)} caption events -> {out.name}")
