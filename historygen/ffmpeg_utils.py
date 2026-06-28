"""Thin wrappers around ffmpeg/ffprobe.

Keep the shell-outs here; stages build clips by calling these primitives. Everything
targets the 9:16 canvas from RenderSettings. Functions raise RuntimeError on failure
with the ffmpeg stderr attached, so callers get a real error rather than a silent bad file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from historygen.config import SETTINGS

R = SETTINGS.render


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({' '.join(cmd[:3])} ...):\n{proc.stderr[-2000:]}"
        )


def probe_duration(path: str | Path) -> float:
    """Return media duration in seconds via ffprobe."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(path),
        ],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return 0.0
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


def static_clip(image: Path, out: Path, seconds: float) -> None:
    """A still image held (no zoom) for `seconds` — used for placeholders/maps."""
    vf = (
        f"scale={R.width}:{R.height}:force_original_aspect_ratio=increase,"
        f"crop={R.width}:{R.height},fps={R.fps}"
    )
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image),
        "-t", f"{seconds:.3f}", "-vf", vf,
        "-pix_fmt", "yuv420p", str(out),
    ])


def still_to_clip(image: Path, out: Path, seconds: float, zoom_in: bool = True) -> None:
    """Ken Burns: scale a still to fill 9:16 and slowly zoom over `seconds`."""
    frames = max(1, int(seconds * R.fps))
    # zoom from 1.0 -> 1.12 (or reverse). Oversample to 4K first for smooth zoompan.
    if zoom_in:
        z = "min(zoom+0.0009,1.12)"
    else:
        z = "if(lte(zoom,1.0),1.12,max(1.0,zoom-0.0009))"
    vf = (
        f"scale={R.width*2}:{R.height*2}:force_original_aspect_ratio=increase,"
        f"crop={R.width*2}:{R.height*2},"
        f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={R.width}x{R.height}:fps={R.fps}"
    )
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image),
        "-t", f"{seconds:.3f}", "-vf", vf,
        "-pix_fmt", "yuv420p", str(out),
    ])


def video_to_clip(video: Path, out: Path, seconds: float) -> None:
    """Scale/crop a video to fill 9:16, looping if short, trimmed to exactly `seconds`."""
    vf = (
        f"scale={R.width}:{R.height}:force_original_aspect_ratio=increase,"
        f"crop={R.width}:{R.height},fps={R.fps}"
    )
    _run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(video),
        "-t", f"{seconds:.3f}", "-vf", vf,
        "-an", "-pix_fmt", "yuv420p", str(out),
    ])


def overlay_image(clip: Path, png: Path | None, out: Path) -> None:
    """Composite a full-frame transparent PNG over a (silent) clip for its whole length."""
    if png is None:
        shutil.copyfile(clip, out)
        return
    _run([
        "ffmpeg", "-y", "-i", str(clip), "-i", str(png),
        "-filter_complex", "[0:v][1:v]overlay=0:0",
        "-pix_fmt", "yuv420p", str(out),
    ])


def attach_audio(clip: Path, audio: Path | None, out: Path, seconds: float) -> None:
    """Give a video clip a narration track, padded/truncated to exactly `seconds`."""
    if audio is None:
        _run([
            "ffmpeg", "-y", "-i", str(clip),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", f"{seconds:.3f}", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out),
        ])
        return
    _run([
        "ffmpeg", "-y", "-i", str(clip), "-i", str(audio),
        "-filter_complex", f"[1:a]apad=whole_dur={seconds:.3f}[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-t", f"{seconds:.3f}", "-c:v", "copy", "-c:a", "aac", str(out),
    ])


def concat(clips: list[Path], out: Path) -> None:
    """Concatenate same-format clips via the concat demuxer."""
    listfile = out.with_suffix(".txt")
    listfile.write_text(
        "".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8"
    )
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c", "copy", str(out),
    ])
    listfile.unlink(missing_ok=True)


def overlay_timed(video: Path, items: list[tuple[Path, float, float]], out: Path) -> None:
    """Overlay time-windowed PNGs (e.g. captions) onto a video, preserving its audio.

    `items` is a list of (png_path, start_seconds, end_seconds).
    """
    if not items:
        shutil.copyfile(video, out)
        return
    total = probe_duration(video) or (max(e for _p, _s, e in items) + 0.1)
    cmd = ["ffmpeg", "-y", "-i", str(video)]
    # Each PNG is a single frame; loop it for the whole (bounded) timeline so its
    # enable window — which may start well after t=0 — actually fires. The explicit
    # -t bounds the looped input so the graph always reaches EOF and terminates.
    for png, _s, _e in items:
        cmd += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(png)]
    parts, prev = [], "[0:v]"
    for i, (_png, s, e) in enumerate(items, start=1):
        label = f"[v{i}]"
        parts.append(f"{prev}[{i}:v]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'{label}")
        prev = label
    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", prev, "-map", "0:a?", "-c:a", "copy",
        "-pix_fmt", "yuv420p", str(out),
    ]
    _run(cmd)


def mix_music(video: Path, music: Path, out: Path, music_db: float = -18.0) -> None:
    """Duck background music under the existing voice track and mux it in."""
    _run([
        "ffmpeg", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(music),
        "-filter_complex",
        f"[1:a]volume={music_db}dB[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(out),
    ])
