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
    rewrite_image_refs,
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


class TestMarkdownImages:
    """The vault uses `![alt](path)` as well as Obsidian embeds."""

    def test_markdown_image_is_collected(self):
        assert referenced_images("![Alt text](diagram.png)") == ["diagram.png"]

    def test_long_alt_text_does_not_break_matching(self):
        text = "![A very long caption, with commas and: colons](saas-two-boxes.png)"
        assert referenced_images(text) == ["saas-two-boxes.png"]

    def test_remote_markdown_image_is_ignored(self):
        assert referenced_images("![x](https://cdn.example/x.png)") == []

    def test_both_syntaxes_collected_together(self):
        text = "![[a.png]] and ![alt](b.png)"
        assert set(referenced_images(text)) == {"a.png", "b.png"}


class TestPercentEncodedPaths:
    def test_percent_encoded_space_resolves(self, tmp_path):
        """Sources contain `saas-two-boxes%201.png` for `saas-two-boxes 1.png`."""
        _make_png(tmp_path / "saas-two-boxes 1.png")
        assert find_image("saas-two-boxes%201.png", [tmp_path]) is not None

    def test_encoded_name_copies_to_the_decoded_filename(self, tmp_path):
        source = tmp_path / "src"
        out = tmp_path / "out"
        _make_png(source / "two boxes.png")

        copy_raster_embeds("![x](two%20boxes.png)", [source], str(out))
        assert (out / "two boxes.png").is_file()


class TestStalePathPrefixes:
    def test_stale_directory_prefix_falls_back_to_basename(self, tmp_path):
        """Archived articles keep paths from where they were drafted.

        `![](2_Areas/articles/drafts/svg/x.png)` no longer resolves, but the
        file sits in the article's own directory.
        """
        source = tmp_path / "article"
        _make_png(source / "activity.png")

        found = find_image("2_Areas/articles/drafts/svg/activity.png", [source])
        assert found == source / "activity.png"


class TestRewriteImageRefs:
    def test_stale_path_is_rewritten_to_the_basename(self):
        copied = {"2_Areas/drafts/x.png": "/out/x.png"}
        text = "![Alt](2_Areas/drafts/x.png)"
        assert rewrite_image_refs(text, copied) == "![Alt](x.png)"

    def test_encoded_path_is_rewritten_to_the_decoded_basename(self):
        copied = {"two%20boxes.png": "/out/two boxes.png"}
        assert rewrite_image_refs("![a](two%20boxes.png)", copied) == "![a](two boxes.png)"

    def test_uncopied_paths_are_left_alone(self):
        text = "![a](https://cdn/x.png)"
        assert rewrite_image_refs(text, {}) == text

    def test_alt_text_is_preserved(self):
        copied = {"d/x.png": "/out/x.png"}
        result = rewrite_image_refs("![Important caption](d/x.png)", copied)
        assert "Important caption" in result
