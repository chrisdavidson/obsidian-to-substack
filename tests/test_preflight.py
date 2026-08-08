"""Tests for preflight warnings (GRD-02).

Each check corresponds to a defect recovered in docs/FINDINGS.md. A defect
found once should never again be rediscovered by pasting and squinting.
"""

from PIL import Image

from obsidian_to_substack.preflight import MAX_IMAGE_WIDTH, check, report
from obsidian_to_substack.render_html import (
    render_to_html,
    strip_unsupported_elements,
    wrap_html,
)


def _png(path, size=(10, 10)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (9, 9, 9)).save(path, "PNG")
    return path


class TestPlaceholderCheck:
    def test_warns_on_leaked_table_placeholder(self, tmp_path):
        html = "<body><!-- TABLE 1: See table-1.csv --><p>x</p></body>"
        warnings = check(html, tmp_path)
        assert any(w.check == "table_placeholder" for w in warnings)

    def test_placeholder_warning_cites_tbl_01(self, tmp_path):
        html = "<body><!-- TABLE 1: x --></body>"
        placeholder = [w for w in check(html, tmp_path) if w.check == "table_placeholder"]
        assert placeholder[0].requirement == "TBL-01"

    def test_unrelated_comment_does_not_warn(self, tmp_path):
        html = "<body><!-- just a note --><p>x</p></body>"
        assert not any(w.check == "table_placeholder" for w in check(html, tmp_path))


class TestDuplicateTitleCheck:
    def test_warns_on_lone_leading_h1(self, tmp_path):
        html = "<body><h1>The Title</h1><h2>S</h2></body>"
        assert any(w.check == "duplicate_title" for w in check(html, tmp_path))

    def test_no_warning_when_h1_used_for_sections(self, tmp_path):
        html = "<body><h1>One</h1><p>a</p><h1>Two</h1></body>"
        assert not any(w.check == "duplicate_title" for w in check(html, tmp_path))

    def test_no_warning_when_body_starts_with_h2(self, tmp_path):
        html = "<body><h2>Intro</h2><p>a</p></body>"
        assert not any(w.check == "duplicate_title" for w in check(html, tmp_path))


class TestImageChecks:
    def test_warns_on_missing_image(self, tmp_path):
        html = '<body><img src="gone.png"></body>'
        assert any(w.check == "missing_image" for w in check(html, tmp_path))

    def test_present_image_does_not_warn(self, tmp_path):
        _png(tmp_path / "there.png")
        html = '<body><img src="there.png"></body>'
        assert not any(w.check == "missing_image" for w in check(html, tmp_path))

    def test_remote_and_data_urls_are_skipped(self, tmp_path):
        html = (
            '<body><img src="https://cdn/x.png">'
            '<img src="data:image/png;base64,AAAA"></body>'
        )
        assert check(html, tmp_path) == []

    def test_warns_on_image_wider_than_substacks_column(self, tmp_path):
        _png(tmp_path / "wide.png", size=(MAX_IMAGE_WIDTH + 200, 40))
        html = '<body><img src="wide.png"></body>'
        assert any(w.check == "image_too_wide" for w in check(html, tmp_path))

    def test_normal_width_image_does_not_warn(self, tmp_path):
        _png(tmp_path / "ok.png", size=(1200, 40))
        html = '<body><img src="ok.png"></body>'
        assert not any(w.check == "image_too_wide" for w in check(html, tmp_path))

    def test_warns_on_unreadable_image(self, tmp_path):
        broken = tmp_path / "broken.png"
        broken.write_bytes(b"not a png")
        html = '<body><img src="broken.png"></body>'
        assert any(w.check == "unreadable_image" for w in check(html, tmp_path))


class TestFootnoteChecks:
    """GRD-02 checks for both footnote failure modes found in the v1.0 audit.

    F1: the literal `[^1]` marker surviving into rendered text (hyphen-form
    definitions that never matched). F2: reference markup surviving with no
    footnotes section beneath it (the section deleted downstream by the div
    strip). The "correct output warns on neither" case is built from the
    real render -> strip chain, not a hand-written snippet — a hand-written
    snippet could accidentally omit the exact shape the real pipeline
    produces and pass for the wrong reason.
    """

    def _real_footnote_html(self):
        rendered = render_to_html(
            "Text with note[^1].\n\n[^1]: The footnote content."
        )
        return strip_unsupported_elements(rendered)

    def test_warns_on_literal_footnote_marker(self, tmp_path):
        html = "<body><p>Text with note[^1].</p></body>"
        assert any(
            w.check == "footnote_marker_literal" for w in check(html, tmp_path)
        )

    def test_literal_marker_warning_cites_grd_02(self, tmp_path):
        html = "<body><p>Text with note[^1].</p></body>"
        warnings = [
            w for w in check(html, tmp_path) if w.check == "footnote_marker_literal"
        ]
        assert warnings[0].requirement == "GRD-02"

    def test_warns_when_reference_markup_has_no_footnotes_section(self, tmp_path):
        # The F2 shape: fnref survives, the fn: section is gone.
        html = '<body><p>Text with note<sup id="fnref:1">1</sup>.</p></body>'
        assert any(
            w.check == "footnote_section_missing" for w in check(html, tmp_path)
        )

    def test_section_missing_warning_cites_grd_02(self, tmp_path):
        html = '<body><p>Text with note<sup id="fnref:1">1</sup>.</p></body>'
        warnings = [
            w for w in check(html, tmp_path) if w.check == "footnote_section_missing"
        ]
        assert warnings[0].requirement == "GRD-02"

    def test_correctly_converted_footnote_produces_no_warning(self, tmp_path):
        html = self._real_footnote_html()
        warnings = [w for w in check(html, tmp_path) if w.check.startswith("footnote_")]
        assert warnings == []

    def test_no_footnotes_at_all_produces_no_warning(self, tmp_path):
        html = "<body><p>Nothing footnote-shaped here.</p></body>"
        warnings = [w for w in check(html, tmp_path) if w.check.startswith("footnote_")]
        assert warnings == []

    def test_footnote_shaped_literal_inside_code_does_not_warn(self, tmp_path):
        html = "<body><pre><code>[^1] - example syntax</code></pre></body>"
        warnings = [w for w in check(html, tmp_path) if w.check.startswith("footnote_")]
        assert warnings == []


class TestSlugTitleCheck:
    """The title fell back to the filename AND the filename is a slug (GRD-02).

    The fallback alone is not a defect: 20 of the 25 published articles take
    their title from the filename and read correctly, because their filenames
    are written as titles. Only the lowercase-slug case is a defect, so every
    no-warn case below is load-bearing.
    """

    def test_warns_on_lowercase_slug_title(self, tmp_path):
        html = "<html><head><title>article with no title</title></head></html>"
        warnings = check(html, tmp_path, title_from_slug=True)
        assert any(w.check == "slug_title" for w in warnings)

    def test_slug_title_warning_cites_grd_02(self, tmp_path):
        html = "<html><head><title>several h1 headings</title></head></html>"
        slug = [w for w in check(html, tmp_path, title_from_slug=True) if w.check == "slug_title"]
        assert slug[0].requirement == "GRD-02"

    def test_warning_names_the_resolved_title(self, tmp_path):
        html = "<html><head><title>all lowercase filename</title></head></html>"
        slug = [w for w in check(html, tmp_path, title_from_slug=True) if w.check == "slug_title"]
        assert "all lowercase filename" in slug[0].message

    def test_warning_does_not_prescribe_adding_an_h1(self, tmp_path):
        # The fallback also fires when a leading H1 exists but is not the
        # document's only one -- 19 of the 25 published articles. Telling the
        # author to "add an H1" would be wrong for them.
        html = "<html><head><title>no capitals here?</title></head></html>"
        slug = [w for w in check(html, tmp_path, title_from_slug=True) if w.check == "slug_title"]
        assert "add an h1" not in slug[0].message.lower()

    def test_filename_that_reads_as_a_title_does_not_warn(self, tmp_path):
        html = "<html><head><title>A Filename That Reads As A Title</title></head></html>"
        warnings = check(html, tmp_path, title_from_slug=True)
        assert not any(w.check == "slug_title" for w in warnings)

    def test_single_capital_is_enough_to_stay_silent(self, tmp_path):
        html = "<html><head><title>A Capitalised Filename</title></head></html>"
        warnings = check(html, tmp_path, title_from_slug=True)
        assert not any(w.check == "slug_title" for w in warnings)

    def test_authored_title_never_warns_however_it_looks(self, tmp_path):
        # Fallback did not fire: the author set this lowercase title deliberately.
        html = "<html><head><title>article with no title</title></head></html>"
        warnings = check(html, tmp_path, title_from_slug=False)
        assert not any(w.check == "slug_title" for w in warnings)

    def test_two_positional_args_still_work_and_never_warn(self, tmp_path):
        html = "<html><head><title>article with no title</title></head></html>"
        warnings = check(html, tmp_path)
        assert not any(w.check == "slug_title" for w in warnings)

    def test_missing_title_element_does_not_crash(self, tmp_path):
        warnings = check("<body><p>x</p></body>", tmp_path, title_from_slug=True)
        assert not any(w.check == "slug_title" for w in warnings)


class TestReport:
    def test_clean_output_produces_no_report(self, tmp_path):
        assert report(check("<body><p>fine</p></body>", tmp_path)) == ""

    def test_report_lists_every_warning(self, tmp_path):
        html = '<body><!-- TABLE 1: x --><h1>T</h1><img src="gone.png"></body>'
        warnings = check(html, tmp_path)
        text = report(warnings)

        assert str(len(warnings)) in text
        for warning in warnings:
            assert warning.requirement in text
