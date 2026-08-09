"""Warn about constructs known to break in Substack, before the author pastes.

Every check here corresponds to a defect recovered in docs/FINDINGS.md by
diffing pipeline output against published posts. The point is that a defect
found once should never again be discovered by pasting and squinting.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

# Substack rejects images above this size.
MAX_IMAGE_MB = 10.0

# Wider than Substack's body column; the browser scales these down and the
# content inside them shrinks with it.
MAX_IMAGE_WIDTH = 2912

# A footnote-shaped literal, e.g. "[^1]" — the marker that survives when a
# hyphen-form definition never matched python-markdown's footnotes extension
# (F1) and the reference degraded to plain text.
FOOTNOTE_MARKER_PATTERN = re.compile(r"\[\^[^\]]+\]")

# The Obsidian comment marker. strip_obsidian_comments (obsidian_syntax.py)
# only handles a same-line pair and a lone-marker-line block, and nothing
# else, by design — a general "opener anywhere, closer anywhere later"
# scanner would risk silently deleting prose between two unrelated markers.
# This check is the other half of that trade-off: an unhandled or
# unbalanced marker is meant to reach the rendered output and be reported
# here rather than be silently guessed at.
OBSIDIAN_COMMENT_MARKER_PATTERN = re.compile(r"%%")


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


def _check_footnotes(soup: BeautifulSoup) -> list[Warning_]:
    """Warn on both footnote failure modes found in the v1.0 audit.

    F1: a literal `[^1]` marker surviving into the rendered text — the
    hyphen-form definition never matched python-markdown's footnotes
    extension, so the reference degraded to plain text instead of erroring.
    F2: reference markup (`sup[id^="fnref:"]`) surviving with no footnotes
    section (`li[id^="fn:"]`) beneath it — the section was deleted
    downstream by strip_unsupported_elements' generic div handling before
    that path preserved div.footnote. Two distinct checks because they have
    different causes and different fixes.

    Searches the soup's text content, not the raw HTML string — the raw
    string carries `id`/`href` attribute values (e.g. `id="fnref:1"`) that
    legitimately contain footnote-shaped substrings, and matching those
    would warn on correct output.
    """
    warnings = []

    for text_node in soup.find_all(string=FOOTNOTE_MARKER_PATTERN):
        if isinstance(text_node, Comment):
            continue
        if text_node.find_parent(["code", "pre"]):
            # Documentation of the syntax, not a failure.
            continue
        for match in FOOTNOTE_MARKER_PATTERN.finditer(str(text_node)):
            warnings.append(
                Warning_(
                    "footnote_marker_literal",
                    "GRD-02",
                    f"A literal footnote marker {match.group()!r} survived "
                    "into the rendered text; it will paste as visible "
                    "garbage instead of a footnote.",
                )
            )

    has_footnote_ref = bool(soup.select('sup[id^="fnref:"]'))
    has_footnote_section = bool(soup.select('li[id^="fn:"]'))
    if has_footnote_ref and not has_footnote_section:
        warnings.append(
            Warning_(
                "footnote_section_missing",
                "GRD-02",
                "Footnote reference markup is present but no footnotes "
                "section survived; the marker will paste with nothing for "
                "the reader to correlate it with.",
            )
        )

    return warnings


def _check_obsidian_comments(soup: BeautifulSoup) -> list[Warning_]:
    """Warn when an Obsidian %%comment%% marker survives into rendered text.

    strip_obsidian_comments only handles a same-line pair and a
    lone-marker-line block, and nothing else, by design (see the module
    comment on OBSIDIAN_COMMENT_MARKER_PATTERN) — that narrowness is the
    defect this check backstops: an unhandled or unbalanced marker is
    reported here instead of being silently guessed at, so the author's
    private notes are not one un-warned paste away from going public.

    Searches the soup's text content, not the raw HTML string, for the same
    reason _check_footnotes does. Two skips, both load-bearing: a marker
    inside a `code`/`pre` parent is documentation of the syntax, not a
    failure, and a marker inside an HTML `Comment` node is invisible in the
    composer and already _check_placeholder_comments' territory — do not
    remove either skip.

    Unlike _check_footnotes, this emits at most one warning per text node
    rather than one per match: several stray markers in one paragraph are
    one defect (an unclosed or unbalanced comment) worth reporting once,
    not a warning per marker.
    """
    warnings = []
    for text_node in soup.find_all(string=OBSIDIAN_COMMENT_MARKER_PATTERN):
        if isinstance(text_node, Comment):
            continue
        if text_node.find_parent(["code", "pre"]):
            # Documentation of the syntax, not a failure.
            continue
        warnings.append(
            Warning_(
                "obsidian_comment",
                "GRD-02",
                "A comment marker ('%%') survived into the rendered text. "
                "The likely cause is an unbalanced or unclosed marker in "
                "the source — the stripper handles a same-line pair and a "
                "lone-marker-line block, and nothing else by design. Note "
                "that an odd number of lone-marker lines makes the stripper "
                "skip block removal for the WHOLE document rather than "
                "risk deleting the prose between an unclosed opener and the "
                "next comment, so this output may be entirely unfiltered. "
                "Close the stray marker in the source and re-run. Private "
                "notes are about to paste into the post.",
            )
        )
    return warnings


def _check_slug_title(soup: BeautifulSoup, title_from_slug: bool) -> list[Warning_]:
    """Warn when the title fell back to the filename AND reads as a slug.

    The fallback on its own is not a defect and must not warn: 20 of the 25
    published articles supply neither a frontmatter `title:` nor a single
    leading H1, so all 20 take their title from the filename — and all 20
    read correctly, because their filenames are written as sentence-cased
    headlines, punctuation and all. Warning on the fallback alone would fire
    on 80% of known-good output, which is the noise `_check_footnotes`
    already refuses to make.

    Requiring the resolved title to contain no uppercase letter narrows that
    to 3 of the 25 — all genuinely weak titles. Crude, but measured; do not
    "simplify" the uppercase condition away without re-measuring, or this
    check goes back to warning on correct output.

    `title_from_slug` has to be passed in: the resolved title is in the
    document, but nothing in the HTML records which of the three sources
    produced it, and a `<title>` matching the filename is equally consistent
    with a deliberate frontmatter title.
    """
    if not title_from_slug:
        return []

    title_tag = soup.find("title")
    if title_tag is None:
        return []

    title = title_tag.get_text(strip=True)
    if not title or any(char.isupper() for char in title):
        return []

    return [
        Warning_(
            "slug_title",
            "GRD-02",
            f"The title {title!r} was taken from the filename, because the "
            "source supplied neither a frontmatter 'title:' nor a single "
            "leading H1. It reads as a slug rather than a title, and it goes "
            "to the title field on the primary selection.",
        )
    ]


def check(
    html: str, base_dir: str | Path, *, title_from_slug: bool = False
) -> list[Warning_]:
    """Run every preflight check against rendered output.

    `title_from_slug` is keyword-only and defaulted so the two-positional-arg
    call shape keeps working.
    """
    soup = BeautifulSoup(html, "html.parser")
    base = Path(base_dir)

    return [
        *_check_placeholder_comments(soup),
        *_check_duplicate_title(soup),
        *_check_images(soup, base),
        *_check_footnotes(soup),
        *_check_obsidian_comments(soup),
        *_check_slug_title(soup, title_from_slug),
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
