"""Tests for title resolution (FMT-02 follow-on).

The converter correctly drops a leading sole-H1 from the pasted body
(FMT-02), but previously threw the heading text away — every article
inherited a filename-slug title. These tests pin the resolved title
reaching the head <title> element, metadata.json, the Datawrapper chart
title, and the CLI's Title line.
"""

import sys

import pytest

from obsidian_to_substack.convert import convert_article, format_result_lines, main
from obsidian_to_substack.render_html import extract_leading_title, strip_duplicate_title

TORTURE_FIXTURE = "tests/fixtures/torture_test"
TORTURE_TITLE = "Torture Test: Every Construct"


class TestStripDuplicateTitleReturnsTuple:
    def test_stripped_document_returns_body_and_heading_text(self):
        html = "<h1>The Axiom</h1><h2>Intro</h2><p>Body.</p>"
        body, heading = strip_duplicate_title(html)
        assert "<h1>" not in body
        assert heading == "The Axiom"

    def test_unstripped_document_returns_unchanged_body_and_empty_string(self):
        html = "<h1>One</h1><h1>Two</h1>"
        body, heading = strip_duplicate_title(html)
        assert body == html
        assert heading == ""


class TestExtractLeadingTitle:
    def test_sole_h1_markdown_returns_the_heading_text(self):
        assert extract_leading_title("# The Real Title\n\nBody text.") == "The Real Title"

    def test_no_qualifying_h1_returns_empty_string(self):
        assert extract_leading_title("Just a paragraph, no heading.") == ""


class TestConvertArticleResolvesTitle:
    def test_result_title_is_the_fixture_h1_text(self, tmp_path):
        result = convert_article(
            f"{TORTURE_FIXTURE}/torture-test.md", str(tmp_path)
        )
        assert result["title"] == TORTURE_TITLE

    def test_article_html_head_title_carries_the_resolved_text(self, tmp_path):
        result = convert_article(
            f"{TORTURE_FIXTURE}/torture-test.md", str(tmp_path)
        )
        html = open(result["html_path"], encoding="utf-8").read()
        assert f"<title>{TORTURE_TITLE}</title>" in html

    def test_article_html_has_no_h1_element(self, tmp_path):
        """FMT-02 is the thing this change is most forbidden to break."""
        result = convert_article(
            f"{TORTURE_FIXTURE}/torture-test.md", str(tmp_path)
        )
        html = open(result["html_path"], encoding="utf-8").read()
        assert "<h1>" not in html and "<h1 " not in html

    def test_metadata_json_contains_the_resolved_title(self, tmp_path):
        import json

        result = convert_article(
            f"{TORTURE_FIXTURE}/torture-test.md", str(tmp_path)
        )
        metadata = json.loads(open(result["metadata_path"], encoding="utf-8").read())
        assert metadata["title"] == TORTURE_TITLE


class TestCliTitleLine:
    def test_format_result_lines_includes_a_title_line(self, tmp_path):
        result = convert_article(
            f"{TORTURE_FIXTURE}/torture-test.md", str(tmp_path)
        )
        lines = format_result_lines(result)
        assert any(TORTURE_TITLE in line for line in lines)

    def test_title_line_sits_directly_below_slug_and_above_preflight(self, tmp_path):
        result = convert_article(
            f"{TORTURE_FIXTURE}/torture-test.md", str(tmp_path)
        )
        # Force a warning so we can assert the Title line still precedes it.
        result_with_warning = {**result, "warnings": ["fake"]}
        lines = format_result_lines(result_with_warning)
        slug_idx = next(i for i, l in enumerate(lines) if l.strip().endswith("/"))
        title_idx = next(i for i, l in enumerate(lines) if l.strip().startswith("Title:"))
        assert title_idx == slug_idx + 1

    def test_main_prints_title_line_via_capsys(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "obsidian-to-substack",
                TORTURE_FIXTURE,
                "--file",
                "torture-test.md",
                "--output-dir",
                str(tmp_path),
            ],
        )
        main()
        captured = capsys.readouterr()
        assert f"Title:  {TORTURE_TITLE}" in captured.out
