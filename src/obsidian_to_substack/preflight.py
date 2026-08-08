"""Warn about constructs known to break in Substack, before the author pastes.

Every check here corresponds to a defect recovered in docs/FINDINGS.md by
diffing pipeline output against published posts. The point is that a defect
found once should never again be discovered by pasting and squinting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

# Substack rejects images above this size.
MAX_IMAGE_MB = 10.0

# Wider than Substack's body column; the browser scales these down and the
# content inside them shrinks with it.
MAX_IMAGE_WIDTH = 2912


@dataclass(frozen=True)
class Warning_:
    """A preflight warning, tied to the requirement that motivated it."""

    check: str
    requirement: str
    message: str

    def format(self) -> str:
        return f"  [{self.requirement}] {self.message}"


def _check_placeholder_comments(soup: BeautifulSoup) -> list[Warning_]:
    warnings = []
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "TABLE" in str(comment).upper():
            warnings.append(
                Warning_(
                    "table_placeholder",
                    "TBL-01",
                    "A table placeholder comment is still in the output; it will "
                    "paste as nothing. Check that table rendering succeeded.",
                )
            )
    return warnings


def _check_duplicate_title(soup: BeautifulSoup) -> list[Warning_]:
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if headings and headings[0].name == "h1":
        count = len([h for h in headings if h.name == "h1"])
        if count == 1:
            return [
                Warning_(
                    "duplicate_title",
                    "FMT-02",
                    f"Output opens with a lone <h1> "
                    f"({headings[0].get_text(strip=True)[:50]!r}); Substack shows "
                    "its own title above the body, so this may paste as a "
                    "duplicate heading.",
                )
            ]
    return []


def _check_images(soup: BeautifulSoup, base_dir: Path) -> list[Warning_]:
    warnings = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src or src.startswith(("http://", "https://", "data:")):
            continue

        path = base_dir / src
        if not path.is_file():
            warnings.append(
                Warning_(
                    "missing_image",
                    "DIAG-02",
                    f"Image {src!r} is referenced but not present in the output "
                    "directory; it will paste broken.",
                )
            )
            continue

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_IMAGE_MB:
            warnings.append(
                Warning_(
                    "image_too_large",
                    "DIAG-03",
                    f"Image {src!r} is {size_mb:.1f} MB; Substack rejects images "
                    f"over {MAX_IMAGE_MB:.0f} MB.",
                )
            )

        try:
            from PIL import Image

            with Image.open(path) as opened:
                if opened.size[0] > MAX_IMAGE_WIDTH:
                    warnings.append(
                        Warning_(
                            "image_too_wide",
                            "DIAG-03",
                            f"Image {src!r} is {opened.size[0]}px wide; Substack "
                            f"scales anything over {MAX_IMAGE_WIDTH}px down, "
                            "shrinking its content.",
                        )
                    )
        except OSError:
            warnings.append(
                Warning_(
                    "unreadable_image",
                    "DIAG-03",
                    f"Image {src!r} could not be opened; it is probably corrupt.",
                )
            )

    return warnings


def check(html: str, base_dir: str | Path) -> list[Warning_]:
    """Run every preflight check against rendered output."""
    soup = BeautifulSoup(html, "html.parser")
    base = Path(base_dir)

    return [
        *_check_placeholder_comments(soup),
        *_check_duplicate_title(soup),
        *_check_images(soup, base),
    ]


def report(warnings: list[Warning_]) -> str:
    """Render warnings for the terminal. Empty string when there are none."""
    if not warnings:
        return ""

    lines = [
        f"\n  {len(warnings)} preflight warning(s) — "
        "these constructs have broken in Substack before:"
    ]
    lines.extend(warning.format() for warning in warnings)
    lines.append("")
    return "\n".join(lines)
