"""Render text to PNGs with Pillow.

This ffmpeg build has no freetype/libass (no `drawtext`/`ass` filters), so all text —
placeholder labels, on-screen dates/numbers, and captions — is drawn here as PNGs and
composited by ffmpeg's `overlay` filter. That also makes the pipeline portable to any
ffmpeg build.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from historygen.config import SETTINGS

W, H = SETTINGS.render.width, SETTINGS.render.height

# Bold first (covers Turkish glyphs), then regular fallbacks.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]


@lru_cache(maxsize=16)
def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _draw_centered(
    img: Image.Image, text: str, *, size: int, target_y_frac: float,
    fill: str = "white", stroke: int = 6, max_w_frac: float = 0.86,
) -> None:
    draw = ImageDraw.Draw(img)
    font = _font(size)
    wrapped = _wrap(draw, text, font, W * max_w_frac)
    bbox = draw.multiline_textbbox(
        (0, 0), wrapped, font=font, stroke_width=stroke, align="center", spacing=14
    )
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) / 2 - bbox[0]
    y = H * target_y_frac - th / 2 - bbox[1]
    draw.multiline_text(
        (x, y), wrapped, font=font, fill=fill, stroke_width=stroke,
        stroke_fill="black", align="center", spacing=14,
    )


def transparent_text(out: Path, text: str, *, size: int, target_y_frac: float) -> Path:
    """Full-frame transparent PNG with centred, outlined text — for overlaying."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if text.strip():
        _draw_centered(img, text, size=size, target_y_frac=target_y_frac)
    img.save(out)
    return out


def placeholder_image(out: Path, label: str, bg: tuple[int, int, int] = (26, 26, 46)) -> Path:
    """Full-frame opaque PNG with a centred label — stands in for a missing visual."""
    img = Image.new("RGB", (W, H), bg)
    _draw_centered(img, label, size=56, target_y_frac=0.5)
    img.save(out)
    return out
