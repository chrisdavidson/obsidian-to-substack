"""Tests for Obsidian syntax transformations."""

from obsidian_to_substack.obsidian_syntax import (
    convert_em_dashes,
    normalize_footnote_definitions,
    replace_image_embeds,
    replace_internal_links,
    transform_obsidian_syntax,
)


class TestReplaceImageEmbeds:
    def test_svg_with_center(self):
        text = "Before\n\n![[diagram.svg | center]]\n\nAfter"
        result = replace_image_embeds(text, {"diagram.svg": "/out/diagram.png"})
        assert '<figure style="text-align: center;">' in result
        assert 'src="diagram.png"' in result
        assert "Before" in result
        assert "After" in result

    def test_svg_without_map_uses_png_name(self):
        text = "![[chart.svg | center]]"
        result = replace_image_embeds(text)
        assert 'src="chart.png"' in result

    def test_png_without_modifier(self):
        text = "![[photo.png]]"
        result = replace_image_embeds(text)
        assert "<img" in result
        assert 'src="photo.png"' in result
        assert "<figure" not in result

    def test_alt_text_from_filename(self):
        text = "![[my-cool-diagram.svg | center]]"
        result = replace_image_embeds(text)
        assert 'alt="my cool diagram"' in result

    def test_multiple_embeds(self):
        text = "![[a.svg | center]]\n\n![[b.png]]"
        result = replace_image_embeds(text, {"a.svg": "/output/a.png"})
        assert 'src="a.png"' in result
        assert 'src="b.png"' in result


class TestReplaceInternalLinks:
    def test_basic_link(self):
        text = "See [[My Note]] for details."
        result = replace_internal_links(text)
        assert result == "See *My Note* for details."

    def test_link_with_special_chars(self):
        text = "Check [[OKRs? KPIs? What's the difference?]]"
        result = replace_internal_links(text)
        assert "*OKRs? KPIs? What's the difference?*" in result

    def test_does_not_affect_image_embeds(self):
        text = "![[image.svg | center]]"
        result = replace_internal_links(text)
        assert result == text

    def test_multiple_links(self):
        text = "See [[Note A]] and [[Note B]]."
        result = replace_internal_links(text)
        assert "*Note A*" in result
        assert "*Note B*" in result


class TestConvertEmDashes:
    def test_basic_em_dash(self):
        text = "This concept -- when applied -- works."
        result = convert_em_dashes(text)
        assert result == "This concept\u2014when applied\u2014works."

    def test_no_false_positives(self):
        text = "Use --flag for options."
        result = convert_em_dashes(text)
        assert result == text

    def test_preserves_code_dashes(self):
        text = "The value is `x--y` here."
        result = convert_em_dashes(text)
        assert result == text


class TestTransformObsidianSyntax:
    def test_combined_transforms(self):
        text = "See [[Note]] and ![[img.svg | center]] with -- dash."
        image_map = {"img.svg": "/output/img.png"}
        result = transform_obsidian_syntax(text, image_map=image_map)
        assert "*Note*" in result
        assert 'src="img.png"' in result
        assert "\u2014" in result
        assert "[[" not in result
        assert "![[" not in result

    def test_input_not_mutated(self):
        original = "See [[Note]] and -- dash."
        text_copy = original
        transform_obsidian_syntax(text_copy)
        assert text_copy == original

    def test_footnote_normalization_runs_before_em_dash_conversion(self):
        # F5: convert_em_dashes turns " -- " into a bare em dash with no
        # surrounding spaces. If it ran before the footnote normalizer, the
        # separator this normalizer keys on would already be destroyed.
        text = "Text with note[^1].\n\n[^1] -- The footnote content"
        result = transform_obsidian_syntax(text)
        assert "[^1]: The footnote content" in result


class TestNormalizeFootnoteDefinitions:
    def test_hyphen_form_becomes_colon_form_when_referenced(self):
        text = "Text with note[^1].\n\n[^1] - The footnote content"
        result = normalize_footnote_definitions(text)
        assert "[^1]: The footnote content" in result
        assert "note[^1]." in result

    def test_double_hyphen_separator_converts(self):
        text = "Text with note[^1].\n\n[^1] -- The footnote content"
        result = normalize_footnote_definitions(text)
        assert "[^1]: The footnote content" in result

    def test_en_dash_separator_converts(self):
        text = "Text with note[^1].\n\n[^1] \u2013 The footnote content"
        result = normalize_footnote_definitions(text)
        assert "[^1]: The footnote content" in result

    def test_em_dash_separator_converts(self):
        text = "Text with note[^1].\n\n[^1] \u2014 The footnote content"
        result = normalize_footnote_definitions(text)
        assert "[^1]: The footnote content" in result

    def test_canonical_colon_form_is_idempotent(self):
        text = "Text with note[^1].\n\n[^1]: The footnote content"
        result = normalize_footnote_definitions(text)
        assert result == text

    def test_footnote_shaped_line_inside_fenced_block_is_unchanged(self):
        text = (
            "Text with note[^1].\n\n"
            "```\n[^1] - fenced example\n```\n\n"
            "[^1] - The real definition"
        )
        result = normalize_footnote_definitions(text)
        assert "```\n[^1] - fenced example\n```" in result
        assert "[^1]: The real definition" in result

    def test_reference_inside_fence_only_does_not_license_definition(self):
        text = (
            "```\nSee [^1] for example.\n```\n\n"
            "[^1] - Not really referenced outside the fence"
        )
        result = normalize_footnote_definitions(text)
        assert result == text

    def test_unreferenced_label_left_unchanged(self):
        # A bare `[^foo] - bar` mid-document, with no other reference to
        # `foo`, is not a definition \u2014 the label's own leading marker on
        # this line must not count as licensing itself.
        text = "Some prose with no reference.\n\n[^foo] - bar"
        result = normalize_footnote_definitions(text)
        assert result == text

    def test_pure_function_no_mutation(self):
        original = "Text with note[^1].\n\n[^1] - definition"
        text_copy = original
        normalize_footnote_definitions(text_copy)
        assert text_copy == original
