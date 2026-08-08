"""Tests for raster embed collection (DIAG-02, GRD-01).

Evidence: the vault mixes two embed styles. Some articles embed
`![[name.svg]]` and let the pipeline rasterize; others embed a pre-made
`![[name 1.png]]`, which nothing copied into the output directory, so the
`<img src>` pointed at a missing file and pasted broken.
"""

from pathlib import Path

from obsidian_to_substack.image_assets import (
    copy_raster_embeds,
    find_image,
    referenced_images,
)


def _make_png(path: Path) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), (1, 2, 3)).save(path, "PNG")
    return path


class TestReferencedImages:
    def test_finds_a_plain_png_embed(self):
        assert referenced_images("![[diagram.png]]") == ["diagram.png"]

    def test_finds_an_embed_with_a_modifier(self):
        assert referenced_images("![[diagram 1.png| center]]") == ["diagram 1.png"]

    def test_ignores_svg_embeds(self):
        """SVGs are handled by export_all_svgs, not copied verbatim."""
        assert referenced_images("![[diagram.svg]]") == []

    def test_ignores_internal_links(self):
        assert referenced_images("[[Some Note]]") == []

    def test_deduplicates_repeated_embeds(self):
        assert referenced_images("![[a.png]] text ![[a.png]]") == ["a.png"]

    def test_accepts_common_raster_suffixes(self):
        text = "![[a.png]] ![[b.jpg]] ![[c.jpeg]] ![[d.gif]] ![[e.webp]]"
        assert len(referenced_images(text)) == 5

    def test_suffix_match_is_case_insensitive(self):
        assert referenced_images("![[Diagram.PNG]]") == ["Diagram.PNG"]


class TestFindImage:
    def test_finds_in_the_first_search_directory(self, tmp_path):
        _make_png(tmp_path / "a.png")
        assert find_image("a.png", [tmp_path]) == tmp_path / "a.png"

    def test_falls_back_to_a_nested_directory(self, tmp_path):
        """Obsidian resolves embeds vault-wide by basename."""
        _make_png(tmp_path / "svg" / "a.png")
        assert find_image("a.png", [tmp_path]) is not None

    def test_missing_image_returns_none(self, tmp_path):
        assert find_image("nope.png", [tmp_path]) is None


class TestCopyRasterEmbeds:
    def test_copies_embedded_image_into_the_output_directory(self, tmp_path):
        source = tmp_path / "src"
        out = tmp_path / "out"
        _make_png(source / "diagram.png")

        copied = copy_raster_embeds("![[diagram.png]]", [source], str(out))

        assert (out / "diagram.png").is_file()
        assert copied["diagram.png"] == str(out / "diagram.png")

    def test_handles_spaces_in_filenames(self, tmp_path):
        """The vault's hand-exported files are named like `derivation-tree 1.png`."""
        source = tmp_path / "src"
        out = tmp_path / "out"
        _make_png(source / "derivation-tree 1.png")

        copy_raster_embeds("![[derivation-tree 1.png| center]]", [source], str(out))

        assert (out / "derivation-tree 1.png").is_file()

    def test_missing_image_is_skipped_not_fatal(self, tmp_path):
        out = tmp_path / "out"
        copied = copy_raster_embeds("![[gone.png]]", [tmp_path], str(out))
        assert copied == {}

    def test_no_embeds_copies_nothing(self, tmp_path):
        assert copy_raster_embeds("plain text", [tmp_path], str(tmp_path / "o")) == {}

    def test_searches_every_supplied_directory(self, tmp_path):
        first = tmp_path / "a"
        second = tmp_path / "b"
        first.mkdir()
        _make_png(second / "d.png")
        out = tmp_path / "out"

        copied = copy_raster_embeds("![[d.png]]", [first, second], str(out))
        assert "d.png" in copied

    def test_copying_onto_itself_is_safe(self, tmp_path):
        """Guards against shutil.SameFileError when output is the source dir."""
        _make_png(tmp_path / "d.png")
        copied = copy_raster_embeds("![[d.png]]", [tmp_path], str(tmp_path))
        assert copied["d.png"] == str(tmp_path / "d.png")
