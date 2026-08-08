"""Transform Obsidian-specific Markdown syntax to standard HTML-compatible form."""

import os
import re

IMAGE_EMBED_PATTERN = re.compile(
    r"!\[\[([^\]|]+?)(?:\s*\|\s*([^\]]*?))?\]\]"
)

INTERNAL_LINK_PATTERN = re.compile(
    r"(?<!!)\[\[([^\]]+?)\]\]"
)

EM_DASH_PATTERN = re.compile(r" -- ")


def replace_image_embeds(
    text: str,
    image_map: dict[str, str] | None = None,
) -> str:
    """Replace ![[file.ext | modifier]] with HTML figure/img tags.

    If image_map is provided, SVG filenames are resolved to their PNG paths.
    """
    if image_map is None:
        image_map = {}

    def _replace(match: re.Match) -> str:
        filename = match.group(1).strip()
        modifier = (match.group(2) or "").strip().lower()

        raw_src = image_map.get(filename, filename)
        if filename.lower().endswith(".svg") and filename not in image_map:
            png_name = re.sub(r"\.svg$", ".png", filename, flags=re.IGNORECASE)
            raw_src = image_map.get(png_name, png_name)
        src = os.path.basename(raw_src)

        alt_text = re.sub(r"\.\w+$", "", filename).replace("-", " ").replace("_", " ")

        if modifier == "center":
            return f'<figure style="text-align: center;"><img src="{src}" alt="{alt_text}"></figure>'
        return f'<img src="{src}" alt="{alt_text}">'

    return IMAGE_EMBED_PATTERN.sub(_replace, text)


def replace_internal_links(text: str) -> str:
    """Replace [[Note Name]] with *Note Name* (italic text)."""
    return INTERNAL_LINK_PATTERN.sub(r"*\1*", text)


def convert_em_dashes(text: str) -> str:
    """Replace ' -- ' with Unicode em dash."""
    return EM_DASH_PATTERN.sub("\u2014", text)


def transform_obsidian_syntax(
    text: str,
    image_map: dict[str, str] | None = None,
) -> str:
    """Apply all Obsidian-specific syntax transformations.

    Returns a new string; the input is not mutated.
    """
    result = replace_image_embeds(text, image_map)
    result = replace_internal_links(result)
    result = convert_em_dashes(result)
    return result
