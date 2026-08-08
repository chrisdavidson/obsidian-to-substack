"""Integration tests for the full conversion pipeline."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from obsidian_to_substack.convert import (
    _inline_images,
    convert_article,
    convert_directory,
    copy_html_to_clipboard,
    slugify,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSlugify:
    def test_basic(self):
        assert slugify("My Article Title.md") == "my-article-title"

    def test_special_chars(self):
        assert slugify("What's the Deal?.md") == "whats-the-deal"

    def test_multiple_spaces(self):
        assert slugify("Too   Many   Spaces.md") == "too-many-spaces"

    def test_already_slugged(self):
        assert slugify("already-a-slug.md") == "already-a-slug"


class TestConvertArticle:
    def test_full_pipeline(self):
        article = str(FIXTURES_DIR / "sample_article.md")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_article(
                article, tmpdir, svg_dir=str(FIXTURES_DIR)
            )
            assert "slug" in result
            assert Path(result["html_path"]).exists()
            assert Path(result["metadata_path"]).exists()

            html = Path(result["html_path"]).read_text()
            assert "<!DOCTYPE html>" in html
            assert "![[" not in html
            assert "[[" not in html

            # The fixture's sole `# Sample Article Title` H1 is the article
            # title. Substack renders its own title above the body, so it must
            # survive in <title> but not as a duplicate heading in the body.
            assert "<title>" in html
            assert "<h1>Sample Article Title</h1>" not in html

            metadata = json.loads(Path(result["metadata_path"]).read_text())
            assert "tags" in metadata

    def test_png_files_generated(self):
        article = str(FIXTURES_DIR / "sample_article.md")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_article(
                article, tmpdir, svg_dir=str(FIXTURES_DIR)
            )
            assert len(result["png_files"]) >= 1
            for png in result["png_files"]:
                assert Path(png).exists()

    def test_table_csv_generated(self):
        article = str(FIXTURES_DIR / "sample_article.md")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_article(
                article, tmpdir, svg_dir=str(FIXTURES_DIR)
            )
            assert result["table_count"] == 1
            csv_files = list(Path(result["output_dir"]).glob("*.csv"))
            assert len(csv_files) == 1

    def test_missing_article_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                convert_article("/nonexistent/article.md", tmpdir)

    def test_dry_run(self):
        article = str(FIXTURES_DIR / "sample_article.md")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_article(
                article, tmpdir, svg_dir=str(FIXTURES_DIR), dry_run=True
            )
            assert result["dry_run"] is True
            assert not list(Path(tmpdir).rglob("*.html"))


class TestConvertDirectory:
    def test_processes_md_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = convert_directory(
                str(FIXTURES_DIR), tmpdir, svg_dir=str(FIXTURES_DIR)
            )
            md_files = list(FIXTURES_DIR.glob("*.md"))
            assert len(results) == len(md_files)

    def test_invalid_directory_raises(self):
        with pytest.raises(NotADirectoryError):
            convert_directory("/nonexistent/dir", "/tmp/out")


class TestInlineImages:
    def test_replaces_local_src_with_data_uri(self, tmp_path):
        # Create a tiny 1x1 red PNG
        from PIL import Image

        img = Image.new("RGB", (1, 1), color="red")
        img.save(tmp_path / "chart.png")

        html = '<html><body><img src="chart.png" alt="chart"></body></html>'
        result = _inline_images(html, tmp_path)

        assert 'src="data:image/png;base64,' in result
        assert 'src="chart.png"' not in result

    def test_skips_http_urls(self, tmp_path):
        html = '<img src="https://example.com/img.png">'
        result = _inline_images(html, tmp_path)
        assert 'src="https://example.com/img.png"' in result

    def test_skips_data_uris(self, tmp_path):
        html = '<img src="data:image/png;base64,abc">'
        result = _inline_images(html, tmp_path)
        assert 'src="data:image/png;base64,abc"' in result

    def test_missing_image_left_unchanged(self, tmp_path):
        html = '<img src="missing.png">'
        result = _inline_images(html, tmp_path)
        assert 'src="missing.png"' in result

    def test_multiple_images_inlined(self, tmp_path):
        from PIL import Image

        for name in ("a.png", "b.png"):
            img = Image.new("RGB", (1, 1), color="blue")
            img.save(tmp_path / name)

        html = '<img src="a.png"><img src="b.png">'
        result = _inline_images(html, tmp_path)

        assert result.count("data:image/png;base64,") == 2


class TestCopyHtmlToClipboard:
    def test_xclip_not_installed(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(SystemExit):
                copy_html_to_clipboard("/tmp/fake.html")

    def test_calls_xclip_with_html_mime_type(self, tmp_path):
        html_file = tmp_path / "article.html"
        html_file.write_text("<p>Hello</p>", encoding="utf-8")

        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as mock_run,
        ):
            copy_html_to_clipboard(str(html_file))
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == ["xclip", "-selection", "clipboard", "-t", "text/html"]
            assert call_args[1]["check"] is True

    def test_inlines_images_before_copy(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (1, 1), color="green")
        img.save(tmp_path / "photo.png")

        html_file = tmp_path / "article.html"
        html_file.write_text(
            '<html><body><img src="photo.png"></body></html>',
            encoding="utf-8",
        )

        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as mock_run,
        ):
            copy_html_to_clipboard(str(html_file))
            copied_html = mock_run.call_args[1]["input"].decode("utf-8")
            assert "data:image/png;base64," in copied_html
            assert 'src="photo.png"' not in copied_html
