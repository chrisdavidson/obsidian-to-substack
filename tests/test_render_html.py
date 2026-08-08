"""Tests for HTML rendering."""

from obsidian_to_substack.render_html import (
    render_to_html,
    strip_unsupported_elements,
    wrap_html,
)


class TestRenderToHtml:
    def test_headings(self):
        text = "# H1\n\n## H2\n\n### H3"
        html = render_to_html(text)
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<h3>" in html

    def test_bold_and_italic(self):
        text = "**bold** and *italic*"
        html = render_to_html(text)
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_lists(self):
        text = "- item 1\n- item 2\n"
        html = render_to_html(text)
        assert "<li>" in html

    def test_code_block(self):
        text = "```python\nprint('hello')\n```"
        html = render_to_html(text)
        assert "<code" in html
        assert "print" in html

    def test_blockquote(self):
        text = "> This is a quote"
        html = render_to_html(text)
        assert "<blockquote>" in html

    def test_footnotes(self):
        text = "Text with note[^1].\n\n[^1]: The footnote content."
        html = render_to_html(text)
        assert "footnote" in html.lower()

    def test_smarty_em_dash(self):
        text = "word -- word"
        html = render_to_html(text)
        assert "--" not in html or "\u2014" in html


class TestWrapHtml:
    def test_produces_valid_document(self):
        body = "<p>Hello</p>"
        doc = wrap_html(body, title="Test")
        assert "<!DOCTYPE html>" in doc
        assert "<title>Test</title>" in doc
        assert "<p>Hello</p>" in doc

    def test_includes_styles(self):
        doc = wrap_html("<p>Content</p>")
        assert "font-family" in doc
        assert "max-width" in doc


class TestStripUnsupportedElements:
    def test_removes_div(self):
        html = "<p>Keep</p><div>Remove wrapper</div>"
        result = strip_unsupported_elements(html)
        assert "<div>" not in result
        assert "Keep" in result

    def test_preserves_style_tag(self):
        html = "<style>body { color: red; }</style><p>Content</p>"
        result = strip_unsupported_elements(html)
        assert "<style>" in result
        assert "Content" in result

    def test_removes_anchor_links(self):
        html = '<p><a href="#section">Jump</a> and <a href="https://example.com">Link</a></p>'
        result = strip_unsupported_elements(html)
        assert 'href="#section"' not in result
        assert "Jump" in result
        assert 'href="https://example.com"' in result

    def test_removes_underline(self):
        html = "<p><u>underlined</u> text</p>"
        result = strip_unsupported_elements(html)
        assert "<u>" not in result
        assert "underlined" in result
