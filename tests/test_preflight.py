"""Tests for preflight warnings (GRD-02).

Each check corresponds to a defect recovered in docs/FINDINGS.md. A defect
found once should never again be rediscovered by pasting and squinting.
"""

from PIL import Image

from obsidian_to_substack.preflight import MAX_IMAGE_WIDTH, check, report


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
