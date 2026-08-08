"""Tests for the evidence-recovery diff tool (Phase 1)."""

from tools.substack_diff import report
from tools.substack_diff.diagnose import detect
from tools.substack_diff.structure import extract

PIPELINE_HTML = """
<!DOCTYPE html>
<html><head><title>t</title></head><body>
<h1>The Axiom: Why It Is Load-Bearing</h1>
<p>Opening paragraph.</p>
<h2>A Section</h2>
<ul><li><p>first item</p></li><li><p>second item</p></li></ul>
<!-- TABLE 1: See table-1.csv for Datawrapper import -->
<figure><img src="diagram.png"/></figure>
</body></html>
"""

PUBLISHED_HTML = """
<html><body><div class="available-content">
<p>Opening paragraph.</p>
<h2>A Section</h2>
<ul><li><p>first item</p></li><li><p>second item</p></li></ul>
<figure><picture><img src="https://substackcdn.com/diagram.png"/></picture></figure>
<div class="subscription-widget-wrap">
  <p>Thanks for reading! Subscribe for free to receive new posts.</p>
</div>
</div></body></html>
"""


class TestStructureExtraction:
    def test_list_item_paragraphs_are_not_counted_as_paragraphs(self):
        """Substack wraps every <li> body in a <p>; those are not paragraphs.

        Without this, a typical article reports ~30 phantom paragraph
        differences and the whole report becomes noise.
        """
        pipeline = extract(PIPELINE_HTML)
        published = extract(PUBLISHED_HTML, is_published=True)

        assert len(pipeline.paragraphs) == 1
        assert len(published.paragraphs) == 1

    def test_list_structure_is_counted_once(self):
        structure = extract(PIPELINE_HTML)
        assert structure.lists == 1
        assert structure.list_items == 2

    def test_substack_chrome_is_excluded(self):
        published = extract(PUBLISHED_HTML, is_published=True)
        joined = " ".join(published.paragraphs)
        assert "Subscribe for free" not in joined

    def test_html_comments_are_captured(self):
        structure = extract(PIPELINE_HTML)
        assert any("TABLE 1" in comment for comment in structure.comments)

    def test_published_extraction_is_scoped_to_article_body(self):
        published = extract(PUBLISHED_HTML, is_published=True)
        assert len(published.images) == 1

    def test_image_only_paragraph_is_not_a_paragraph(self):
        html = '<body><p><img src="x.png"/></p></body>'
        assert extract(html).paragraphs == []


class TestDiagnose:
    def test_detects_duplicate_title_h1(self):
        pipeline = extract(PIPELINE_HTML)
        published = extract(PUBLISHED_HTML, is_published=True)

        patterns = detect(pipeline, published, "The Axiom: Why It Is Load-Bearing")
        assert any(p.key == "duplicate_title_h1" for p in patterns)

    def test_duplicate_title_detection_ignores_punctuation_and_case(self):
        pipeline = extract(PIPELINE_HTML)
        published = extract(PUBLISHED_HTML, is_published=True)

        patterns = detect(pipeline, published, "the axiom - why it is load bearing!")
        assert any(p.key == "duplicate_title_h1" for p in patterns)

    def test_no_duplicate_title_when_h1_differs_from_post_title(self):
        pipeline = extract(PIPELINE_HTML)
        published = extract(PUBLISHED_HTML, is_published=True)

        patterns = detect(pipeline, published, "A Completely Different Title")
        assert not any(p.key == "duplicate_title_h1" for p in patterns)

    def test_detects_leaked_table_placeholder(self):
        pipeline = extract(PIPELINE_HTML)
        published = extract(PUBLISHED_HTML, is_published=True)

        patterns = detect(pipeline, published, "irrelevant")
        leaked = [p for p in patterns if p.key == "table_placeholder_leaked"]
        assert len(leaked) == 1
        assert leaked[0].requirement == "TBL-01"

    def test_detects_hand_added_images(self):
        pipeline = extract('<body><img src="a.png"/></body>')
        published = extract(
            '<body><div class="available-content">'
            '<img src="a.png"/><img src="b.png"/></div></body>',
            is_published=True,
        )

        patterns = detect(pipeline, published, "t")
        assert any(p.key == "images_hand_added" for p in patterns)

    def test_detects_lost_images(self):
        pipeline = extract('<body><img src="a.png"/><img src="b.png"/></body>')
        published = extract(
            '<body><div class="available-content"><img src="a.png"/></div></body>',
            is_published=True,
        )

        patterns = detect(pipeline, published, "t")
        assert any(p.key == "images_lost" for p in patterns)

    def test_clean_article_produces_no_patterns(self):
        clean = "<body><h2>Section</h2><p>Text.</p></body>"
        published = (
            '<body><div class="available-content">'
            "<h2>Section</h2><p>Text.</p></div></body>"
        )
        patterns = detect(extract(clean), extract(published, is_published=True), "Title")
        assert patterns == []


class TestHandRecordedFindings:
    """report.render splices hand-authored findings into the generated doc.

    docs/FINDINGS.md is machine-generated (overwritten wholesale by
    `python -m tools.substack_diff --all`), so a hand-written entry needs a
    render() parameter rather than a direct edit to survive regeneration.
    """

    def test_hand_recorded_text_appears_in_the_rendered_document(self):
        rendered = report.render(
            [],
            [],
            {},
            "2026-01-01 00:00",
            hand_recorded="### A Hand-recorded Entry\n\nSome detail text.",
        )
        assert "## Hand-recorded findings" in rendered
        assert "### A Hand-recorded Entry" in rendered
        assert "Some detail text." in rendered

    def test_section_is_omitted_when_hand_recorded_text_is_empty(self):
        rendered = report.render([], [], {}, "2026-01-01 00:00", hand_recorded="")
        assert "## Hand-recorded findings" not in rendered
