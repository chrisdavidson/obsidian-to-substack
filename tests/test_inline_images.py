"""Tests for clipboard image inlining.

This is the single point of failure for the whole paste workflow: Substack
cannot resolve local file paths, so every image must become a data URI before
it reaches the clipboard. On failure `_inline_images` logs a warning and moves
on, so a broken image is silent — which is exactly how it would be mistaken for
a Substack rendering defect.
"""

from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image

from obsidian_to_substack.convert import _inline_images


def _png(path: Path, size=(6, 6)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (7, 8, 9)).save(path, "PNG")
    return path


def _srcs(html: str) -> list[str]:
    return [img.get("src", "") for img in BeautifulSoup(html, "html.parser").find_all("img")]


class TestInlineImages:
    def test_local_image_becomes_a_data_uri(self, tmp_path):
        _png(tmp_path / "a.png")
        result = _inline_images('<img src="a.png">', tmp_path)
        assert _srcs(result)[0].startswith("data:image/png;base64,")

    def test_filename_with_spaces_is_inlined(self, tmp_path):
        """The vault's hand-exported files are named `derivation-tree 1.png`.

        These sit in an unquoted-looking src attribute and are the exact images
        the morning checklist asks the author to verify.
        """
        _png(tmp_path / "derivation-tree 1.png")
        result = _inline_images('<img src="derivation-tree 1.png">', tmp_path)
        assert _srcs(result)[0].startswith("data:")

    def test_every_image_in_a_document_is_inlined(self, tmp_path):
        for name in ("a.png", "b 1.png", "c.png"):
            _png(tmp_path / name)
        html = "".join(f'<img src="{n}">' for n in ("a.png", "b 1.png", "c.png"))

        assert all(src.startswith("data:") for src in _srcs(_inline_images(html, tmp_path)))

    def test_remote_urls_are_left_alone(self, tmp_path):
        html = '<img src="https://cdn.example/x.png">'
        assert _srcs(_inline_images(html, tmp_path))[0] == "https://cdn.example/x.png"

    def test_existing_data_uri_is_not_re_encoded(self, tmp_path):
        html = '<img src="data:image/png;base64,AAAA">'
        assert _srcs(_inline_images(html, tmp_path))[0] == "data:image/png;base64,AAAA"

    def test_missing_image_is_left_unresolved_not_fatal(self, tmp_path):
        result = _inline_images('<img src="gone.png">', tmp_path)
        assert _srcs(result)[0] == "gone.png"

    def test_surrounding_markup_survives(self, tmp_path):
        _png(tmp_path / "a.png")
        result = _inline_images("<h2>Heading</h2><p>Text.</p><img src='a.png'>", tmp_path)
        assert "Heading" in result and "Text." in result

    def test_jpeg_gets_its_own_mime_type(self, tmp_path):
        path = tmp_path / "a.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (6, 6), (1, 2, 3)).save(path, "JPEG")

        assert _srcs(_inline_images('<img src="a.jpg">', tmp_path))[0].startswith(
            "data:image/jpeg;base64,"
        )
