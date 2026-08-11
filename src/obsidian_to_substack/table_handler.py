"""Extract Markdown pipe tables, render them to PNG figures, and export a
CSV data sidecar alongside each one."""

import csv
import re
import logging
from pathlib import Path
from typing import NamedTuple

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


class TableReplacement(NamedTuple):
    """The rewritten text, and the PNGs written while rewriting it.

    The second field exists because `convert_article` builds its `png_files`
    result from what its callees report, and this function used to report
    nothing — the table PNGs were written to disk and referenced by the body
    but named nowhere the caller could see. A consumer assembling a
    publishable directory from `png_files` therefore left them behind.

    Returning them beats reconstructing `table-{n}.png` at the call site: that
    name is formed here, and a caller that re-derives it silently collects
    nothing the day this module renames anything.
    """

    text: str
    png_files: list[str]


def replace_tables_with_images(
    text: str,
    tables: list[tuple[int, int, str, list[list[str]]]],
    output_dir: str,
    scale: float = 1.0,
) -> TableReplacement:
    """Replace each table with a rendered PNG figure, and export the CSV too.

    This is the only table path. Substack's composer will not accept a
    pasted HTML table, so the table is rendered to an image the same way the
    author used to do by hand. The CSV is still written alongside it as a
    standalone data sidecar.

    Tables are processed in reverse order to preserve line numbers, so the
    reported PNGs are sorted back into table order before returning — a caller
    reading the list should see table-1 before table-2.

    Only PNGs that were actually written are reported. A table whose render
    raises leaves a placeholder comment and no file; naming it anyway would
    hand the caller a path that never existed, which fails harder than the
    omission this return value fixes.
    """
    if not tables:
        return TableReplacement(text, [])

    out_dir = Path(output_dir)
    lines = text.split("\n")
    written: list[tuple[int, str]] = []

    for idx, (start, end, raw, parsed_rows) in enumerate(reversed(tables), 1):
        table_num = len(tables) - idx + 1
        table_to_csv(parsed_rows, str(out_dir / f"table-{table_num}.csv"))

        png_name = f"table-{table_num}.png"
        png_path = out_dir / png_name
        try:
            render_table(
                parsed_rows,
                str(png_path),
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

        # Recorded only past the except branch — a render that raised wrote no
        # file, and `continue` above skips this.
        written.append((table_num, str(png_path)))

        figure = f'<figure><img src="{png_name}" alt="Table {table_num}"></figure>'
        lines[start:end + 1] = [figure]

    return TableReplacement(
        "\n".join(lines), [path for _num, path in sorted(written)]
    )


