"""Extract Markdown pipe tables, render them to PNG figures, and export a
CSV data sidecar alongside each one."""

import csv
import re
import logging
from pathlib import Path

from .table_render import render_table

logger = logging.getLogger(__name__)

TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
SEPARATOR_PATTERN = re.compile(r"^\s*\|[\s:_-]+(\|[\s:_-]+)+\|\s*$")

BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
BOLD_ITALIC_PATTERN = re.compile(r"\*\*\*(.+?)\*\*\*")


def _md_inline_to_html(text: str) -> str:
    """Convert markdown bold/italic markers to HTML tags.

    Processes bold-italic (***) before bold (**) before italic (*) to
    avoid partial matches.
    """
    result = BOLD_ITALIC_PATTERN.sub(r"<strong><em>\1</em></strong>", text)
    result = BOLD_PATTERN.sub(r"<strong>\1</strong>", result)
    result = ITALIC_PATTERN.sub(r"<em>\1</em>", result)
    return result


def _parse_row(line: str) -> list[str]:
    """Parse a pipe-delimited row into a list of cell values."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [_md_inline_to_html(cell.strip()) for cell in stripped.split("|")]


def _is_separator(line: str) -> bool:
    """Check if a line is a table separator row (e.g. | :--- | :--- |)."""
    return bool(SEPARATOR_PATTERN.match(line))


def extract_tables(text: str) -> list[tuple[int, int, str, list[list[str]]]]:
    """Find all pipe-delimited tables in the text.

    Returns a list of (start_line, end_line, raw_text, parsed_rows).
    Line numbers are 0-indexed. The separator row is excluded from parsed_rows.
    """
    lines = text.split("\n")
    tables: list[tuple[int, int, str, list[list[str]]]] = []

    i = 0
    while i < len(lines):
        if not TABLE_ROW_PATTERN.match(lines[i]):
            i += 1
            continue

        start = i
        block_lines: list[str] = [lines[i]]
        i += 1

        while i < len(lines) and TABLE_ROW_PATTERN.match(lines[i]):
            block_lines.append(lines[i])
            i += 1

        has_separator = any(_is_separator(line) for line in block_lines)
        if not has_separator or len(block_lines) < 3:
            continue

        parsed_rows = [
            _parse_row(line)
            for line in block_lines
            if not _is_separator(line)
        ]

        raw_text = "\n".join(block_lines)
        end = start + len(block_lines) - 1
        tables.append((start, end, raw_text, parsed_rows))

    return tables


def parse_alignments(raw_text: str) -> list[str]:
    """Read column alignment from a table's separator row.

    `:---` is left, `:---:` is center, `---:` is right. Returns an empty list
    when the block has no separator row.
    """
    for line in raw_text.split("\n"):
        if not _is_separator(line):
            continue
        alignments = []
        for cell in _parse_row(line):
            marker = cell.strip()
            starts = marker.startswith(":")
            ends = marker.endswith(":")
            if starts and ends:
                alignments.append("center")
            elif ends:
                alignments.append("right")
            else:
                alignments.append("left")
        return alignments
    return []


def table_to_csv(parsed_rows: list[list[str]], output_path: str) -> str:
    """Write parsed table rows to a CSV file. Returns the output path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in parsed_rows:
            writer.writerow(row)

    logger.info("Table exported to CSV: %s", path.name)
    return str(path)


def replace_tables_with_images(
    text: str,
    tables: list[tuple[int, int, str, list[list[str]]]],
    output_dir: str,
    scale: float = 1.0,
) -> str:
    """Replace each table with a rendered PNG figure, and export the CSV too.

    This is the only table path. Substack's composer will not accept a
    pasted HTML table, so the table is rendered to an image the same way the
    author used to do by hand. The CSV is still written alongside it as a
    standalone data sidecar.

    Tables are processed in reverse order to preserve line numbers.
    """
    if not tables:
        return text

    out_dir = Path(output_dir)
    lines = text.split("\n")

    for idx, (start, end, raw, parsed_rows) in enumerate(reversed(tables), 1):
        table_num = len(tables) - idx + 1
        table_to_csv(parsed_rows, str(out_dir / f"table-{table_num}.csv"))

        png_name = f"table-{table_num}.png"
        try:
            render_table(
                parsed_rows,
                str(out_dir / png_name),
                alignments=parse_alignments(raw),
                scale=scale,
            )
        except (ValueError, OSError) as exc:
            logger.error(
                "Table %d could not be rendered (%s); leaving a placeholder",
                table_num,
                exc,
            )
            lines[start:end + 1] = [
                f"<!-- TABLE {table_num}: render failed, see table-{table_num}.csv -->"
            ]
            continue

        figure = f'<figure><img src="{png_name}" alt="Table {table_num}"></figure>'
        lines[start:end + 1] = [figure]

    return "\n".join(lines)


