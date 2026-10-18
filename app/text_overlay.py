"""
app/text_overlay.py - TEXT composition with Pillow (text_mode = "overlay").

Why do this at all if the image model can draw text?
  * Image models still misspell words, especially long quotes or Hindi/Hinglish.
  * Marketing teams need the headline pixel-perfect and on-brand.
So in "overlay" mode the prompt asks for a clean empty band, and WE draw the
quote on top - exact spelling, exact colour, exact font, every time.
"""
from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .config import config
from .schemas import AdSettings

# PROVIDED: font files shipped in app/fonts (DejaVu, free licence) so Windows,
# Mac and Linux all render the same.
FONT_FILES = {
    "modern-sans": "DejaVuSans-Bold.ttf",
    "elegant-serif": "DejaVuSerif-Bold.ttf",
    "bold-display": "DejaVuSansCondensed-Bold.ttf",
}


@lru_cache(maxsize=64)
def load_font(font_style: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """PROVIDED: bundled font -> common system fonts -> Pillow default."""
    candidates = [str(config.fonts_dir / FONT_FILES.get(font_style, "DejaVuSans-Bold.ttf")),
                  "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    """PROVIDED: pixel width of `text` in `font`."""
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def hex_to_rgb(c: str) -> tuple[int, int, int]:
    """PROVIDED: '#E4572E' -> (228, 87, 46)"""
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


# ---------------------------------------------------------------------------
# TODO 4a - wrap_text()
# ---------------------------------------------------------------------------
def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """
    Greedy word wrap by PIXEL width (not characters - fonts are proportional).

    Walk the words; keep adding a word to the current line while
    text_width(draw, candidate, font) <= max_width; otherwise start a new line.
    A single word wider than max_width goes on its own line (do not split words).
    Empty text -> [].
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# TODO 4b - overlay_quote()
# ---------------------------------------------------------------------------
def overlay_quote(png: bytes, quote: str, s: AdSettings) -> bytes:
    """
    Draw the quote (and the brand name, if any) onto the image. Return PNG bytes.

    Suggested recipe (W, H = image size):
      1. img = Image.open(...).convert("RGBA"); make a transparent layer the same size
      2. Band: height ~ 24% of H, full width, at s.quote_position
         (top -> y=0, center -> middle, bottom -> y=H-band)
      3. Fit the text: start with font size ~ 7% of H and shrink (step 2px, min 18px)
         until wrap_text(..., max_width = 88% of W) gives lines whose total height
         (line height = 1.2 x font size) fits in ~75% of the band.
      4. Draw a rounded rectangle behind the text block in s.accent_color with
         alpha ~200 (so the photo shows through a little).
      5. Draw each line centred horizontally in s.text_color; a 2px dark shadow
         first makes it readable on any background.
      6. If s.brand_name: draw it in small caps-ish (upper case, ~40% of the font
         size) under the quote, inside the same panel.
      7. Image.alpha_composite(img, layer) -> convert("RGB") -> save PNG -> bytes.
    Blank quote -> return the input unchanged.
    """
    if not quote.strip():
        return png

    with Image.open(io.BytesIO(png)) as source:
        img = source.convert("RGBA")
    width, height = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    band_height = max(1, int(height * 0.24))
    band_top = {
        "top": 0,
        "center": (height - band_height) // 2,
        "bottom": height - band_height,
    }[s.quote_position]
    max_width = max(1, int(width * 0.88))
    font_size = max(18, int(height * 0.07))
    brand = s.brand_name.upper() if s.brand_name else ""

    while True:
        font = load_font(s.font_style, font_size)
        lines = wrap_text(draw, quote, font, max_width)
        line_height = max(1, int(font_size * 1.2))
        brand_size = max(1, int(font_size * 0.4))
        brand_font = load_font(s.font_style, brand_size)
        brand_lines = wrap_text(draw, brand, brand_font, max_width)
        brand_line_height = max(1, int(brand_size * 1.2))
        gap = max(2, font_size // 5) if brand_lines else 0
        block_height = len(lines) * line_height + gap + len(brand_lines) * brand_line_height
        fits_width = all(text_width(draw, line, font) <= max_width for line in lines)
        fits_width = fits_width and all(
            text_width(draw, line, brand_font) <= max_width for line in brand_lines
        )
        if font_size <= 18 or (fits_width and block_height <= band_height * 0.75):
            break
        font_size = max(18, font_size - 2)

    margin_x = max(1, int(width * 0.03))
    margin_y = max(1, int(band_height * 0.04))
    draw.rounded_rectangle(
        (margin_x, band_top + margin_y,
         width - margin_x - 1, band_top + band_height - margin_y - 1),
        radius=max(1, int(height * 0.02)),
        fill=(*hex_to_rgb(s.accent_color), 200),
    )
    color = (*hex_to_rgb(s.text_color), 255)

    def draw_centered(line: str, line_font, top: float) -> None:
        left, upper, right, _ = draw.textbbox((0, 0), line, font=line_font)
        x = (width - (right - left)) / 2 - left
        y = top - upper
        draw.text((x + 2, y + 2), line, font=line_font, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=line_font, fill=color)

    y = band_top + (band_height - block_height) / 2
    for line in lines:
        draw_centered(line, font, y)
        y += line_height
    y += gap
    for line in brand_lines:
        draw_centered(line, brand_font, y)
        y += brand_line_height

    result = Image.alpha_composite(img, layer).convert("RGB")
    output = io.BytesIO()
    result.save(output, format="PNG")
    return output.getvalue()
