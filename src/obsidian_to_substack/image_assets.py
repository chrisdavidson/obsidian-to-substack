"""Collect raster images an article embeds directly.

`export_all_svgs` handles `![[diagram.svg]]` by rasterizing it into the output
directory. An embed that already names a raster file — `![[diagram.png]]` —
had no such path: nothing copied it, so the `<img src="diagram.png">` in the
output pointed at a file that was not there. Clipboard inlining then skipped
it and the image pasted broken.

Both embed forms now resolve, so the author never needs to pre-rasterize a
diagram by hand before embedding it (DIAG-02).
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from urllib.parse import unquote

from .obsidian_syntax import IMAGE_EMBED_PATTERN

logger = logging.getLogger(__name__)

RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SVG_SUFFIXES = {".svg"}

# Standard Markdown images: ![alt](path). Alt text can be long and contain
# brackets-free prose, and the path may be percent-encoded.
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _referenced_matching_suffix(
    text: str, patterns: tuple[re.Pattern, ...], suffixes: set[str]
) -> list[str]:
    """Shared core of referenced_images and referenced_svgs.

    Writes the http/https/data skip, the percent-decode, the suffix test,
    and the order-preserving dedup exactly once for both callers.
    """
    seen: list[str] = []

    for pattern in patterns:
        for match in pattern.finditer(text):
            filename = match.group(1).strip()
            if filename.startswith(("http://", "https://", "data:")):
                continue
            if Path(unquote(filename)).suffix.lower() not in suffixes:
                continue
            if filename not in seen:
                seen.append(filename)

    return seen


def referenced_images(text: str) -> list[str]:
    """Return every raster image the text references, in order, deduplicated.

    Covers both Obsidian embeds (`![[a.png]]`) and Markdown images
    (`![alt](a.png)`), since the vault uses both.
    """
    return _referenced_matching_suffix(
        text, (IMAGE_EMBED_PATTERN, MARKDOWN_IMAGE_PATTERN), RASTER_SUFFIXES
    )


def referenced_svgs(text: str) -> list[str]:
    """Return every SVG the text references, in order, deduplicated.

    Scans `IMAGE_EMBED_PATTERN` (`![[x.svg]]`) only, not
    `MARKDOWN_IMAGE_PATTERN` (`![alt](x.svg)`). This is a measured
    exclusion, not an assumption: `![alt](x.svg)` occurs 0 times across the
    70 Markdown files in the two vault article directories and 0 times in
    tests/fixtures/, while `![[x.svg]]` occurs in 11 of them. The
    consequence a later reader should know: the Markdown form does produce
    a broken reference today — nothing copies it, and preflight's
    `missing_image` check catches it — so a caller of this function
    under-reports relative to preflight on a form the corpus does not use.
    If that form ever appears, the fix is to widen this pattern list, not
    to fork the rule.
    """
    return _referenced_matching_suffix(text, (IMAGE_EMBED_PATTERN,), SVG_SUFFIXES)


def find_image(filename: str, search_dirs: list[Path]) -> Path | None:
    """Locate a referenced image across the article's search directories.

    Paths are percent-decoded first (`saas-two-boxes%201.png`), then tried as
    written, then by basename. The basename fallback matters because Obsidian
    resolves embeds vault-wide, and because archived articles keep stale path
    prefixes from wherever they were drafted.
    """
    decoded = unquote(filename)

    for directory in search_dirs:
        candidate = Path(directory) / decoded
        if candidate.is_file():
            return candidate

    basename = Path(decoded).name
    for directory in search_dirs:
        candidate = Path(directory) / basename
        if candidate.is_file():
            return candidate
        for found in Path(directory).glob(f"**/{basename}"):
            if found.is_file():
                return found
    return None


def rewrite_image_refs(text: str, copied: dict[str, str]) -> str:
    """Point Markdown image paths at the copied file's basename.

    Obsidian embeds are basenamed by `replace_image_embeds`, but Markdown
    images pass through the renderer untouched, so a stale or encoded path
    would survive into the output.
    """
    def _replace(match: re.Match) -> str:
        path = match.group(1).strip()
        if path not in copied:
            return match.group(0)
        return match.group(0).replace(path, Path(copied[path]).name)

    return MARKDOWN_IMAGE_PATTERN.sub(_replace, text)


def copy_raster_embeds(
    text: str, search_dirs: list[Path], output_dir: str
) -> dict[str, str]:
    """Copy every embedded raster image into the output directory.

    Returns a map of embed name -> copied path, suitable for merging into the
    image map that `transform_obsidian_syntax` consumes.
    """
    out = Path(output_dir)
    copied: dict[str, str] = {}

    for filename in referenced_images(text):
        source = find_image(filename, search_dirs)
        if source is None:
            logger.warning("Embedded image not found: %s", filename)
            continue

        destination = out / Path(unquote(filename)).name
        out.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        copied[filename] = str(destination)
        logger.debug("Copied embedded image %s", filename)

    if copied:
        logger.info("Copied %d embedded raster image(s)", len(copied))
    return copied
