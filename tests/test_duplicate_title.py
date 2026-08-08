"""Tests for duplicate-title suppression (FMT-02, GRD-01).

Evidence: docs/FINDINGS.md pattern `duplicate_title_h1`, present in 5 of 17
published articles. The "sole H1" rule below classifies all 17 correctly.
"""

from obsidian_to_substack.render_html import strip_duplicate_title


class TestSoleH1IsATitle:
    def test_sole_leading_h1_is_removed(self):
        html = "<h1>The Axiom</h1><h2>Intro</h2><p>Body.</p>"
        result = strip_duplicate_title(html)
        assert "<h1>" not in result
        assert "<h2>Intro</h2>" in result

    def test_removal_works_without_a_title_argument(self):
        """Obsidian sources carry no frontmatter title, so this is the real path."""
        html = "<h1>Whatever The Title Is</h1><h2>S</h2><p>B.</p>"
        assert "<h1>" not in strip_duplicate_title(html)

    def test_reworded_title_is_still_caught(self):
        """The author lengthened this title when publishing to Substack.

        Exact title matching missed it; the sole-H1 rule catches it.
        """
        html = "<h1>The Knowledge Base Is Already Written</h1><h2>Intro</h2>"
        result = strip_duplicate_title(
            html, "The Knowledge Base Is Already Written: Using Domain Articles"
        )
        assert "<h1>" not in result


class TestMultipleH1sAreSectionHeadings:
    def test_leading_h1_is_kept_when_the_document_uses_h1_for_sections(self):
        """`# Introduction` opening an article that uses `#` throughout.

        Stripping here would delete a real section heading.
        """
        html = "<h1>Introduction</h1><p>a</p><h1>The Problem</h1><p>b</p>"
        assert strip_duplicate_title(html) == html

    def test_many_h1s_are_all_preserved(self):
        html = "<h1>One</h1><h1>Two</h1><h1>Three</h1>"
        result = strip_duplicate_title(html)
        assert result.count("<h1>") == 3


class TestExplicitTitleMatch:
    def test_matching_title_strips_even_with_multiple_h1s(self):
        html = "<h1>The Axiom</h1><p>a</p><h1>Later Section</h1>"
        result = strip_duplicate_title(html, "The Axiom")
        assert "The Axiom" not in result
        assert "Later Section" in result

    def test_match_ignores_case_and_punctuation(self):
        html = "<h1>The Axiom: Why It Is Load-Bearing</h1><p>a</p><h1>Other</h1>"
        result = strip_duplicate_title(html, "the axiom why it is load bearing")
        assert "Load-Bearing" not in result


class TestSafety:
    def test_leading_h2_is_never_stripped(self):
        html = "<h2>The Axiom</h2><p>Body.</p>"
        assert strip_duplicate_title(html, "The Axiom") == html

    def test_h1_later_in_the_document_is_kept(self):
        html = "<h2>Opening</h2><p>Body.</p><h1>The Axiom</h1>"
        assert strip_duplicate_title(html, "The Axiom") == html

    def test_document_without_headings_is_untouched(self):
        html = "<p>Body only.</p>"
        assert strip_duplicate_title(html, "Some Title") == html

    def test_body_content_survives_removal(self):
        html = "<h1>T</h1><p>first</p><p>second</p>"
        result = strip_duplicate_title(html)
        assert "first" in result and "second" in result
