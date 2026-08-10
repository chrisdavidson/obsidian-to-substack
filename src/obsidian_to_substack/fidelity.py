"""Compare the author's source Markdown against the pipeline's rendered HTML.

Every other guard in this project checks that the output is *valid*. This one
checks that the output still contains what the author wrote. Two real defects
motivate it:

* **The leak (2026-08-08).** A published post carried an inline aside and a
  34-line caption/alt-text block from Obsidian `%%` comments. The author did not
  catch it by reading the post; it surfaced by accident days later.
* **The near-miss (`260809-a1o`).** The first cut of `strip_obsidian_comments`
  deleted real prose silently -- `Growth was 50%% up from 20%% last year.`
  became `Growth was 50last year.` -- leaving no marker behind for preflight to
  report.

Deleted prose is the one failure mode this project cannot recover from, because
it destroys its own evidence. That is what this module is for.

THE INDEPENDENCE RULE -- READ BEFORE CHANGING ANYTHING HERE
-----------------------------------------------------------
This module must NEVER call `strip_obsidian_comments`,
`transform_obsidian_syntax`, or any other pipeline transform to decide what was
legitimately removed. If it did, a bug *inside* that transform would be
invisible by construction: both sides would delete the same prose and agree.
Run the near-miss above through a comparator built on the transform and it
reports clean.

So `comment_spans` below re-derives the comment rule from scratch -- its own
digit lookbehind, its own odd-count bail, its own fence tracking. It is
deliberately a second implementation of a judgement the codebase already makes
elsewhere.

**This is a considered departure from the house convention** that "where a
transform and a check make the same judgement, they share the rule and say so."
That convention is correct for `preflight._check_obsidian_comments`, which
inspects *output* for surviving markers: sharing the rule there prevents false
positives, and a false positive is noise the author cannot act on. It is wrong
here, where the subject is *what was deleted*: sharing the rule produces false
negatives, and a false negative here is the exact defect class the module
exists to catch. Do not "tidy" this by importing
`obsidian_syntax.INLINE_COMMENT_PATTERN` or
`preflight.OBSIDIAN_COMMENT_MARKER_PATTERN`. The duplication is the feature.

`tests/test_fidelity.py::TestIndependenceFromThePipeline` pins that the two
rules nonetheless agree on the inputs that matter, so drift is caught.

THE LEDGER
----------
This is an accounting ledger, not a diff with an exclusion list. Every run of
source text missing from the output must be attributable to a named reason
whose evidence is held in hand -- the frontmatter block, the resolved title,
the extracted table cells, a comment span computed here. Anything left over is
reported. The distinction matters for tables especially: table prose is not
*vanished*, it is *relocated* into the PNG and CSV, so it reconciles exactly
against `extract_tables`' cell text rather than being waved through because it
sat on a line starting with a pipe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from types import MappingProxyType
from typing import Mapping, Sequence

from bs4 import BeautifulSoup

# A word is letters and digits, optionally carrying internal apostrophes.
# Everything else -- every dash, quote, pipe, hash, asterisk and bracket -- is
# invisible to the comparison.
#
# The underscore is deliberately NOT a word character, though it is one to
# `\w`. Markdown reads `_italic_` and `__bold__` as emphasis, so the source
# carries underscores the output does not; treating them as part of the word
# made `_italic_` and `italic` different tokens and reported live prose as
# lost. Splitting `snake_case` in a code block is the cost, and it is no cost
# at all -- both sides split it the same way.
#
# That is what makes the whole comparison robust against `smarty` and the
# ` -- ` em-dash conversion without needing a normalisation pass: source
# `don't`, `"quoted"` and `a -- b` and output `don’t`, `“quoted”` and `a—b`
# tokenize identically. Normalising the strings instead would shift character
# offsets and break span attribution, and would itself be a transform whose
# bugs could hide a real deletion.
WORD_PATTERN = re.compile(r"[0-9A-Za-z]+(?:['’][0-9A-Za-z]+)*")

# This module's OWN comment rule. See the independence note above -- these
# deliberately duplicate obsidian_syntax's patterns rather than importing them.
#
# The digit lookbehind reaches the same verdict as the stripper's for the same
# reason: a doubled percent is legal prose ("50%% up from 20%%"), and reading
# it as a comment is what deleted text in the near-miss. Here the consequence
# of getting it wrong is inverted -- without the lookbehind this module would
# *excuse* that deletion instead of reporting it.
_OWN_INLINE_COMMENT = re.compile(
    r"(?P<code>`+[^`]*`+)|(?P<comment>(?<![0-9])%%.*?%%[ \t]*)"
)
_OWN_BARE_MARKER = "%%"

_FENCE_PREFIXES = ("```", "~~~")

# A table row, for locating table text in the source. Position alone never
# excuses a removal -- see _attribute -- so this pattern only narrows where to
# look, and the extracted cell text does the actual accounting.
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")

# A fenced block's info string (the "python" in ```python) becomes a class
# attribute on <code>, never body text.
_FENCE_INFO = re.compile(r"^\s*(?:```|~~~)\s*(?P<info>\S+.*?)\s*$")

# An ordered list's marker becomes <ol> structure, so the digit leaves the
# text. Unordered markers need no entry -- "-" and "*" are punctuation and are
# invisible to WORD_PATTERN already.
_ORDERED_MARKER = re.compile(r"^\s*(?P<marker>\d+)[.)]\s")

# A footnote definition line, in both shapes the corpus writes: the canonical
# `[^1]: body` and Obsidian's `[^1] - body`, which the pipeline normalizes into
# the first. Re-derived here rather than imported from
# normalize_footnote_definitions, for the reason the module docstring gives at
# length: a comparator that asks a transform what it did cannot see the
# transform being wrong.
#
# Position alone never excuses a removal -- see _attribute -- so this pattern
# only narrows where to look, exactly as _TABLE_LINE does.
_FOOTNOTE_DEFINITION = re.compile(r"^\s{0,3}\[\^(?P<label>[^\]]+)\]\s*(?::|-)\s")

# A definition continues onto following indented lines. They are part of the
# same relocated block and move with it.
_FOOTNOTE_CONTINUATION = re.compile(r"^(?:\t| {4,})\S")

_FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---[ \t]*\r?\n", re.DOTALL)
_IMAGE_EMBED = re.compile(r"!\[\[[^\]]*\]\]")
_LINK_TARGET = re.compile(r"\]\(([^)]*)\)")

# A markdown image's alt text becomes an `alt` attribute, not body text. The
# leading "!" is what separates this from an ordinary link, whose visible label
# does survive and must never be authorized here.
_IMAGE_ALT = re.compile(r"!\[(?P<alt>[^\]]*)\]\(")
_FOOTNOTE_MARKER = re.compile(r"\[\^[^\]]+\]")

# A raw HTML tag written into the Markdown. The tag name and its attributes are
# markup, not prose -- the corpus writes `<u>...</u>` for emphasis, and
# `strip_unsupported_elements` unwraps `u` while keeping its content, so only
# the angle-bracket text disappears. Matching the whole tag leaves everything
# BETWEEN the tags comparable, which is the part that must survive.
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*?)?/?>")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<text>.*?)\s*#*\s*$")


@dataclass(frozen=True)
class Token:
    """One source word and where it sits."""

    word: str
    start: int
    end: int
    line: int


@dataclass(frozen=True)
class Span:
    """A character range the pipeline is authorized to drop, and why."""

    start: int
    end: int
    reason: str


@dataclass(frozen=True)
class Removal:
    """A run of source text missing from the output with no accountable reason."""

    text: str
    line: int

    def format(self) -> str:
        return f"  line {self.line}: {self.text}"


@dataclass(frozen=True)
class FidelityReport:
    """The ledger. Empty `unaccounted` means the output kept the author's text."""

    unaccounted: tuple[Removal, ...]
    reasons_used: frozenset[str]
    source_word_count: int
    compared_word_count: int = 0

    @property
    def is_clean(self) -> bool:
        return not self.unaccounted

    @property
    def coverage(self) -> float:
        """Share of source words actually compared, 0.0-1.0.

        A clean report only means something alongside this number. Every
        authorized span withholds words from the comparison, so a check that
        authorized everything would also report clean -- and would be worthless.
        Coverage is what distinguishes "nothing was lost" from "nothing was
        looked at."
        """
        if not self.source_word_count:
            return 1.0
        return self.compared_word_count / self.source_word_count

    def format(self) -> str:
        if self.is_clean:
            return "fidelity: clean"
        lines = [f"fidelity: {len(self.unaccounted)} unaccounted removal(s)"]
        lines.extend(removal.format() for removal in self.unaccounted)
        return "\n".join(lines)


def tokenize(text: str) -> tuple[Token, ...]:
    """Split text into comparable word tokens with source offsets.

    Pure: returns a new tuple, never mutates the input.
    """
    line_starts = _line_starts(text)
    return tuple(
        Token(
            word=match.group(0).replace("’", "'"),
            start=match.start(),
            end=match.end(),
            # 1-based: these numbers are read against the source file in an
            # editor, and a 0-based report sends the author to the wrong line.
            line=_line_of(match.start(), line_starts) + 1,
        )
        for match in WORD_PATTERN.finditer(text)
    )


def comment_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Character ranges this module judges to be Obsidian comments.

    An independent re-derivation of the stripper's rule -- see the module
    docstring for why it must not import one. Both fail-safes are reproduced,
    and both matter more here than they do in the stripper:

    * **Odd marker count bails entirely.** If some comment is unclosed, which
      one is the stray is unknowable, so no block is authorized at all. The
      stripper's version of this prevents deleting prose; this one prevents
      *excusing* prose that a buggy stripper deleted.
    * **A digit-preceded marker never opens a comment**, so "50%% up from 20%%"
      contributes no span and any text lost from it is reported.

    Fenced code is skipped by both passes, matching the stripper, so an article
    that documents `%%` syntax inside a fence yields no spans.

    Pure: returns a new tuple, never mutates the input.
    """
    lines = text.split("\n")
    line_starts = _line_starts(text)

    marker_lines: list[int] = []
    in_fence = False
    for index, line in enumerate(lines):
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.strip() == _OWN_BARE_MARKER:
            marker_lines.append(index)

    spans: list[tuple[int, int]] = []
    blocked: set[int] = set()
    if len(marker_lines) % 2 == 0:
        for start_line, end_line in zip(marker_lines[0::2], marker_lines[1::2]):
            blocked.update(range(start_line, end_line + 1))
            spans.append(
                (
                    line_starts[start_line],
                    line_starts[end_line] + len(lines[end_line]),
                )
            )

    in_fence = False
    for index, line in enumerate(lines):
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence or index in blocked:
            continue
        for match in _OWN_INLINE_COMMENT.finditer(line):
            if match.group("comment") is None:
                continue
            offset = line_starts[index]
            spans.append((offset + match.start(), offset + match.end()))

    return tuple(sorted(spans))


def authorized_spans(
    source: str,
    *,
    resolved_title: str = "",
    tables: Sequence[Sequence[Sequence[str]]] = (),
) -> tuple[Span, ...]:
    """Every character range the pipeline may legitimately drop, with its reason.

    Table lines are deliberately absent: position on a table line is not
    authorization on its own, because the defect worth catching is extraction
    losing a row. Table text is reconciled token-by-token against the extracted
    cells in `_attribute` instead.

    Pure: returns a new tuple, never mutates the inputs.
    """
    spans: list[Span] = []

    frontmatter = _FRONTMATTER.match(source)
    if frontmatter:
        spans.append(Span(frontmatter.start(), frontmatter.end(), "frontmatter"))

    if resolved_title.strip():
        title_span = _leading_title_span(source, resolved_title)
        if title_span is not None:
            spans.append(Span(title_span[0], title_span[1], "title"))

    spans.extend(Span(start, end, "comment") for start, end in comment_spans(source))

    # The whole `![[file.svg | center]]` construct: the extension and the
    # alignment modifier never reach the rendered text, and the stem only
    # survives as an alt attribute BeautifulSoup does not surface.
    spans.extend(
        Span(match.start(), match.end(), "image_embed")
        for match in _IMAGE_EMBED.finditer(source)
    )

    # A link's target moves into an href attribute, so its words leave the
    # body text. Only the target is authorized -- the link's visible label is
    # outside the captured group and must still survive.
    spans.extend(
        Span(match.start(1), match.end(1), "link_target")
        for match in _LINK_TARGET.finditer(source)
    )

    spans.extend(
        Span(match.start("alt"), match.end("alt"), "image_alt")
        for match in _IMAGE_ALT.finditer(source)
    )

    spans.extend(
        Span(match.start(), match.end(), "footnote_marker")
        for match in _FOOTNOTE_MARKER.finditer(source)
    )

    spans.extend(
        Span(match.start(), match.end(), "html_tag")
        for match in _HTML_TAG.finditer(source)
    )

    spans.extend(_markup_spans(source))

    return tuple(spans)


def _markup_spans(source: str) -> tuple[Span, ...]:
    """Per-line markup whose words become structure rather than text.

    Both entries are things markdown moves out of the body: a fence's info
    string into a `class` attribute, an ordered list's number into `<ol>`.
    Neither is prose, and both showed up as false positives the first time this
    module met a real article -- which is the argument for measuring noise
    against the corpus rather than reasoning about it.
    """
    spans: list[Span] = []
    offset = 0
    in_fence = False
    for line in source.split("\n"):
        if _is_fence(line):
            info = _FENCE_INFO.match(line)
            if info is not None and not in_fence:
                spans.append(
                    Span(
                        offset + info.start("info"),
                        offset + info.end("info"),
                        "fence_info",
                    )
                )
            in_fence = not in_fence
            offset += len(line) + 1
            continue
        if not in_fence:
            marker = _ORDERED_MARKER.match(line)
            if marker is not None:
                spans.append(
                    Span(
                        offset + marker.start("marker"),
                        offset + marker.end("marker"),
                        "list_marker",
                    )
                )
        offset += len(line) + 1
    return tuple(spans)


def compare(
    source_markdown: str,
    output_html: str,
    *,
    resolved_title: str = "",
    tables: Sequence[Sequence[Sequence[str]]] = (),
) -> FidelityReport:
    """Report source text missing from the output without an accountable reason.

    `tables` takes the parsed rows from `extract_tables` -- the cell text this
    module reconciles relocated table prose against.

    Pure: returns a new report, never mutates the inputs.
    """
    source_tokens = tokenize(source_markdown)
    output_words = [token.word.casefold() for token in tokenize(_visible_text(output_html))]

    spans = authorized_spans(
        source_markdown, resolved_title=resolved_title, tables=tables
    )
    table_lines = _table_lines(source_markdown)
    definition_owners = footnote_definition_labels(source_markdown)
    definition_words = _footnote_words(output_html)
    table_words = {
        word.casefold()
        for table in tables
        for row in table
        for cell in row
        for word in WORD_PATTERN.findall(str(cell))
    }

    # Authorized tokens are withheld from the comparison entirely rather than
    # excused after the fact, and the reason is an alignment trap that made 18
    # of the first corpus sweep's 20 findings false positives.
    #
    # The vault links to the author's own posts, so a link's label and its URL
    # slug carry the same words:
    # `[The Architect and the Taxonomy](.../the-architect-and-the-taxonomy)`.
    # With the URL still in the source sequence, SequenceMatcher is free to
    # align the output's surviving label against the SOURCE'S URL words and
    # declare the label itself deleted -- an exactly inverted, and entirely
    # phantom, finding. Dropping authorized tokens first leaves the label only
    # one thing it can align to.
    #
    # This does not weaken the ledger: every withheld token still had to earn a
    # named reason, and table words earn theirs by appearing in the extracted
    # cells rather than by sitting on a table line.
    comparable: list[Token] = []
    reasons: set[str] = set()
    for token in source_tokens:
        reason = _attribute(
            token,
            spans,
            table_lines,
            table_words,
            definition_owners,
            definition_words,
        )
        if reason is None:
            comparable.append(token)
        else:
            reasons.add(reason)

    matcher = SequenceMatcher(
        None,
        [token.word.casefold() for token in comparable],
        output_words,
        # autojunk treats items appearing in more than 1% of a long sequence as
        # noise, which on article-length prose silently drops common words from
        # the match and manufactures phantom deletions. Never enable it here.
        autojunk=False,
    )

    unaccounted: list[Removal] = []
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            run = comparable[i1:i2]
            if run:
                unaccounted.append(
                    Removal(
                        text=" ".join(token.word for token in run),
                        line=run[0].line,
                    )
                )

    return FidelityReport(
        unaccounted=tuple(unaccounted),
        reasons_used=frozenset(reasons),
        source_word_count=len(source_tokens),
        compared_word_count=len(comparable),
    )


def _attribute(
    token: Token,
    spans: Sequence[Span],
    table_lines: frozenset[int],
    table_words: frozenset[str] | set[str],
    definition_owners: Mapping[int, str] = MappingProxyType({}),
    definition_words: Mapping[str, frozenset[str]] = MappingProxyType({}),
) -> str | None:
    """Name the reason this token may be missing, or None if there is none."""
    for span in spans:
        if span.start <= token.start and token.end <= span.end:
            return span.reason

    # Relocated, not vanished: a table word counts as accounted for only when
    # it actually reached the extracted cells. A row that extraction dropped
    # sits on a table line too, and must still be reported.
    if token.line in table_lines and token.word.casefold() in table_words:
        return "table"

    # Also relocated, not vanished, and reconciled for the same reason. Markdown
    # moves every footnote definition to the end of the rendered document, so a
    # definition written mid-source arrives after text that followed it and
    # SequenceMatcher -- which can only align in order -- has no path that keeps
    # both. One of the two runs reads as deleted.
    #
    # Do NOT simplify this into an authorized span in `authorized_spans`. That
    # would excuse a definition by where it sits, and a footnote body the
    # renderer genuinely dropped sits in exactly the same place -- the loss this
    # module exists to catch would become invisible. Withholding is only ever
    # earned by evidence the words arrived, which here is their presence in the
    # rendered `fn:` list item CARRYING THIS DEFINITION'S OWN LABEL. One pooled
    # set across all footnotes would let a sibling sharing the same vocabulary
    # vouch for a body that was dropped outright.
    owner = definition_owners.get(token.line)
    if owner is not None and token.word.casefold() in definition_words.get(
        owner, frozenset()
    ):
        return "footnote_definition"

    return None


def _visible_text(html: str) -> str:
    """The text a reader would see, ignoring head metadata and attributes.

    Only `<body>` is read. The head's `<title>` repeats the article title, and
    counting it would let a genuinely deleted heading look present.
    """
    soup = BeautifulSoup(html, "html.parser")
    root = soup.body if soup.body is not None else soup
    return root.get_text(" ")


def _line_starts(text: str) -> tuple[int, ...]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return tuple(starts)


def _line_of(offset: int, line_starts: Sequence[int]) -> int:
    low, high = 0, len(line_starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if line_starts[mid] <= offset:
            low = mid
        else:
            high = mid - 1
    return low


def _is_fence(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(_FENCE_PREFIXES)


def _table_lines(source: str) -> frozenset[int]:
    """1-based line numbers that look like table rows, matching Token.line."""
    return frozenset(
        index
        for index, line in enumerate(source.split("\n"), start=1)
        if _TABLE_LINE.match(line)
    )


def footnote_definition_labels(source: str) -> dict[int, str]:
    """1-based line number -> the footnote label whose definition owns it.

    A definition runs from its `[^label]:` line through any indented
    continuation lines beneath it, and ends at the first line that is neither.
    A blank line does not end it on its own -- a multi-paragraph footnote is
    legal -- but a blank line followed by unindented prose does, because that
    prose is back in the body.

    The label rides along rather than being discarded because reconciliation is
    per-footnote: pooling every definition's words into one set would let a
    sibling that happens to share vocabulary vouch for a body that was dropped
    outright.

    Fenced code is skipped for the same reason every other check skips it: an
    article that *documents* footnote syntax is correct output, and the words
    inside the fence stay in the body where they were written.

    Pure: returns a new dict, never mutates the input.
    """
    owners: dict[int, str] = {}
    label: str | None = None
    in_fence = False
    pending_blank: list[int] = []

    for index, line in enumerate(source.split("\n"), start=1):
        if _is_fence(line):
            in_fence = not in_fence
            label = None
            pending_blank.clear()
            continue
        if in_fence:
            continue

        definition = _FOOTNOTE_DEFINITION.match(line)
        if definition is not None:
            label = definition.group("label")
            pending_blank.clear()
            owners[index] = label
            continue

        if label is None:
            continue

        if not line.strip():
            # Held, not claimed: a blank line belongs to the definition only if
            # an indented line follows it. Claiming it immediately would let a
            # definition at the end of a paragraph swallow the blank line and
            # then keep going.
            pending_blank.append(index)
            continue

        if _FOOTNOTE_CONTINUATION.match(line):
            for blank in pending_blank:
                owners[blank] = label
            pending_blank.clear()
            owners[index] = label
            continue

        label = None
        pending_blank.clear()

    return owners


def footnote_definition_lines(source: str) -> frozenset[int]:
    """The line numbers of `footnote_definition_labels`, without the labels."""
    return frozenset(footnote_definition_labels(source))


def _footnote_words(html: str) -> dict[str, frozenset[str]]:
    """Casefolded words that reached each rendered footnote, keyed by label.

    Keyed on `id="fn:..."` rather than the extension's `<div class="footnote">`
    wrapper, because `strip_unsupported_elements` removes `div` -- by the time
    the written article.html reaches this module the wrapper is gone and the
    list item ids are the only thing left that names the subtree. The label
    itself survives the id verbatim, including spaces and non-ASCII, so it can
    be matched straight back against the source definition.

    A label absent from this mapping has no words to vouch for it, so its whole
    definition is reported -- which is the correct answer for a footnote the
    renderer dropped.
    """
    soup = BeautifulSoup(html, "html.parser")
    by_label: dict[str, frozenset[str]] = {}
    for item in soup.find_all("li", id=True):
        item_id = str(item.get("id", ""))
        if not item_id.startswith("fn:"):
            continue
        label = item_id[len("fn:"):]
        by_label[label] = frozenset(
            word.casefold() for word in WORD_PATTERN.findall(item.get_text(" "))
        )
    return by_label


def _leading_title_span(source: str, resolved_title: str) -> tuple[int, int] | None:
    """Locate the leading H1 that `strip_duplicate_title` removes.

    Only a heading whose text matches the resolved title is authorized, and
    only before any body prose -- otherwise a mid-article heading that happened
    to repeat the title would excuse its own deletion.

    The scan starts after the frontmatter block rather than skipping lines that
    merely look like delimiters. Walking `---` alone stops at the first
    `tags:` line and gives up, which is how the torture fixture's real title
    was reported lost.
    """
    wanted = _normalized(resolved_title)

    frontmatter = _FRONTMATTER.match(source)
    offset = frontmatter.end() if frontmatter else 0

    for line in source[offset:].split("\n"):
        stripped = line.strip()
        if stripped:
            heading = _HEADING.match(line)
            if heading is None:
                return None
            if _normalized(heading.group("text")) == wanted:
                return (offset, offset + len(line))
            return None
        offset += len(line) + 1
    return None


def _normalized(text: str) -> str:
    return " ".join(WORD_PATTERN.findall(text)).casefold()
