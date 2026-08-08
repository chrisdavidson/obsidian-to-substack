"""Tests for frontmatter parsing."""

from obsidian_to_substack.frontmatter import parse_frontmatter


class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        text = "---\ntags:\n  - one\n  - two\nurl: https://example.com\n---\n# Body\nContent here."
        metadata, body = parse_frontmatter(text)
        assert metadata["tags"] == ["one", "two"]
        assert metadata["url"] == "https://example.com"
        assert body.startswith("# Body")

    def test_no_frontmatter(self):
        text = "# Just a heading\n\nSome content."
        metadata, body = parse_frontmatter(text)
        assert metadata == {}
        assert body == text

    def test_malformed_yaml(self):
        text = "---\n: invalid: yaml: [broken\n---\n# Body"
        metadata, body = parse_frontmatter(text)
        assert metadata == {}
        assert body == text

    def test_empty_frontmatter(self):
        text = "---\n---\n# Body"
        metadata, body = parse_frontmatter(text)
        # Empty YAML block parses to None, which is non-dict, so treated as no frontmatter
        assert metadata == {}
        assert body == text

    def test_frontmatter_with_empty_url(self):
        text = "---\ntags:\n  - test\nurl:\n---\nContent"
        metadata, body = parse_frontmatter(text)
        assert metadata["tags"] == ["test"]
        assert metadata["url"] is None
        assert body == "Content"

    def test_body_preserved_exactly(self):
        text = "---\ntitle: Test\n---\nLine 1\n\nLine 2\n"
        _, body = parse_frontmatter(text)
        assert body == "Line 1\n\nLine 2\n"
