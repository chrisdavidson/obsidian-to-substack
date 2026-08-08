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
import shutil
from pathlib import Path

from .obsidian_syntax import IMAGE_EMBED_PATTERN

logger = logging.getLogger(__name__)

RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def referenced_images(text: str) -> list[str]:
    """Return every raster filename the text embeds, in order, deduplicated."""
    seen: list[str] = []
    for match in IMAGE_EMBED_PATTERN.finditer(text):
        filename = match.group(1).strip()
        if Path(filename).suffix.lower() in RASTER_SUFFIXES and filename not in seen:
            seen.append(filename)
    return seen


def find_image(filename: str, search_dirs: list[Path]) -> Path | None:
    """Locate an embedded image across the article's search directories."""
    for directory in search_dirs:
        candidate = Path(directory) / filename
        if candidate.is_file():
            return candidate

    # Obsidian resolves embeds vault-wide by basename, so fall back to a
    # shallow search rather than failing on a subdirectory mismatch.
    basename = Path(filename).name
    for directory in search_dirs:
        for candidate in Path(directory).glob(f"**/{basename}"):
            if candidate.is_file():
                return candidate
    return None


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

        destination = out / Path(filename).name
        out.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        copied[filename] = str(destination)
        logger.debug("Copied embedded image %s", filename)

    if copied:
        logger.info("Copied %d embedded raster image(s)", len(copied))
    return copied
