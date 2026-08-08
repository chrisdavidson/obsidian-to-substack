"""Render a Markdown table to a PNG image.

Substack's composer does not accept pasted HTML tables, so the pipeline used to
emit a placeholder comment and leave the author to hand-draw the table as an
SVG. This renders the same thing automatically, from the Markdown source.

Pillow is used rather than SVG because it provides real font metrics — cell
widths and text wrapping have to be measured, not estimated.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

FONT_CANDIDATES = {
    "regular": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ),
    "bold": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
    "italic": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    ),
    "bolditalic": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
    ),
}

# Visual constants — tuned to read like body text in the Substack composer.
#
# Substack renders body images at up to 1456 CSS pixels wide. Anything wider is
# scaled down in the browser, shrinking the text with it — so the table is laid
# out to a logical width of MAX_TABLE_WIDTH and `scale` (dpi/96) multiplies that
# for pixel density, giving a crisp image rather than a shrunken one.
FONT_SIZE = 17
CELL_PADDING_X = 14
CELL_PADDING_Y = 10
MAX_TABLE_WIDTH = 1400
MIN_CELL_WIDTH = 70
BORDER = 1

COLOR_TEXT = (34, 34, 34)
COLOR_HEADER_BG = (242, 242, 242)
COLOR_BORDER = (196, 196, 196)
COLOR_BG = (255, 255, 255)

BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
ITALIC_PATTERN = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)|(?<!_)_([^_]+?)_(?!_)")


@dataclass(frozen=True)
class Span:
    """A run of text sharing one style."""

    text: str
    bold: bool = False
    italic: bool = False

    @property
    def style(self) -> str:
        if self.bold and self.italic:
            return "bolditalic"
        if self.bold:
            return "bold"
        if self.italic:
            return "italic"
        return "regular"


class FontSet:
    """Resolve the four style variants once, with a graceful fallback."""

    def __init__(self, size: int = FONT_SIZE) -> None:
        self.size = size
        self.fonts = {
            style: self._load(paths, size) for style, paths in FONT_CANDIDATES.items()
        }

    @staticmethod
    def _load(paths: tuple[str, ...], size: int):
        for path in paths:
            if Path(path).exists():
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
        logger.warning("No TrueType font found; falling back to the bitmap default")
        return ImageFont.load_default()

    def get(self, style: str):
        return self.fonts.get(style, self.fonts["regular"])

    def measure(self, text: str, style: str) -> int:
        font = self.get(style)
        return int(font.getlength(text)) if hasattr(font, "getlength") else font.getbbox(text)[2]

    def line_height(self) -> int:
        ascent, descent = self.get("regular").getmetrics()
        return ascent + descent


BOLD_TAGS = {"strong", "b"}
ITALIC_TAGS = {"em", "i"}
CODE_TICKS = re.compile(r"`([^`]*)`")


def parse_spans(cell: str) -> list[Span]:
    """Split a cell into styled runs.

    Cells arrive already converted to inline HTML by `table_handler._parse_row`
    (`<strong>`, `<em>`), but raw Markdown markers survive in sources that were
    not converted, so both forms are handled. Backticks are stripped — the
    renderer has no monospace variant, and a literal backtick reads as a typo.
    """
    soup = BeautifulSoup(cell, "html.parser")
    spans: list[Span] = []

    def walk(node, bold: bool, italic: bool) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                text = CODE_TICKS.sub(r"\1", str(child))
                if bold or italic:
                    if text:
                        spans.append(Span(text, bold, italic))
                else:
                    spans.extend(_markdown_spans(text))
            else:
                walk(
                    child,
                    bold or child.name in BOLD_TAGS,
                    italic or child.name in ITALIC_TAGS,
                )

    walk(soup, False, False)
    return [s for s in spans if s.text] or [Span("")]


def _markdown_spans(text: str) -> list[Span]:
    """Apply Markdown bold/italic markers to a plain run."""
    spans: list[Span] = []
    cursor = 0

    for match in BOLD_PATTERN.finditer(text):
        if match.start() > cursor:
            spans.extend(_italic_spans(text[cursor : match.start()]))
        inner = match.group(1) or match.group(2) or ""
        stripped = ITALIC_PATTERN.sub(lambda m: m.group(1) or m.group(2) or "", inner)
        spans.append(Span(stripped, bold=True, italic=stripped != inner))
        cursor = match.end()

    if cursor < len(text):
        spans.extend(_italic_spans(text[cursor:]))

    return spans


def _italic_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    cursor = 0
    for match in ITALIC_PATTERN.finditer(text):
        if match.start() > cursor:
            spans.append(Span(text[cursor : match.start()]))
        spans.append(Span(match.group(1) or match.group(2) or "", italic=True))
        cursor = match.end()
    if cursor < len(text):
        spans.append(Span(text[cursor:]))
    return spans


def wrap_spans(spans: list[Span], fonts: FontSet, max_width: int) -> list[list[Span]]:
    """Greedy word wrap that preserves per-word styling."""
    lines: list[list[Span]] = [[]]
    width = 0

    for span in spans:
        for word in re.findall(r"\S+\s*", span.text):
            piece = Span(word, span.bold, span.italic)
            piece_width = fonts.measure(word, piece.style)
            if width + piece_width > max_width and lines[-1]:
                lines.append([])
                width = 0
            lines[-1].append(piece)
            width += piece_width

    return [line for line in lines if line] or [[Span("")]]


def _line_width(line: list[Span], fonts: FontSet) -> int:
    return sum(fonts.measure(s.text, s.style) for s in line)


def render_table(
    rows: list[list[str]],
    output_path: str,
    alignments: list[str] | None = None,
    scale: float = 1.0,
) -> str:
    """Render parsed table rows to a PNG. Returns the output path.

    `rows[0]` is treated as the header. `alignments` holds "left", "center", or
    "right" per column, as parsed from the Markdown separator row.
    """
    if not rows:
        raise ValueError("Cannot render an empty table")

    fonts = FontSet(max(1, int(FONT_SIZE * scale)))
    padding_x = int(CELL_PADDING_X * scale)
    padding_y = int(CELL_PADDING_Y * scale)
    max_total = int(MAX_TABLE_WIDTH * scale)
    min_cell = int(MIN_CELL_WIDTH * scale)
    line_height = fonts.line_height()

    column_count = max(len(row) for row in rows)
    normalized = [list(row) + [""] * (column_count - len(row)) for row in rows]
    alignments = (alignments or [])[:column_count]
    alignments += ["left"] * (column_count - len(alignments))

    parsed = [[parse_spans(cell) for cell in row] for row in normalized]

    # Column widths: start from the widest natural cell, then shrink
    # proportionally if the table would exceed the target width. Shrinking
    # proportionally keeps a naturally-wide column wider than a narrow one
    # instead of forcing every column to the same size.
    natural_widths = [
        max(_line_width(row[column], fonts) for row in parsed) + padding_x * 2
        for column in range(column_count)
    ]
    total_natural = sum(natural_widths)

    if total_natural > max_total:
        floor = min_cell + padding_x * 2
        shrinkable = sum(max(0, w - floor) for w in natural_widths)
        overflow = total_natural - max_total
        if shrinkable > 0:
            ratio = min(1.0, overflow / shrinkable)
            widths = [
                max(floor, w - int(max(0, w - floor) * ratio)) for w in natural_widths
            ]
        else:
            widths = [floor] * column_count
    else:
        widths = natural_widths

    # Wrap each cell to its column width and derive row heights.
    wrapped = [
        [
            wrap_spans(row[column], fonts, widths[column] - padding_x * 2)
            for column in range(column_count)
        ]
        for row in parsed
    ]
    heights = [
        max(len(cell) for cell in row) * line_height + padding_y * 2 for row in wrapped
    ]

    width = sum(widths) + BORDER
    height = sum(heights) + BORDER

    image = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(image)

    y = 0
    for row_index, row in enumerate(wrapped):
        x = 0
        is_header = row_index == 0
        for column, cell in enumerate(row):
            box = (x, y, x + widths[column], y + heights[row_index])
            if is_header:
                draw.rectangle(box, fill=COLOR_HEADER_BG)
            draw.rectangle(box, outline=COLOR_BORDER, width=BORDER)

            text_y = y + padding_y
            for line in cell:
                line_width = _line_width(line, fonts)
                available = widths[column] - padding_x * 2
                if alignments[column] == "center":
                    text_x = x + padding_x + (available - line_width) // 2
                elif alignments[column] == "right":
                    text_x = x + widths[column] - padding_x - line_width
                else:
                    text_x = x + padding_x

                for span in line:
                    style = "bold" if is_header and span.style == "regular" else span.style
                    draw.text(
                        (text_x, text_y), span.text, font=fonts.get(style), fill=COLOR_TEXT
                    )
                    text_x += fonts.measure(span.text, style)
                text_y += line_height

            x += widths[column]
        y += heights[row_index]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG", optimize=True)
    logger.info("Rendered table -> %s (%dx%d)", output_path, width, height)
    return output_path
