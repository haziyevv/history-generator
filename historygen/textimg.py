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

# Bold first (covers Turkish glyphs), then regular fallbacks.
_FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu[wdth,wght].ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # macOS
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
    W, H = SETTINGS.render.width, SETTINGS.render.height
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
    W, H = SETTINGS.render.width, SETTINGS.render.height
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if text.strip():
        _draw_centered(img, text, size=size, target_y_frac=target_y_frac)
    img.save(out)
    return out


def placeholder_image(out: Path, label: str, bg: tuple[int, int, int] = (26, 26, 46)) -> Path:
    """Full-frame opaque PNG with a centred label — stands in for a missing visual."""
    W, H = SETTINGS.render.width, SETTINGS.render.height
    img = Image.new("RGB", (W, H), bg)
    _draw_centered(img, label, size=56, target_y_frac=0.5)
    img.save(out)
    return out


def stat_card(
    out: Path, value: str, label: str,
    bg: tuple[int, int, int] = (17, 20, 33), accent: tuple[int, int, int] = (232, 93, 79),
) -> Path:
    """Full-frame data card: huge number, caption beneath, accent bar between them.

    Rendered locally (no API), so stat cards always work even with no keys. Saved as
    JPEG so it drops straight into the assemble stage's `visual_NN.jpg` slot.
    """
    W, H = SETTINGS.render.width, SETTINGS.render.height
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # Big number, upper-middle. Shrink font if the value is long so it never overflows.
    size = 300
    while size > 120 and draw.textlength(value or "—", font=_font(size)) > W * 0.84:
        size -= 20
    _draw_centered(img, value or "—", size=size, target_y_frac=0.40, fill=_hex(accent), stroke=0)

    # Accent bar.
    bar_w, bar_h = int(W * 0.22), 12
    x0 = (W - bar_w) // 2
    y0 = int(H * 0.52)
    draw.rounded_rectangle([x0, y0, x0 + bar_w, y0 + bar_h], radius=bar_h // 2, fill=accent)

    # Caption below the bar.
    if label.strip():
        _draw_centered(img, label, size=64, target_y_frac=0.62, fill="white", stroke=0, max_w_frac=0.78)

    img.save(out, quality=92)
    return out


def scene_card(
    out: Path, heading: str, subheading: str = "",
    bg: tuple[int, int, int] = (17, 20, 33), accent: tuple[int, int, int] = (232, 93, 79),
) -> Path:
    """Full-frame fallback visual for a scene whose image could not be generated.

    Same visual language as `stat_card` (dark ground, accent bar) so it blends into
    the video instead of reading as an error. Rendered locally, so it always works.
    """
    W, H = SETTINGS.render.width, SETTINGS.render.height
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    heading = heading.strip() or "•"
    # Shrink the heading if it's long so one line never overflows after wrapping.
    size = 140
    while size > 72 and draw.textlength(heading, font=_font(size)) > W * 1.6:
        size -= 12
    _draw_centered(img, heading, size=size, target_y_frac=0.42, stroke=0)

    bar_w, bar_h = int(W * 0.22), 12
    x0 = (W - bar_w) // 2
    y0 = int(H * 0.53)
    draw.rounded_rectangle([x0, y0, x0 + bar_w, y0 + bar_h], radius=bar_h // 2, fill=accent)

    if subheading.strip():
        _draw_centered(
            img, subheading, size=54, target_y_frac=0.62,
            fill=_hex((170, 176, 194)), stroke=0, max_w_frac=0.78,
        )

    img.save(out, quality=92)
    return out


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb
