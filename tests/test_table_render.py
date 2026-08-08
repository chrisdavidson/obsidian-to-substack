"""Tests for Markdown-table-to-PNG rendering (Phase 2, TBL-01..04, GRD-01)."""

import pytest
from PIL import Image

from obsidian_to_substack.table_handler import (
    extract_tables,
    parse_alignments,
    replace_tables_with_images,
)
from obsidian_to_substack.table_render import (
    MAX_TABLE_WIDTH,
    Span,
    parse_spans,
    render_table,
)

SIMPLE_TABLE = """Intro paragraph.

| Kind | Authority | Action |
| :--- | :---: | ---: |
| Derived | Traces to the axiom | Keep it |
| Hidden | Derives from nothing | Promote it |

Closing paragraph.
"""


class TestSpanParsing:
    def test_plain_text_is_one_regular_span(self):
        assert parse_spans("hello") == [Span("hello")]

    def test_bold_is_detected(self):
        spans = parse_spans("**loud**")
        assert spans == [Span("loud", bold=True)]

    def test_italic_is_detected(self):
        spans = parse_spans("*quiet*")
        assert spans == [Span("quiet", italic=True)]

    def test_underscore_italic_is_detected(self):
        assert parse_spans("_quiet_") == [Span("quiet", italic=True)]

    def test_mixed_styles_split_into_runs(self):
        spans = parse_spans("plain **bold** tail")
        assert [s.text.strip() for s in spans] == ["plain", "bold", "tail"]
        assert [s.bold for s in spans] == [False, True, False]

    def test_bold_italic_combines_both(self):
        spans = parse_spans("**_both_**")
        assert spans[0].bold and spans[0].italic

    def test_style_name_maps_to_font_variant(self):
        assert Span("x", bold=True, italic=True).style == "bolditalic"
        assert Span("x").style == "regular"


class TestRenderTable:
    def test_renders_a_readable_png(self, tmp_path):
        out = tmp_path / "t.png"
        render_table([["A", "B"], ["1", "2"]], str(out))

        image = Image.open(out)
        assert image.format == "PNG"
        assert image.size[0] > 0 and image.size[1] > 0

    def test_header_row_is_shaded(self, tmp_path):
        out = tmp_path / "t.png"
        render_table([["Header"], ["Body"]], str(out))

        pixels = Image.open(out).convert("RGB").load()
        assert pixels[3, 3] != (255, 255, 255)

    def test_table_never_exceeds_the_target_width(self, tmp_path):
        """Substack scales oversized images down, shrinking the text with them."""
        wide = [["col " + "x" * 60] * 6, ["data " + "y" * 60] * 6]
        out = tmp_path / "wide.png"
        render_table(wide, str(out))

        assert Image.open(out).size[0] <= MAX_TABLE_WIDTH + 8

    def test_scale_multiplies_pixel_density(self, tmp_path):
        rows = [["A", "B"], ["1", "2"]]
        one = tmp_path / "1.png"
        two = tmp_path / "2.png"
        render_table(rows, str(one), scale=1.0)
        render_table(rows, str(two), scale=2.0)

        assert Image.open(two).size[0] > Image.open(one).size[0]

    def test_ragged_rows_are_padded_not_dropped(self, tmp_path):
        out = tmp_path / "t.png"
        render_table([["A", "B", "C"], ["only one"]], str(out))
        assert Image.open(out).size[0] > 0

    def test_empty_table_raises(self, tmp_path):
        with pytest.raises(ValueError):
            render_table([], str(tmp_path / "t.png"))

    def test_creates_missing_parent_directories(self, tmp_path):
        out = tmp_path / "nested" / "deep" / "t.png"
        render_table([["A"], ["1"]], str(out))
        assert out.exists()


class TestAlignmentParsing:
    def test_reads_alignment_markers_from_separator(self):
        _, _, raw, _ = extract_tables(SIMPLE_TABLE)[0]
        assert parse_alignments(raw) == ["left", "center", "right"]

    def test_no_separator_yields_no_alignments(self):
        assert parse_alignments("| a | b |") == []


class TestReplaceTablesWithImages:
    def test_placeholder_comment_never_reaches_the_output(self, tmp_path):
        """TBL-01 regression.

        The old behavior emitted `<!-- TABLE 1: ... -->`, which pasted into the
        Substack composer as nothing at all and forced the author to hand-draw
        the table. That comment must never appear again.
        """
        tables = extract_tables(SIMPLE_TABLE)
        result = replace_tables_with_images(SIMPLE_TABLE, tables, str(tmp_path))

        assert "<!-- TABLE" not in result
        assert "Datawrapper import" not in result

    def test_table_becomes_an_image_figure(self, tmp_path):
        tables = extract_tables(SIMPLE_TABLE)
        result = replace_tables_with_images(SIMPLE_TABLE, tables, str(tmp_path))

        assert '<img src="table-1.png"' in result
        assert (tmp_path / "table-1.png").exists()

    def test_csv_is_still_exported_for_the_datawrapper_route(self, tmp_path):
        tables = extract_tables(SIMPLE_TABLE)
        replace_tables_with_images(SIMPLE_TABLE, tables, str(tmp_path))

        assert (tmp_path / "table-1.csv").exists()

    def test_surrounding_prose_is_preserved(self, tmp_path):
        tables = extract_tables(SIMPLE_TABLE)
        result = replace_tables_with_images(SIMPLE_TABLE, tables, str(tmp_path))

        assert "Intro paragraph." in result
        assert "Closing paragraph." in result
        assert "| Derived |" not in result

    def test_multiple_tables_are_numbered_independently(self, tmp_path):
        text = SIMPLE_TABLE + "\n" + SIMPLE_TABLE
        tables = extract_tables(text)
        result = replace_tables_with_images(text, tables, str(tmp_path))

        assert len(tables) == 2
        assert (tmp_path / "table-1.png").exists()
        assert (tmp_path / "table-2.png").exists()
        assert 'table-1.png' in result and 'table-2.png' in result

    def test_no_tables_leaves_text_untouched(self, tmp_path):
        text = "Just prose.\n"
        assert replace_tables_with_images(text, [], str(tmp_path)) == text
