"""Tests for Markdown-table-to-PNG rendering (Phase 2, TBL-01..04, GRD-01)."""

import sys
from pathlib import Path

import pytest
from PIL import Image

from obsidian_to_substack import table_handler
from obsidian_to_substack.convert import convert_article, main
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


class TestInlineHtmlSpans:
    """`table_handler._parse_row` converts markers to HTML before rendering.

    Without HTML awareness the renderer drew the literal text
    `<strong>Bold cell</strong>` into the image.
    """

    def test_strong_tag_becomes_a_bold_span(self):
        spans = parse_spans("<strong>Bold cell</strong>")
        assert spans == [Span("Bold cell", bold=True)]

    def test_em_tag_becomes_an_italic_span(self):
        assert parse_spans("<em>quiet</em>") == [Span("quiet", italic=True)]

    def test_b_and_i_tags_are_honored(self):
        assert parse_spans("<b>x</b>")[0].bold
        assert parse_spans("<i>y</i>")[0].italic

    def test_nested_tags_combine(self):
        spans = parse_spans("<strong><em>both</em></strong>")
        assert spans[0].bold and spans[0].italic

    def test_html_and_plain_text_mix(self):
        spans = parse_spans("before <strong>bold</strong> after")
        assert [s.text.strip() for s in spans] == ["before", "bold", "after"]
        assert [s.bold for s in spans] == [False, True, False]

    def test_no_html_tag_text_survives_into_the_image(self):
        rendered = "".join(s.text for s in parse_spans("<strong>Bold</strong>"))
        assert "<" not in rendered and ">" not in rendered

    def test_backticks_are_stripped(self):
        """The renderer has no monospace variant; a literal backtick reads as a typo."""
        assert parse_spans("`code`") == [Span("code")]

    def test_backticks_inside_a_styled_run_are_stripped(self):
        spans = parse_spans("<strong>`code`</strong>")
        assert spans[0].text == "code" and spans[0].bold


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

    def test_csv_is_still_exported_on_the_image_path(self, tmp_path):
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


class TestDatawrapperRemovalGuards:
    """Pins the retirement of the --datawrapper flag and its code path.

    Guard A is end-to-end and should already pass against the pre-removal
    code (a well-formed fixture table renders fine on the local path) — that
    confirms the guard measures the removal, not the fixture. Guards B and C
    are structural and start red until the deletions land.
    """

    def test_convert_article_writes_no_placeholder_comment_and_still_renders_table(
        self, tmp_path
    ):
        source = tmp_path / "article.md"
        source.write_text(
            "| A | B |\n| --- | --- |\n| 1 | 2 |\n\nSome prose.\n",
            encoding="utf-8",
        )
        result = convert_article(str(source), str(tmp_path / "out"))

        html = Path(result["html_path"]).read_text(encoding="utf-8")
        assert "<!-- TABLE" not in html

        out_dir = Path(result["output_dir"])
        assert (out_dir / "table-1.png").exists()
        assert (out_dir / "table-1.csv").exists()

    def test_datawrapper_module_is_gone(self):
        with pytest.raises(ModuleNotFoundError):
            import obsidian_to_substack.datawrapper  # noqa: F401

    def test_removed_functions_are_gone_from_table_handler(self):
        assert not hasattr(table_handler, "replace_tables_with_embeds")
        assert not hasattr(table_handler, "replace_tables_with_placeholders")

    def test_cli_rejects_retired_datawrapper_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            ["obsidian-to-substack", str(tmp_path), "--datawrapper", "--dry-run"],
        )
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
