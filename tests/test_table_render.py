"""Tests for Markdown-table-to-PNG rendering (Phase 2, TBL-01..04, GRD-01)."""

import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

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

        assert "<!-- TABLE" not in result.text
        assert "Datawrapper import" not in result.text

    def test_table_becomes_an_image_figure(self, tmp_path):
        tables = extract_tables(SIMPLE_TABLE)
        result = replace_tables_with_images(SIMPLE_TABLE, tables, str(tmp_path))

        assert '<img src="table-1.png"' in result.text
        assert (tmp_path / "table-1.png").exists()

    def test_csv_is_still_exported_on_the_image_path(self, tmp_path):
        tables = extract_tables(SIMPLE_TABLE)
        replace_tables_with_images(SIMPLE_TABLE, tables, str(tmp_path))

        assert (tmp_path / "table-1.csv").exists()

    def test_surrounding_prose_is_preserved(self, tmp_path):
        tables = extract_tables(SIMPLE_TABLE)
        result = replace_tables_with_images(SIMPLE_TABLE, tables, str(tmp_path))

        assert "Intro paragraph." in result.text
        assert "Closing paragraph." in result.text
        assert "| Derived |" not in result.text

    def test_multiple_tables_are_numbered_independently(self, tmp_path):
        text = SIMPLE_TABLE + "\n" + SIMPLE_TABLE
        tables = extract_tables(text)
        result = replace_tables_with_images(text, tables, str(tmp_path))

        assert len(tables) == 2
        assert (tmp_path / "table-1.png").exists()
        assert (tmp_path / "table-2.png").exists()
        assert 'table-1.png' in result.text and 'table-2.png' in result.text

    def test_no_tables_leaves_text_untouched(self, tmp_path):
        text = "Just prose.\n"
        assert replace_tables_with_images(text, [], str(tmp_path)).text == text

    def test_written_pngs_are_reported_back(self, tmp_path):
        """The caller cannot know what was written unless this says so.

        convert_article builds `png_files` from what it is told exists. Before
        this, the table PNGs were written and referenced by the body but named
        nowhere in the result, so a consumer collecting `png_files` assembled a
        directory whose article.html pointed at files it had not copied.
        Reconstructing `table-{n}.png` at the call site was the alternative and
        was rejected: that name is private to this module.
        """
        text = SIMPLE_TABLE + "\n" + SIMPLE_TABLE
        tables = extract_tables(text)
        result = replace_tables_with_images(text, tables, str(tmp_path))

        assert [Path(p).name for p in result.png_files] == [
            "table-1.png",
            "table-2.png",
        ]
        for png in result.png_files:
            assert Path(png).exists()

    def test_a_failed_render_is_absent_from_the_reported_pngs(
        self, tmp_path, monkeypatch
    ):
        """A render failure stays a soft degradation, and stays honest.

        The except branch writes no PNG and leaves a placeholder comment. Naming
        the unwritten file anyway would hand the consumer a path that never
        existed — worse than the omission this test's sibling fixes, because the
        consumer would fail resolving it rather than quietly under-collect.
        """
        monkeypatch.setattr(
            table_handler,
            "render_table",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("no fonts")),
        )
        tables = extract_tables(SIMPLE_TABLE)
        result = replace_tables_with_images(SIMPLE_TABLE, tables, str(tmp_path))

        assert result.png_files == []
        assert "<!-- TABLE 1: render failed" in result.text
        assert not (tmp_path / "table-1.png").exists()
        # The CSV sidecar is still written — it is the recovery path the
        # placeholder comment points the author at.
        assert (tmp_path / "table-1.csv").exists()


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


class TestFontResolution:
    """How a TrueType face is found, and what happens when none is.

    The hardcoded candidate list is Debian's layout plus one macOS path. On
    Arch the same fonts live in `/usr/share/fonts/liberation/` rather than
    `/usr/share/fonts/truetype/liberation/`, so every path missed, every
    variant fell to `ImageFont.load_default()`, and tables rendered in a
    bitmap face on a machine with 798 fonts installed. Nothing here covered
    FontSet at all, which is how that survived.

    Every test mocks the font environment rather than reading the host's.
    These assertions must mean the same thing on the author's machine, on
    Debian, and in a container with no fonts at all -- the display-server
    leak in tests/conftest.py was the same class of mistake.
    """

    def _fc_output(self, family: str, file: str, fmt: str = "TrueType") -> str:
        return f"{family}\n{file}\n{fmt}"

    def test_a_hardcoded_path_is_used_without_consulting_fontconfig(self):
        # The fast path. Where the existing layout already resolves, nothing
        # changes and no subprocess is spawned.
        from obsidian_to_substack.table_render import FontSet

        with (
            patch("obsidian_to_substack.table_render.Path.exists", return_value=True),
            patch("obsidian_to_substack.table_render.ImageFont.truetype") as truetype,
            patch("obsidian_to_substack.table_render._fc_match") as fc_match,
        ):
            FontSet()

        assert truetype.called
        assert not fc_match.called

    def test_fontconfig_resolves_when_no_hardcoded_path_exists(self):
        # The Arch case that started this: the paths are all wrong, but the
        # font is right there and fontconfig knows where.
        from obsidian_to_substack.table_render import FontSet

        with (
            patch("obsidian_to_substack.table_render.Path.exists", return_value=False),
            patch("shutil.which", return_value="/usr/bin/fc-match"),
            patch("subprocess.run") as run,
            patch("obsidian_to_substack.table_render.ImageFont.truetype") as truetype,
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = self._fc_output(
                "Liberation Sans", "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"
            )
            FontSet()

        assert truetype.called
        loaded = {call.args[0] for call in truetype.call_args_list}
        assert loaded == {"/usr/share/fonts/liberation/LiberationSans-Regular.ttf"}

    def test_each_style_asks_fontconfig_for_that_style(self):
        # A bold cell must not silently render regular. The style bits are
        # the whole reason for querying per variant instead of once.
        from obsidian_to_substack.table_render import FontSet

        with (
            patch("obsidian_to_substack.table_render.Path.exists", return_value=False),
            patch("shutil.which", return_value="/usr/bin/fc-match"),
            patch("subprocess.run") as run,
            patch("obsidian_to_substack.table_render.ImageFont.truetype"),
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = self._fc_output("Liberation Sans", "/f.ttf")
            FontSet()

        patterns = " ".join(
            str(call.args[0]) for call in run.call_args_list
        )
        assert ":bold:italic" in patterns
        assert ":bold" in patterns
        assert ":italic" in patterns

    def test_a_substituted_family_is_not_mistaken_for_the_named_one(self):
        # fc-match always answers. Asked for a family nobody has installed it
        # returns its best guess rather than nothing, so the reply has to be
        # checked against the request -- otherwise the first name in the
        # preference list always appears to win and the ordering is a lie.
        from obsidian_to_substack.table_render import _fc_match

        with (
            patch("shutil.which", return_value="/usr/bin/fc-match"),
            patch("subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = self._fc_output("Liberation Sans", "/lib.ttf")

            assert _fc_match("DejaVu Sans", require_family="DejaVu Sans") is None
            assert _fc_match("Liberation Sans", require_family="Liberation Sans") == "/lib.ttf"
            # The generic query takes whatever fontconfig considers best.
            assert _fc_match("sans-serif") == "/lib.ttf"

    def test_a_non_truetype_match_is_refused(self):
        # Pillow's truetype() cannot open a bitmap or Type1 face. Handing it
        # one raises where returning None would have fallen through cleanly.
        from obsidian_to_substack.table_render import _fc_match

        with (
            patch("shutil.which", return_value="/usr/bin/fc-match"),
            patch("subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = self._fc_output("Fixed", "/f.pcf", fmt="PCF")

            assert _fc_match("sans-serif") is None

    def test_missing_fontconfig_is_not_an_error(self):
        from obsidian_to_substack.table_render import _fc_match

        with patch("shutil.which", return_value=None), patch("subprocess.run") as run:
            assert _fc_match("sans-serif") is None
            assert not run.called

    @pytest.mark.parametrize(
        "failure",
        [
            OSError("boom"),
            subprocess.TimeoutExpired(cmd="fc-match", timeout=5),
            subprocess.CalledProcessError(1, "fc-match"),
        ],
    )
    def test_a_broken_fontconfig_is_not_fatal(self, failure):
        # Rendering a table without the nicest font is a degraded article.
        # Crashing the conversion over it is a lost one.
        from obsidian_to_substack.table_render import _fc_match

        with (
            patch("shutil.which", return_value="/usr/bin/fc-match"),
            patch("subprocess.run", side_effect=failure),
        ):
            assert _fc_match("sans-serif") is None

    def test_the_bitmap_fallback_still_warns_when_nothing_resolves(self, caplog):
        # The last resort has to stay loud: this is the state that silently
        # degraded every published table.
        from obsidian_to_substack.table_render import FontSet

        with (
            patch("obsidian_to_substack.table_render.Path.exists", return_value=False),
            patch("shutil.which", return_value=None),
            caplog.at_level(logging.WARNING),
        ):
            FontSet()

        assert "No TrueType font" in caplog.text

    def test_a_resolved_font_is_reported_once_not_per_variant(self, caplog):
        # Four variants resolve per FontSet. Logging each one turns a normal
        # run into four lines of noise in a tool whose output the author
        # actually reads.
        from obsidian_to_substack.table_render import FontSet

        with (
            patch("obsidian_to_substack.table_render.Path.exists", return_value=False),
            patch("shutil.which", return_value="/usr/bin/fc-match"),
            patch("subprocess.run") as run,
            patch("obsidian_to_substack.table_render.ImageFont.truetype"),
            caplog.at_level(logging.WARNING),
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = self._fc_output("Liberation Sans", "/f.ttf")
            FontSet()

        assert caplog.text == ""

    def test_the_torture_fixture_still_carries_a_glyph_the_fallback_lacks(self):
        """Guard the guard: keep a character the bitmap default cannot draw.

        The font fallback was found because a published table rendered
        `Off\u2011the\u2011shelf` as `Off\u2591the\u2591shelf` -- Pillow's
        `load_default()` has no glyph for U+2011 and drew replacement boxes.
        That is what made this a fidelity defect and not a cosmetic one:
        characters the author wrote did not reach the reader.

        The fixture carries one so the construct stays represented end to end.
        If it ever goes pure ASCII, every test above still passes while proving
        nothing about the case that actually reached a live post -- the same
        trap `test_a_real_article_carries_non_ascii` was written for.
        """
        fixture = (
            Path(__file__).parent / "fixtures" / "torture_test" / "torture-test.md"
        )
        table_lines = [
            line
            for line in fixture.read_text(encoding="utf-8").splitlines()
            if line.startswith("|")
        ]

        assert any("\u2011" in line for line in table_lines)
