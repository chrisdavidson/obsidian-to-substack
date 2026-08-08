"""Extract Markdown pipe tables and export to CSV for Datawrapper."""

import csv
import io
import re
import logging
from pathlib import Path

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


def replace_tables_with_placeholders(
    text: str,
    tables: list[tuple[int, int, str, list[list[str]]]],
    output_dir: str,
) -> str:
    """Replace each table with a placeholder comment and export to CSV.

    Tables are processed in reverse order to preserve line numbers.
    Returns the modified text.
    """
    if not tables:
        return text

    out_dir = Path(output_dir)
    lines = text.split("\n")

    for idx, (start, end, _raw, parsed_rows) in enumerate(reversed(tables), 1):
        table_num = len(tables) - idx + 1
        csv_name = f"table-{table_num}.csv"
        table_to_csv(parsed_rows, str(out_dir / csv_name))

        placeholder = f"<!-- TABLE {table_num}: See {csv_name} for Datawrapper import -->"
        lines[start:end + 1] = [placeholder]

    return "\n".join(lines)


def _rows_to_csv_string(parsed_rows: list[list[str]]) -> str:
    """Convert parsed rows to a CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in parsed_rows:
        writer.writerow(row)
    return buf.getvalue()


def replace_tables_with_embeds(
    text: str,
    tables: list[tuple[int, int, str, list[list[str]]]],
    output_dir: str,
    api_token: str,
    article_title: str = "",
) -> str:
    """Replace tables with Datawrapper chart images and export CSV backups.

    Each table is published to Datawrapper, exported as a PNG, and replaced
    with an <img> tag pointing to the local PNG. This ensures charts render
    correctly both in browser preview and when pasted into Substack via --copy.

    CSV files are still saved locally as backups. Falls back to placeholder
    comments if the API call fails.
    """
    from obsidian_to_substack.datawrapper import export_chart_png, publish_table

    if not tables:
        return text

    out_dir = Path(output_dir)
    lines = text.split("\n")

    for idx, (start, end, _raw, parsed_rows) in enumerate(reversed(tables), 1):
        table_num = len(tables) - idx + 1
        csv_name = f"table-{table_num}.csv"
        table_to_csv(parsed_rows, str(out_dir / csv_name))

        csv_data = _rows_to_csv_string(parsed_rows)
        title = f"{article_title} — Table {table_num}" if article_title else f"Table {table_num}"

        try:
            embed_url, chart_id = publish_table(csv_data, title, api_token)
            logger.info("Table %d published to Datawrapper: %s", table_num, embed_url)

            png_name = f"table-{table_num}.png"
            png_bytes = export_chart_png(chart_id, api_token)
            png_path = out_dir / png_name
            png_path.write_bytes(png_bytes)
            logger.info("Table %d exported as PNG: %s", table_num, png_name)

            alt_text = title.replace('"', "&quot;")
            replacement = (
                f'<!-- Datawrapper: {embed_url} -->\n'
                f'<img src="{png_name}" alt="{alt_text}">'
            )
        except Exception as exc:
            logger.warning(
                "Datawrapper publish failed for table %d: %s. Using placeholder.",
                table_num, exc,
            )
            replacement = f"<!-- TABLE {table_num}: See {csv_name} for Datawrapper import -->"

        lines[start:end + 1] = [replacement]

    return "\n".join(lines)
