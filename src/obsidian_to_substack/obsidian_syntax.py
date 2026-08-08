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

# The author's vault writes footnote definitions as `[^1] - text` (a hyphen,
# en dash, em dash, or double hyphen separator) where python-markdown's
# footnotes extension requires `[^1]: text` (a colon). Longest-first
# alternation matters: with "-" tried before "--", "[^1] -- text" would match
# only the first hyphen and leave a stray "-" glued to the definition text.
FOOTNOTE_DEF_PATTERN = re.compile(
    r"^\[\^(?P<label>[^\]]+)\](?P<pre_ws>\s*)(?P<sep>--|—|–|-)(?P<post_ws>\s+)(?P<def_text>.*)$"
)
FOOTNOTE_REF_PATTERN = re.compile(r"\[\^([^\]]+)\]")


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


def _is_fence_delimiter(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def normalize_footnote_definitions(text: str) -> str:
    """Rewrite the author's hyphen-form footnote definitions to colon form.

    The vault writes `[^1] - text` (hyphen, en dash, em dash, or double
    hyphen); python-markdown's footnotes extension only matches `[^1]: text`
    (colon), so the hyphen form degrades to plain text rather than erroring
    (F1). Rewriting is gated on the label being referenced elsewhere in the
    document \u2014 a bare `[^foo] - bar` mid-document, with nothing else pointing
    at `foo`, is not a definition, and its own leading `[^foo]` does not
    count as the reference that licenses it (that would make every
    definition self-license).

    Two passes over the document's lines, both tracking fenced-code state
    with a single toggling boolean: pass one collects referenced labels
    (skipping fenced regions and each definition line's own marker), pass
    two rewrites definition-shaped lines whose label was collected. A
    footnote-shaped line inside a fenced block, and an already-canonical
    `[^1]: text` line (the colon is not in the separator class, so it never
    matches), are both returned byte-identical.

    Pure: returns a new string, never mutates the input.
    """
    lines = text.split("\n")

    referenced_labels: set[str] = set()
    in_fence = False
    for line in lines:
        if _is_fence_delimiter(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        def_match = FOOTNOTE_DEF_PATTERN.match(line)
        exclude_span = (0, def_match.start("pre_ws")) if def_match else None
        for ref_match in FOOTNOTE_REF_PATTERN.finditer(line):
            if exclude_span is not None and ref_match.span() == exclude_span:
                continue
            referenced_labels.add(ref_match.group(1))

    result_lines: list[str] = []
    in_fence = False
    for line in lines:
        if _is_fence_delimiter(line):
            in_fence = not in_fence
            result_lines.append(line)
            continue
        if in_fence:
            result_lines.append(line)
            continue

        def_match = FOOTNOTE_DEF_PATTERN.match(line)
        if def_match and def_match.group("label") in referenced_labels:
            result_lines.append(
                f"[^{def_match.group('label')}]: {def_match.group('def_text')}"
            )
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def transform_obsidian_syntax(
    text: str,
    image_map: dict[str, str] | None = None,
) -> str:
    """Apply all Obsidian-specific syntax transformations.

    Returns a new string; the input is not mutated.
    """
    # Footnote normalization runs FIRST: convert_em_dashes rewrites a spaced
    # double hyphen into a bare em dash with no surrounding spaces, which
    # would destroy the " -- " separator normalize_footnote_definitions
    # keys on (F5). Reordering this call silently re-breaks hyphen-form
    # footnotes — do not move it.
    result = normalize_footnote_definitions(text)
    result = replace_image_embeds(result, image_map)
    result = replace_internal_links(result)
    result = convert_em_dashes(result)
    return result
