"""Tests for Obsidian syntax transformations."""

from obsidian_to_substack.obsidian_syntax import (
    convert_em_dashes,
    normalize_footnote_definitions,
    replace_image_embeds,
    replace_internal_links,
    strip_obsidian_comments,
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

    def test_comment_stripping_runs_before_image_embed_replacement(self):
        # Proves strip_obsidian_comments is the first call: an embed written
        # inside a comment must never become markup, because the comment is
        # gone before replace_image_embeds ever sees it.
        text = "%%\n![[diagram.png]]\n%%\n\nAfter."
        result = transform_obsidian_syntax(text)
        assert "<img" not in result
        assert "diagram.png" not in result
        assert "After." in result

    def test_comment_stripping_runs_before_footnote_collection(self):
        # A footnote label referenced ONLY inside a comment must not license
        # its definition. After the comment is stripped the label is
        # unreferenced, so normalize_footnote_definitions correctly leaves
        # "[^1] - text" as literal text. That literal then legitimately
        # trips _check_footnotes' GRD-02 warning downstream -- it is not a
        # regression, it is the unbalanced/no-longer-referenced case working
        # as designed.
        text = (
            "%%\nSee [^1] for context.\n%%\n\n"
            "[^1] - The footnote content"
        )
        result = transform_obsidian_syntax(text)
        assert "context" not in result
        assert "[^1] - The footnote content" in result
        assert "[^1]: The footnote content" not in result


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


class TestStripObsidianComments:
    """Strip Obsidian %%comment%% content -- the two shapes seen in real
    output: a same-line inline pair, and a block delimited by a marker
    alone on its own line at each end. Synthetic fixtures only.
    """

    # --- Block shape ---

    def test_block_form_removes_marker_and_body_lines(self):
        text = "Para one.\n\n%%\nbody line\n%%\n\nPara two."
        result = strip_obsidian_comments(text)
        assert result == "Para one.\n\n\nPara two."
        assert "body line" not in result

    def test_block_form_body_with_blank_lines_removed_in_full(self):
        # The seven-paragraph case from F2: a block whose body itself
        # contains blank lines is still removed in its entirety.
        text = "Before.\n\n%%\nline1\n\nline2\n%%\n\nAfter."
        result = strip_obsidian_comments(text)
        assert result == "Before.\n\n\nAfter."
        assert "line1" not in result
        assert "line2" not in result

    def test_two_separate_balanced_blocks_both_removed(self):
        text = "A.\n\n%%\nc1\n%%\n\nB.\n\n%%\nc2\n%%\n\nC."
        result = strip_obsidian_comments(text)
        assert result == "A.\n\n\nB.\n\n\nC."
        assert "c1" not in result
        assert "c2" not in result

    def test_block_prose_block_prose_between_survives(self):
        # Pairing is positional -- first marker with second, third with
        # fourth. A naive "first marker to last marker" span would swallow
        # the prose between the two blocks; this test is what stops that.
        text = "%%\nc1\n%%\n\nProse between.\n\n%%\nc2\n%%"
        result = strip_obsidian_comments(text)
        assert result == "\nProse between.\n"
        assert "c1" not in result
        assert "c2" not in result

    # --- Inline shape ---

    def test_inline_comment_mid_sentence_leaves_one_space_at_seam(self):
        text = "Text %% note %% more"
        result = strip_obsidian_comments(text)
        assert result == "Text more"

    def test_inline_comment_at_start_of_line(self):
        text = "%% note %% Text"
        result = strip_obsidian_comments(text)
        assert result == "Text"

    def test_inline_comment_at_end_of_line_leaves_no_trailing_space(self):
        text = "Text %% note %%"
        result = strip_obsidian_comments(text)
        assert result == "Text"

    def test_inline_comment_does_not_leave_indented_code_block(self):
        # Critically NOT four leading spaces, which python-markdown would
        # render as an indented code block.
        text = "%% note %%    Text"
        result = strip_obsidian_comments(text)
        assert result == "Text"

    def test_inline_comment_preserves_list_indentation(self):
        text = "  - item %% note %% rest"
        result = strip_obsidian_comments(text)
        assert result == "  - item rest"

    def test_comment_only_line_is_dropped_not_blanked(self):
        # The outer lines are one lazy-continuation paragraph; leaving a
        # blank line in place of the comment-only line would split them
        # into two paragraphs.
        text = "Line one\n%% aside %%\nline three"
        result = strip_obsidian_comments(text)
        assert result == "Line one\nline three"

    def test_two_inline_comments_on_one_line_both_removed(self):
        text = "A %% one %% B %% two %% C"
        result = strip_obsidian_comments(text)
        assert result == "A B C"

    # --- Exemptions: returned byte-identical ---

    def test_comment_shaped_line_inside_fence_is_untouched(self):
        text = "```\n%% not a comment %%\n```"
        result = strip_obsidian_comments(text)
        assert result == text

    def test_comment_shaped_span_inside_inline_code_is_untouched(self):
        text = "Use `%% note %%` for asides."
        result = strip_obsidian_comments(text)
        assert result == text

    def test_fenced_block_of_a_lone_marker_line_is_not_a_block_delimiter(self):
        text = "```\n%%\n```"
        result = strip_obsidian_comments(text)
        assert result == text

    # --- Fail-safe: never delete to end of document ---

    def test_odd_number_of_block_markers_strips_no_block_at_all(self):
        # An odd count means at least one marker is unclosed, and which
        # marker is the stray one is unknowable. Pairing positionally from
        # the top would pair an unclosed opener with the NEXT comment's
        # opener and silently delete the real prose in between (see
        # test_unclosed_opener_does_not_swallow_the_prose_after_it).
        # Deleted prose is unrecoverable; a surviving comment is not, and
        # preflight's check fires on every marker left behind. So the whole
        # block pass bails: nothing is removed, everything survives.
        text = (
            "Before.\n\n%%\nblock1\n%%\n\n"
            "%%\nafter this marker everything survives"
        )
        result = strip_obsidian_comments(text)
        assert result == text
        assert "block1" in result

    def test_unclosed_opener_does_not_swallow_the_prose_after_it(self):
        # The case the bail exists for. With positional pairing the first
        # marker (unclosed) would pair with the second (the real comment's
        # opener), taking "Keep me." with it.
        text = "%%\n\nKeep me.\n\n%%\nreal note\n%%\n\nEnd."
        result = strip_obsidian_comments(text)
        assert result == text
        assert "Keep me." in result

    def test_even_block_markers_still_strip_normally(self):
        # The bail is scoped to the odd case only -- a balanced document is
        # unaffected by it.
        text = "Before.\n\n%%\nblock1\n%%\n\nAfter."
        result = strip_obsidian_comments(text)
        assert "block1" not in result
        assert "Before." in result
        assert "After." in result

    def test_inline_line_with_single_unmatched_marker_is_unchanged(self):
        text = "Some text %% unmatched"
        result = strip_obsidian_comments(text)
        assert result == text

    # --- Fail-safe: a literal doubled percent in prose is not an opener ---

    def test_literal_double_percent_in_prose_is_not_treated_as_a_comment(self):
        # "50%% up from 20%%" has two markers on one line, so a bare
        # `%%.*?%%` reads it as a comment and deletes " up from 20" --
        # silent prose loss with nothing left to warn about. An opening
        # marker must sit at the start of the line or follow whitespace, so
        # a marker glued to the end of a word can never open a comment.
        text = "Growth was 50%% up from 20%% last year."
        result = strip_obsidian_comments(text)
        assert result == text

    def test_single_literal_double_percent_is_unchanged(self):
        text = "Use 100%% of the budget."
        result = strip_obsidian_comments(text)
        assert result == text

    def test_real_comment_survives_alongside_a_literal_percent(self):
        # The guard must not cost us the real case: the comment's opener
        # follows a space and is still stripped, while the literal stays.
        text = "The rate rose 5%% %% but check this %% today."
        result = strip_obsidian_comments(text)
        assert result == "The rate rose 5%% today."

    def test_comment_at_line_start_is_still_an_opener(self):
        # Start-of-line counts as a boundary even with no whitespace
        # before it -- this is the shape observed in the real article.
        text = "%% Source data for the diagram above. %%"
        result = strip_obsidian_comments(text)
        assert result == ""

    # --- Contract ---

    def test_text_with_no_marker_is_returned_identical(self):
        text = "Plain text.\n\nAnother paragraph."
        result = strip_obsidian_comments(text)
        assert result == text

    def test_idempotent(self):
        text = "Intro %% note %% continues.\n\n%%\nBlock body.\n%%\n\nOutro."
        once = strip_obsidian_comments(text)
        twice = strip_obsidian_comments(once)
        assert twice == once

    def test_pure_function_no_mutation(self):
        original = "Intro %% note %% continues."
        text_copy = original
        strip_obsidian_comments(text_copy)
        assert text_copy == original
