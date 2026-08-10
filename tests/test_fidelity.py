"""Tests for the source-to-output fidelity comparator.

The comparator answers one question: did the pipeline remove text the author
wrote, without an accountable reason? Two real defects motivate it, and both
appear here as fixtures:

* the 2026-08-08 leak, where `%%` comment content reached a live published post
* the `260809-a1o` near-miss, where the first cut of `strip_obsidian_comments`
  turned "Growth was 50%% up from 20%% last year." into "Growth was 50last
  year." with nothing left behind to warn about

The acceptance test is `test_fires_on_the_reverted_stripper`. It reproduces the
old buggy stripper and asserts the comparator reports the loss. If that test
can be made to pass by a comparator that reuses the pipeline's own transforms,
the comparator is worthless — see the module docstring in fidelity.py.
"""

from __future__ import annotations

import re

from obsidian_to_substack.fidelity import (
    authorized_spans,
    compare,
    comment_spans,
    footnote_definition_lines,
    tokenize,
)
from obsidian_to_substack.obsidian_syntax import (
    strip_obsidian_comments,
    transform_obsidian_syntax,
)
from obsidian_to_substack.render_html import render_to_html


# --------------------------------------------------------------------------
# The reverted stripper: strip_obsidian_comments as it existed before the
# fail-closed revision in 260809-a1o. Reproduced here rather than imported,
# because the point of the acceptance test is to run the comparator against
# output the current code can no longer produce.
#
# Two differences from the shipped version, both defects:
#   1. no digit lookbehind — "50%% ... 20%%" reads as a comment
#   2. positional pairing regardless of parity — an unclosed opener pairs with
#      the NEXT comment's opening marker, deleting the prose between them
# --------------------------------------------------------------------------
_BUGGY_INLINE = re.compile(r"(?P<code>`+[^`]*`+)|(?P<comment>%%.*?%%[ \t]*)")


def _buggy_strip_obsidian_comments(text: str) -> str:
    lines = text.split("\n")

    marker_indices = [i for i, line in enumerate(lines) if line.strip() == "%%"]
    remove: set[int] = set()
    # No parity check — this is defect 2.
    for start, end in zip(marker_indices[0::2], marker_indices[1::2]):
        remove.update(range(start, end + 1))
    kept = [line for i, line in enumerate(lines) if i not in remove]

    out = []
    for line in kept:
        substituted = _BUGGY_INLINE.sub(
            lambda m: m.group("code") if m.group("code") is not None else "", line
        )
        if line.strip() and not substituted.strip():
            continue
        out.append(substituted.rstrip() if substituted != line else line)
    return "\n".join(out)


def _render(markdown_text: str) -> str:
    """Run the real pipeline's transform + render, as convert_article does."""
    return render_to_html(transform_obsidian_syntax(markdown_text))


def _render_with_buggy_stripper(markdown_text: str) -> str:
    """Render via the reverted stripper, skipping the shipped one."""
    return render_to_html(_buggy_strip_obsidian_comments(markdown_text))


class TestAcceptanceCriterion:
    """The test this whole module exists to make possible."""

    def test_fires_on_the_reverted_stripper(self):
        # The exact prose from the near-miss recorded in FINDINGS-MANUAL.md.
        source = "Growth was 50%% up from 20%% last year.\n"

        html = _render_with_buggy_stripper(source)
        assert "up from" not in html, "fixture invalid: buggy stripper did not bite"

        report = compare(source, html)

        assert not report.is_clean
        lost = " ".join(r.text for r in report.unaccounted)
        assert "up" in lost and "from" in lost and "20" in lost

    def test_clean_against_the_shipped_stripper(self):
        source = "Growth was 50%% up from 20%% last year.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_fires_when_an_unbalanced_opener_eats_real_prose(self):
        # A stray opener, then a genuine comment. The buggy pairing joins the
        # stray to the genuine comment's OPENING marker and deletes the real
        # paragraph sitting between them.
        source = (
            "Intro paragraph.\n"
            "\n"
            "%%\n"
            "\n"
            "This paragraph is real prose and must survive.\n"
            "\n"
            "%%\n"
            "a private note\n"
            "%%\n"
            "\n"
            "Closing paragraph.\n"
        )

        html = _render_with_buggy_stripper(source)
        assert "real prose" not in html, "fixture invalid: buggy pairing did not bite"

        report = compare(source, html)

        assert not report.is_clean
        lost = " ".join(r.text for r in report.unaccounted)
        assert "real" in lost and "prose" in lost


class TestLegitimateRemovals:
    """Everything the pipeline is allowed to drop must be accounted for."""

    def test_block_comment_content_is_accounted_for(self):
        source = (
            "Real text before.\n"
            "\n"
            "%%\n"
            "a private note to self\n"
            "spanning two lines\n"
            "%%\n"
            "\n"
            "Real text after.\n"
        )

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "comment" in report.reasons_used

    def test_inline_comment_content_is_accounted_for(self):
        source = "Visible prose %%hidden aside%% continues here.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_frontmatter_is_accounted_for(self):
        source = (
            "---\n"
            "title: Something\n"
            "tags: [alpha, beta]\n"
            "---\n"
            "\n"
            "The body text.\n"
        )
        body = source.split("---\n")[2]

        report = compare(source, _render(body))

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "frontmatter" in report.reasons_used

    def test_stripped_title_is_accounted_for(self):
        source = "# The Article Title\n\nBody paragraph.\n"
        html = "<html><body><p>Body paragraph.</p></body></html>"

        report = compare(source, html, resolved_title="The Article Title")

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "title" in report.reasons_used

    def test_table_text_is_reconciled_against_extracted_cells(self):
        # Table prose is RELOCATED into the PNG/CSV, not vanished. It is
        # accounted for only because the cell text is held in hand.
        source = (
            "Before.\n"
            "\n"
            "| Region | Revenue |\n"
            "|--------|---------|\n"
            "| North  | 1200    |\n"
            "\n"
            "After.\n"
        )
        tables = [[["Region", "Revenue"], ["North", "1200"]]]
        html = "<html><body><p>Before.</p><p>After.</p></body></html>"

        report = compare(source, html, tables=tables)

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "table" in report.reasons_used

    def test_table_text_absent_from_the_cells_is_not_excused(self):
        # A table line whose words are NOT in the extracted cells means the
        # extraction lost them — exactly what this check is for. Position on a
        # table line must not be enough on its own.
        source = "| Region | Revenue |\n|--------|---------|\n| North | 1200 |\n"
        tables = [[["Region", "Revenue"]]]  # the North row never made it
        html = "<html><body></body></html>"

        report = compare(source, html, tables=tables)

        assert not report.is_clean
        lost = " ".join(r.text for r in report.unaccounted)
        assert "North" in lost

    def test_image_embed_syntax_is_accounted_for(self):
        source = "Text.\n\n![[diagram-one.svg | center]]\n\nMore text.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_link_target_is_accounted_for(self):
        source = "See [the docs](https://example.com/deep/path) for detail.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"


class TestNoFalsePositives:
    """Constructs that must never be reported."""

    def test_fenced_code_survives_and_is_not_reported(self):
        source = (
            "Prose.\n"
            "\n"
            "```python\n"
            "x = 1  # a comment with %% markers %% inside\n"
            "```\n"
            "\n"
            "More prose.\n"
        )

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_em_dash_conversion_is_not_a_removal(self):
        source = "One thing -- and another -- follow.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_a_dash_joining_two_words_tokenizes_alike_on_both_sides(self):
        # The assertion above passes whether or not dashes are handled: with
        # spaces around it, " -- " yields no token on either side. The case
        # that would actually bite is a dash gluing two words together, where
        # the source's "--" must split exactly as the output's em dash does.
        assert [t.word for t in tokenize("a--b")] == ["a", "b"]
        assert [t.word for t in tokenize("a—b")] == ["a", "b"]
        assert [t.word for t in tokenize("a–b")] == ["a", "b"]

    def test_smart_quotes_are_not_a_removal(self):
        source = "The author's \"quoted phrase\" stays put.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_wikilink_text_survives(self):
        source = "Refer to [[Some Other Note]] for background.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_formatting_markup_is_not_a_removal(self):
        source = "This is **bold** and *italic* and `code`.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_headings_and_lists_survive(self):
        source = "## A Heading\n\n- first item\n- second item\n\n1. numbered\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"


class TestCorpusNoiseCategories:
    """Each of these was a false positive the first corpus sweep produced.

    Pinned so they cannot come back. Together they took the sweep from 20
    findings across 11 articles to 0 across 46, at 93.8% word coverage.
    """

    def test_self_referential_link_does_not_report_its_own_label(self):
        # 18 of the first sweep's 20 findings were this. The vault links to the
        # author's own posts, so the label and the URL slug carry the same
        # words; with the URL left in the comparison, SequenceMatcher aligns
        # the surviving label against the source's URL and calls the label
        # deleted.
        source = (
            "In [The Architect and the Taxonomy]"
            "(https://example.com/p/the-architect-and-the-taxonomy), "
            "we established the frame.\n"
        )

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_underscore_emphasis_is_not_reported(self):
        source = "Underscores too: _italic_ and __bold__.\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_raw_html_tag_names_are_accounted_for_but_content_is_not(self):
        # The corpus writes <u>...</u>. strip_unsupported_elements unwraps `u`
        # and keeps its content, so only the tag text disappears.
        source = "- <u>A system of classification</u>\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "html_tag" in report.reasons_used

    def test_markdown_image_alt_text_is_accounted_for(self):
        source = "![A caption for the image](diagram.png)\n"

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "image_alt" in report.reasons_used

    def test_title_is_found_after_a_frontmatter_block(self):
        # Walking "---" alone stops at the first `tags:` line and gives up,
        # which reported the torture fixture's real title as lost.
        source = "---\ntags:\n  - fixture\n---\n# The Real Title\n\nBody.\n"
        html = "<html><body><p>Body.</p></body></html>"

        report = compare(source, html, resolved_title="The Real Title")

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "title" in report.reasons_used


class TestRelocatedFootnoteDefinitions:
    """A footnote definition moves to the end of the document when rendered.

    `SequenceMatcher` can only align in order, so a definition written in the
    middle of the source arrives after text that followed it and one of the two
    runs reads as deleted. The fixture's footnotes all sit at end-of-file, which
    is why nothing caught this — and the corpus has exactly one footnoted
    article, whose definition is also at the end.
    """

    def test_mid_document_definition_is_not_reported(self):
        source = (
            "Intro prose with a footnote.[^1]\n"
            "\n"
            "[^1]: The footnote body written the canonical way.\n"
            "\n"
            "A final paragraph that plainly survives into the output.\n"
        )

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "footnote_definition" in report.reasons_used

    def test_mid_document_definition_in_the_vault_hyphen_form(self):
        # The form Obsidian sources actually write, normalized by the pipeline
        # before rendering. Fidelity re-derives the pattern rather than calling
        # normalize_footnote_definitions, so it has to know both shapes itself.
        source = (
            "Intro prose with a footnote.[^1]\n"
            "\n"
            "[^1] - The footnote body written the Obsidian way.\n"
            "\n"
            "A final paragraph that plainly survives into the output.\n"
        )

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"
        assert "footnote_definition" in report.reasons_used

    def test_continuation_lines_are_reconciled_too(self):
        source = (
            "Intro prose with a footnote.[^long]\n"
            "\n"
            "[^long]: The opening sentence of the definition.\n"
            "    A continuation line indented beneath it.\n"
            "\n"
            "A final paragraph that plainly survives into the output.\n"
        )

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_a_definition_that_never_arrives_is_still_reported(self):
        # The guard against fixing the false positive by going blind. Sitting
        # on a definition line must not excuse a token on its own — a footnote
        # body the renderer genuinely dropped sits on one too, and that is the
        # loss this module exists to catch.
        source = (
            "Intro prose with a footnote.[^1]\n"
            "\n"
            "[^1]: Words that the renderer swallowed entirely.\n"
        )
        html = "<html><body><p>Intro prose with a footnote.</p></body></html>"

        report = compare(source, html)

        assert not report.is_clean
        lost = " ".join(removal.text for removal in report.unaccounted)
        assert "swallowed" in lost

    def test_a_lost_definition_is_not_excused_by_another_footnote(self):
        # The words have to arrive in THIS footnote, not merely somewhere in
        # the footnote list. Pooling every definition's words into one set lets
        # a sibling that happens to share vocabulary vouch for a body that was
        # dropped outright — a false negative in the ledger, which is the one
        # failure this module exists to prevent.
        source = (
            "Intro.[^1] More.[^2]\n"
            "\n"
            "[^1]: the shared body text\n"
            "\n"
            "[^2]: the shared body text\n"
            "\n"
            "Tail paragraph here.\n"
        )
        html = (
            "<html><body><p>Intro. More.</p><p>Tail paragraph here.</p>"
            '<ol><li id="fn:2"><p>the shared body text</p></li></ol></body></html>'
        )

        report = compare(source, html)

        assert not report.is_clean, "a dropped footnote body vouched for by its sibling"

    def test_words_missing_from_a_definition_are_still_reported(self):
        # The partial case: the definition arrived, but not all of it.
        source = "Intro.[^1]\n\n[^1]: the body of a much longer sentence\n"
        html = (
            "<html><body><p>Intro.</p>"
            '<ol><li id="fn:1"><p>the body</p></li></ol></body></html>'
        )

        report = compare(source, html)

        assert not report.is_clean
        lost = " ".join(removal.text for removal in report.unaccounted)
        assert "longer sentence" in lost

    def test_an_end_of_document_definition_still_reports_clean(self):
        # The case that already worked. It has to keep working.
        source = (
            "Intro prose with a footnote.[^1]\n"
            "\n"
            "A final paragraph that plainly survives into the output.\n"
            "\n"
            "[^1]: The footnote body written the canonical way.\n"
        )

        report = compare(source, _render(source))

        assert report.is_clean, f"false positive: {report.unaccounted}"

    def test_prose_after_a_definition_is_still_compared(self):
        # The definition must not swallow the rest of the document. If the
        # trailing paragraph really vanished, that has to still be reported.
        source = (
            "Intro prose with a footnote.[^1]\n"
            "\n"
            "[^1]: The footnote body written the canonical way.\n"
            "\n"
            "A trailing paragraph the renderer lost completely.\n"
        )
        html = (
            "<html><body><p>Intro prose with a footnote.</p>"
            '<ol><li id="fn:1"><p>The footnote body written the canonical '
            "way.</p></li></ol></body></html>"
        )

        report = compare(source, html)

        assert not report.is_clean
        lost = " ".join(removal.text for removal in report.unaccounted)
        assert "trailing" in lost


class TestFootnoteDefinitionLines:
    """Where the definition block starts and, more importantly, where it stops."""

    def test_both_marker_forms_are_found(self):
        source = "[^1]: canonical\n[^2] - obsidian\n"

        assert footnote_definition_lines(source) == frozenset({1, 2})

    def test_a_definition_does_not_run_into_following_prose(self):
        # The block must end, or it would swallow the rest of the article and
        # excuse every later loss by association.
        source = "[^1]: the body\n\nOrdinary prose resumed here.\n"

        assert footnote_definition_lines(source) == frozenset({1})

    def test_a_blank_line_between_indented_parts_is_kept(self):
        source = "[^1]: first paragraph\n\n    second paragraph\n\nBody again.\n"

        assert footnote_definition_lines(source) == frozenset({1, 2, 3})

    def test_several_blank_lines_before_a_continuation_are_kept(self):
        source = "[^1]: first\n\n\n    second\n\nBody again.\n"

        assert footnote_definition_lines(source) == frozenset({1, 2, 3, 4})

    def test_trailing_blank_lines_at_eof_are_not_claimed(self):
        # The held blanks are never flushed, so they must not leak into the
        # block by default.
        source = "Body.\n\n[^1]: the definition\n\n\n"

        assert footnote_definition_lines(source) == frozenset({3})

    def test_fenced_code_is_skipped(self):
        # An article that documents footnote syntax is correct output; those
        # words stay in the body where they were written.
        source = "```\n[^1]: not a real definition\n```\n"

        assert footnote_definition_lines(source) == frozenset()

    def test_a_footnote_marker_in_prose_is_not_a_definition(self):
        source = "A sentence citing [^1] mid-line.\n"

        assert footnote_definition_lines(source) == frozenset()


class TestCoverage:
    """A clean report means nothing without knowing how much was compared."""

    def test_coverage_reports_the_compared_share(self):
        source = "Plain prose with no authorized spans at all.\n"

        report = compare(source, _render(source))

        assert report.coverage == 1.0

    def test_coverage_falls_when_spans_withhold_words(self):
        source = "---\ntitle: x\ntags: [alpha, beta, gamma]\n---\n\nShort body.\n"

        report = compare(source, _render("\nShort body.\n"))

        assert report.is_clean
        assert report.coverage < 1.0

    def test_line_numbers_are_one_based(self):
        # A 0-based report sends the author to the wrong line in their editor.
        source = "first line\nsecond line\n"
        html = "<html><body><p>first line</p></body></html>"

        report = compare(source, html)

        assert report.unaccounted
        assert report.unaccounted[0].line == 2


class TestIndependenceFromThePipeline:
    """The comparator's comment rule must be its own, not the stripper's."""

    def test_comment_spans_refuses_a_digit_preceded_marker(self):
        # Independently re-derived, but it must reach the same verdict as
        # strip_obsidian_comments on this input, or the check is broken.
        text = "Growth was 50%% up from 20%% last year."

        assert comment_spans(text) == ()
        assert strip_obsidian_comments(text) == text

    def test_comment_spans_bails_on_an_odd_marker_count(self):
        text = "a\n%%\nb\n%%\nc\n%%\nd\n"

        # Three lone markers: no block may be authorized as a comment.
        spans = comment_spans(text)
        assert all("b" not in text[s:e] for s, e in spans)

    def test_comment_spans_skips_fenced_code(self):
        text = "```\n%%\nnot a comment\n%%\n```\n"

        assert comment_spans(text) == ()


class TestPurity:
    def test_pure_function_no_mutation(self):
        source = "%%\nnote\n%%\n\nBody with a [link](https://example.com).\n"
        html = _render(source)
        source_copy = source
        html_copy = html

        compare(source, html)
        tokenize(source)
        comment_spans(source)
        footnote_definition_lines(source)
        authorized_spans(source, resolved_title="", tables=())

        assert source == source_copy
        assert html == html_copy
