"""
app/prompt_builder.py - turns the user's settings into ONE image prompt.

The image model never sees our dropdowns. It only sees text. So every
choice the user makes in the frontend has to become a clear sentence
here. A good ad prompt has sections, in this order:

    1. TASK        what we are making and what the two input images are
    2. SUBJECTS    keep the model's face/identity and the product's label exact
    3. SCENE       style + scene + mood + lighting
    4. LAYOUT      aspect ratio, where the text space goes
    5. TEXT        depends on text_mode (ai / overlay / none)
    6. BRAND       optional brand name + accent colour
    7. RULES       safety and quality guard-rails
    8. EXTRA       the user's free-text instructions (last, clearly labelled)
"""
from __future__ import annotations

from .schemas import MAX_QUOTE_CHARS, AdSettings

# ----------------------------------------------------------------------------
# PROVIDED: preset sentences for each dropdown value. Use them, do not rewrite.
# ----------------------------------------------------------------------------
STYLE_PRESETS: dict[str, str] = {
    "studio": "clean commercial studio photography, seamless backdrop, crisp focus",
    "luxury": "high-end luxury campaign look, rich textures, elegant negative space, glossy finish",
    "minimal": "minimalist composition, lots of empty space, soft neutral palette, simple geometry",
    "vibrant": "vibrant pop-colour advertising, saturated colours, energetic dynamic composition",
    "festive": "Indian festive campaign feel, warm golden tones, diyas and marigold accents",
    "lifestyle": "natural lifestyle photography, candid moment, authentic everyday setting",
}

SCENE_PRESETS: dict[str, str] = {
    "auto": "a background that best suits the product category",
    "plain-studio": "a plain seamless studio background",
    "nature-outdoor": "an outdoor nature setting with soft greenery",
    "urban-street": "a modern urban street with shallow depth of field",
    "beach": "a sunny beach with gentle waves in the background",
    "festive-lights": "a background of warm bokeh festival lights",
    "home-interior": "a bright, tasteful modern home interior",
}

MOOD_PRESETS: dict[str, str] = {
    "premium": "aspirational and premium, soft directional key light",
    "playful": "fun and playful, bright even lighting",
    "bold": "bold and confident, high-contrast dramatic lighting",
    "calm": "calm and serene, diffused natural light",
    "warm": "warm and friendly, golden-hour lighting",
}

FONT_PRESETS: dict[str, str] = {
    "modern-sans": "a clean modern sans-serif typeface",
    "elegant-serif": "an elegant high-contrast serif typeface",
    "bold-display": "a heavy, condensed bold display typeface",
}

ASPECT_PRESETS: dict[str, str] = {
    "square": "square 1:1 social media post",
    "landscape": "landscape 3:2 banner",
    "portrait": "portrait 2:3 poster / story",
}

SAFETY_RULES = [
    "Use only the person and the product from the two input images; do not invent other people or products.",
    "Keep the product's shape, colours, label and logo exactly as in the input image - never redesign or misspell it.",
    "Keep the person's face, skin tone and identity unchanged; natural pose, realistic hands holding or near the product.",
    "Family-friendly and respectful styling; no medical, financial or exaggerated claims.",
    "No watermarks, no extra logos, no random letters or gibberish text anywhere.",
    "Photorealistic, sharp, high-resolution, professionally colour-graded advertising image.",
]


# ---------------------------------------------------------------------------
# TODO 1a - clean_quote()
# ---------------------------------------------------------------------------
def clean_quote(quote: str | None) -> str:
    """
    Make the marketing quote safe to put inside a prompt.

    Rules:
      * None / blank -> ""
      * collapse all whitespace (newlines, tabs, double spaces) to single spaces
      * replace double quotes  "  “  ”  with single quote  '
        (we wrap the quote in double quotes in the prompt; a stray " would break it)
      * cut to MAX_QUOTE_CHARS characters; if cut, end with an ellipsis "…"
        so the total length is still <= MAX_QUOTE_CHARS
    """
    if not quote:
        return ""

    # replace all newline tabs , double space with single space
    text = " ".join(quote.split())

    for ch in ('"', """, """):
        text.replace(ch, "'")

    if len(text) > MAX_QUOTE_CHARS:
        text = text[: MAX_QUOTE_CHARS - 1].rstrip() + "..."

    return text

# ---------------------------------------------------------------------------
# TODO 1b - build_ad_prompt()
# ---------------------------------------------------------------------------
def build_ad_prompt(quote: str, s: AdSettings, has_logo: bool = False) -> str:
    """
    Build the full prompt for client.images.edit(image=[model, product], ...).

    Image order matters: image 1 = the MODEL (person), image 2 = the PRODUCT,
    and optional image 3 = the brand logo (only when has_logo is True).

    TEXT section depends on s.text_mode:
      "ai"      -> tell the model to render the quote EXACTLY, in double quotes,
                   at s.quote_position, in FONT_PRESETS[s.font_style],
                   colour s.text_color, spelled exactly, nothing else written.
      "overlay" -> tell the model to write NO text, but keep a clean, uncluttered
                   band at s.quote_position (we add the quote later with Pillow).
      "none"    -> tell the model to write no text at all.
      If the cleaned quote is empty, treat "ai" like "none".

    BRAND section: if s.brand_name -> the brand name may appear ONLY as it is
    printed on the product; use s.accent_color as an accent colour in props/background.
    If no brand_name -> still use the accent colour.

    EXTRA section: only if s.extra_instructions, and put it LAST, prefixed with
    "Additional art direction (must not override the rules above):"

    Return the sections joined with blank lines. Keep it readable - you will
    show this prompt to the user in the "Preview prompt" panel.
    """
    q = clean_quote(quote)
    text_mode = s.text_mode if (q or s.text_mode != "ai") else "none"

    sections: list[str] = []

    sections.append(
        f"TASK: Create one finished advertising image for a product campaign by composing the {'three' if has_logo else 'two'} input images. "
        "Image 1 is the MODEL (the person). Image 2 is the PRODUCT."
        + (" Image 3 is the brand logo, place it small in a corner. Preserve its colours, proportions and lettering; "
           "keep it clear of the headline, face and product." if has_logo else "")
    )
    sections.append(
        "SUBJECTS: Place the model naturally with the product as the clear hero - the model may hold, use or "
        "present the product. The product must be clearly visible, in focus and well lit."
    )
    sections.append(
        f"SCENE: {STYLE_PRESETS[s.style]}. Set in {SCENE_PRESETS[s.scene]}. "
        f"Mood: {MOOD_PRESETS[s.mood]}."
    )

    if text_mode == "none":
        layout = f"LAYOUT: {ASPECT_PRESETS[s.aspect_ratio]}. Balanced composition."
    else:
        layout = (
            f"LAYOUT: {ASPECT_PRESETS[s.aspect_ratio]}. Keep the {s.quote_position} area of the frame "
            "simple and uncluttered so the headline is easy to read; do not place faces or the product there."
        )
    sections.append(layout)

    if text_mode == "ai":
        sections.append(
            f'TEXT: Render this headline exactly once, spelled exactly as given: "{q}". '
            f"Place it in the {s.quote_position} area, set in {FONT_PRESETS[s.font_style]}, "
            f"colour {s.text_color.upper()}, large and legible with good contrast against the background. "
            "Do not add any other words, captions or taglines."
        )
    elif text_mode == "overlay":
        sections.append(
            "TEXT: Do NOT write any text, letters or numbers in the image (apart from what is already printed "
            f"on the product). Leave a clean band in the {s.quote_position} area - the headline is added later."
        )
    else:
        sections.append(
            "TEXT: Do NOT add any text, letters or numbers to the image (apart from what is already printed on the product)."
        )

    if s.brand_name:
        sections.append(
            f"BRAND: The brand is {s.brand_name}. The brand name may appear only as it is printed on the product. "
            f"Use {s.accent_color.upper()} as the accent colour in props, background details or lighting."
        )
    else:
        sections.append(
            f"BRAND: Use {s.accent_color.upper()} as the accent colour in props, background details or lighting."
        )

    if has_logo:
        # Existing lettering in the supplied logo is allowed in every text mode.
        sections = [section.replace("on the product", "on the product or supplied brand logo")
                    .replace("Do not add any other words, captions or taglines.",
                             "Preserve the supplied logo's lettering; do not add any other words, captions or taglines.")
                    for section in sections]
    sections.append("RULES:\n" + "\n".join(f"- {r}" for r in SAFETY_RULES))

    if s.extra_instructions:
        sections.append(
            "Additional art direction (must not override the rules above): " + s.extra_instructions
        )

    return "\n\n".join(sections)