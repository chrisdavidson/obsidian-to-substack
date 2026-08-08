"""Tests for table extraction and CSV export."""

import tempfile
from pathlib import Path

from obsidian_to_substack.table_handler import (
    _md_inline_to_html,
    extract_tables,
    table_to_csv,
)


class TestMdInlineToHtml:
    def test_bold(self):
        assert _md_inline_to_html("**hello**") == "<strong>hello</strong>"

    def test_italic(self):
        assert _md_inline_to_html("*hello*") == "<em>hello</em>"

    def test_bold_italic(self):
        assert _md_inline_to_html("***hello***") == "<strong><em>hello</em></strong>"

    def test_mixed_inline(self):
        result = _md_inline_to_html("**bold** and *italic*")
        assert result == "<strong>bold</strong> and <em>italic</em>"

    def test_no_formatting(self):
        assert _md_inline_to_html("plain text") == "plain text"

    def test_bold_in_sentence(self):
        result = _md_inline_to_html("This is **important** info")
        assert result == "This is <strong>important</strong> info"

    def test_multiple_bold(self):
        result = _md_inline_to_html("**one** and **two**")
        assert result == "<strong>one</strong> and <strong>two</strong>"


class TestExtractTables:
    def test_single_table(self):
        text = (
            "Before\n\n"
            "| Col A | Col B |\n"
            "| :--- | :--- |\n"
            "| val 1 | val 2 |\n"
            "| val 3 | val 4 |\n\n"
            "After"
        )
        tables = extract_tables(text)
        assert len(tables) == 1
        start, end, raw, rows = tables[0]
        assert len(rows) == 3  # header + 2 data rows, separator excluded
        assert rows[0] == ["Col A", "Col B"]
        assert rows[1] == ["val 1", "val 2"]

    def test_multiple_tables(self):
        text = (
            "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
            "Middle text\n\n"
            "| C | D |\n| --- | --- |\n| 3 | 4 |\n"
        )
        tables = extract_tables(text)
        assert len(tables) == 2

    def test_no_tables(self):
        text = "Just regular text\n\nWith paragraphs."
        tables = extract_tables(text)
        assert tables == []

    def test_pipe_without_separator_is_not_table(self):
        text = "| this is not | a table |\n| no separator here |\n"
        tables = extract_tables(text)
        assert tables == []

    def test_bold_cells_converted_to_html(self):
        text = "| **Header** | Normal |\n| --- | --- |\n| **bold val** | plain |\n"
        tables = extract_tables(text)
        assert len(tables) == 1
        rows = tables[0][3]
        assert rows[0] == ["<strong>Header</strong>", "Normal"]
        assert rows[1] == ["<strong>bold val</strong>", "plain"]

    def test_alignment_markers(self):
        text = "| Left | Center | Right |\n| :--- | :---: | ---: |\n| a | b | c |\n"
        tables = extract_tables(text)
        assert len(tables) == 1
        assert tables[0][3][0] == ["Left", "Center", "Right"]


class TestTableToCsv:
    def test_csv_output(self):
        rows = [["Feature", "Status"], ["Bold", "Yes"], ["Tables", "No"]]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = table_to_csv(rows, f"{tmpdir}/test.csv")
            content = Path(csv_path).read_text()
            assert "Feature,Status" in content
            assert "Bold,Yes" in content
            assert "Tables,No" in content
