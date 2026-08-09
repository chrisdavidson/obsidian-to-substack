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
from typing import Sequence

from bs4 import BeautifulSoup

# A word is letters, digits and underscores, optionally carrying internal
# apostrophes. Everything else -- every dash, quote, pipe, hash, asterisk and
# bracket -- is invisible to the comparison.
#
# That is what makes the whole comparison robust against `smarty` and the
# ` -- ` em-dash conversion without needing a normalisation pass: source
# `don't`, `"quoted"` and `a -- b` and output `don’t`, `“quoted”` and `a—b`
# tokenize identically. Normalising the strings instead would shift character
# offsets and break span attribution, and would itself be a transform whose
# bugs could hide a real deletion.
WORD_PATTERN = re.compile(r"[0-9A-Za-z_]+(?:['’][0-9A-Za-z_]+)*")

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

_FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---[ \t]*\r?\n", re.DOTALL)
_IMAGE_EMBED = re.compile(r"!\[\[[^\]]*\]\]")
_LINK_TARGET = re.compile(r"\]\(([^)]*)\)")
_FOOTNOTE_MARKER = re.compile(r"\[\^[^\]]+\]")
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

    @property
    def is_clean(self) -> bool:
        return not self.unaccounted

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
            line=_line_of(match.start(), line_starts),
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
        Span(match.start(), match.end(), "footnote_marker")
        for match in _FOOTNOTE_MARKER.finditer(source)
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
    table_words = {
        word.casefold()
        for table in tables
        for row in table
        for cell in row
        for word in WORD_PATTERN.findall(str(cell))
    }

    matcher = SequenceMatcher(
        None,
        [token.word.casefold() for token in source_tokens],
        output_words,
        # autojunk treats items appearing in more than 1% of a long sequence as
        # noise, which on article-length prose silently drops common words from
        # the match and manufactures phantom deletions. Never enable it here.
        autojunk=False,
    )

    unaccounted: list[Removal] = []
    reasons: set[str] = set()
    pending: list[Token] = []

    def flush() -> None:
        if not pending:
            return
        unaccounted.append(
            Removal(text=" ".join(t.word for t in pending), line=pending[0].line)
        )
        pending.clear()

    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for token in source_tokens[i1:i2]:
            reason = _attribute(token, spans, table_lines, table_words)
            if reason is None:
                pending.append(token)
            else:
                reasons.add(reason)
                flush()
        flush()

    return FidelityReport(
        unaccounted=tuple(unaccounted),
        reasons_used=frozenset(reasons),
        source_word_count=len(source_tokens),
    )


def _attribute(
    token: Token,
    spans: Sequence[Span],
    table_lines: frozenset[int],
    table_words: frozenset[str] | set[str],
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
    return frozenset(
        index
        for index, line in enumerate(source.split("\n"))
        if _TABLE_LINE.match(line)
    )


def _leading_title_span(source: str, resolved_title: str) -> tuple[int, int] | None:
    """Locate the leading H1 that `strip_duplicate_title` removes.

    Only a heading whose text matches the resolved title is authorized, and
    only before any body prose -- otherwise a mid-article heading that happened
    to repeat the title would excuse its own deletion.
    """
    wanted = _normalized(resolved_title)
    offset = 0
    for line in source.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("---"):
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
