"""Transform Obsidian-specific Markdown syntax to standard HTML-compatible form."""

import os
import re

IMAGE_EMBED_PATTERN = re.compile(
    r"!\[\[([^\]|]+?)(?:\s*\|\s*([^\]]*?))?\]\]"
)

INTERNAL_LINK_PATTERN = re.compile(
    r"(?<!!)\[\[([^\]]+?)\]\]"
)

EM_DASH_PATTERN = re.compile(r" -- ")

# The author's vault writes footnote definitions as `[^1] - text` (a hyphen,
# en dash, em dash, or double hyphen separator) where python-markdown's
# footnotes extension requires `[^1]: text` (a colon). Longest-first
# alternation matters: with "-" tried before "--", "[^1] -- text" would match
# only the first hyphen and leave a stray "-" glued to the definition text.
FOOTNOTE_DEF_PATTERN = re.compile(
    r"^\[\^(?P<label>[^\]]+)\](?P<pre_ws>\s*)(?P<sep>--|—|–|-)(?P<post_ws>\s+)(?P<def_text>.*)$"
)
FOOTNOTE_REF_PATTERN = re.compile(r"\[\^([^\]]+)\]")

# The vault's private notes-to-self, written as `%%comment%%`. Only two
# shapes are handled: a same-line inline pair, and a block whose opening
# and closing markers each sit alone on their own line. A marker that opens
# mid-line and closes lines later is legal Obsidian but is not observed in
# the corpus and is deliberately out of scope -- see strip_obsidian_comments'
# docstring for why a narrow, occasionally-inert stripper beats a general
# one here.
OBSIDIAN_COMMENT_MARKER = "%%"

# Alternation order matters: the code-span alternative is tried FIRST, so a
# code span consumes its own markers before the comment alternative can see
# them (`Use `%% note %%` for asides.` must survive untouched). The comment
# alternative is a lazy, non-DOTALL match, so it can never cross a newline
# or span past the nearest closing marker on the same line -- a lone
# unmatched marker on a line simply fails to match. Trailing horizontal
# whitespace after the closing marker is consumed (but leading whitespace
# before the opening marker is not), which is what keeps
# "%% note %%    Text" from becoming a four-space indented code block while
# leaving list indentation at the start of a line untouched.
#
# A marker preceded by a DIGIT never opens a comment. A doubled percent is
# legal prose ("Growth was 50%% up from 20%% last year."), and without this
# guard the two literals read as one comment and " up from 20" is deleted
# outright -- silent prose loss, with nothing surviving for preflight to
# warn about.
#
# The guard is a digit lookbehind and not a whitespace requirement on
# purpose. Requiring whitespace before the opener looks safer but silently
# stops stripping every comment glued to a full stop, a blockquote ">", an
# em dash, a bracket or a word -- all ordinary in the vault's prose, and all
# cases where the comment would then ship. Only the digit case is a real
# ambiguity, so only the digit case is rejected.
INLINE_COMMENT_PATTERN = re.compile(
    r"(?P<code>`+[^`]*`+)|(?P<comment>(?<![0-9])%%.*?%%[ \t]*)"
)


def replace_image_embeds(
    text: str,
    image_map: dict[str, str] | None = None,
) -> str:
    """Replace ![[file.ext | modifier]] with HTML figure/img tags.

    If image_map is provided, SVG filenames are resolved to their PNG paths.
    """
    if image_map is None:
        image_map = {}

    def _replace(match: re.Match) -> str:
        filename = match.group(1).strip()
        modifier = (match.group(2) or "").strip().lower()

        raw_src = image_map.get(filename, filename)
        if filename.lower().endswith(".svg") and filename not in image_map:
            png_name = re.sub(r"\.svg$", ".png", filename, flags=re.IGNORECASE)
            raw_src = image_map.get(png_name, png_name)
        src = os.path.basename(raw_src)

        alt_text = re.sub(r"\.\w+$", "", filename).replace("-", " ").replace("_", " ")

        if modifier == "center":
            return f'<figure style="text-align: center;"><img src="{src}" alt="{alt_text}"></figure>'
        return f'<img src="{src}" alt="{alt_text}">'

    return IMAGE_EMBED_PATTERN.sub(_replace, text)


def replace_internal_links(text: str) -> str:
    """Replace [[Note Name]] with *Note Name* (italic text)."""
    return INTERNAL_LINK_PATTERN.sub(r"*\1*", text)


def convert_em_dashes(text: str) -> str:
    """Replace ' -- ' with Unicode em dash."""
    return EM_DASH_PATTERN.sub("\u2014", text)


def _is_fence_delimiter(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _is_bare_comment_marker(line: str) -> bool:
    return line.strip() == OBSIDIAN_COMMENT_MARKER


def _replace_inline_comment(match: re.Match) -> str:
    code = match.group("code")
    if code is not None:
        return code
    return ""


def strip_obsidian_comments(text: str) -> str:
    """Remove Obsidian %%comment%% content from the raw Markdown.

    Only two shapes are handled, both observed in a real converted article:
    a same-line inline pair, and a block delimited by a marker alone on its
    own line at each end (whose body may itself contain blank lines, which
    is why this has to run on raw Markdown before rendering -- by the time
    there is HTML the block has already been split into several separate
    paragraph elements with nothing left to identify them as one unit).

    A general "opener anywhere, closer anywhere later" scanner would turn
    two stray, unrelated markers in ordinary prose into the silent deletion
    of everything between them. This narrow pair of shapes fails the other
    way instead: an unhandled or unbalanced marker survives in the output
    and preflight's check on the rendered HTML fires loudly. Inert-and-noisy
    beats silent-and-destructive, so do not "improve" this into a general
    scanner.

    Two fail-safes enforce that asymmetry, and both are load-bearing:

    * An odd number of lone-marker lines means some comment is unclosed.
      Rather than pair positionally and risk pairing an unclosed opener
      with the next comment's opener -- deleting the prose between them --
      the block pass strips nothing at all for that document.
    * A marker preceded by a digit never opens a comment, so a doubled
      percent in ordinary prose ("50%% up from 20%%") is not read as one.
      The guard is deliberately just the digit case: requiring whitespace
      before the opener would stop stripping comments glued to a full
      stop, a blockquote marker, an em dash or a word, and ship them.

    In both cases the markers survive into the rendered HTML, where
    preflight's `_check_obsidian_comments` reports them. Deleted prose is
    unrecoverable and silent; a surviving comment is neither.

    Two passes over `text.split("\\n")`, block first so an outer block wins
    over anything inline inside it. Pure -- builds and returns a new
    string, never mutates the input.
    """
    lines = text.split("\n")

    # Pass one: block form. Walk the lines tracking fenced state (the same
    # `_is_fence_delimiter` + toggling `in_fence` idiom used below in
    # normalize_footnote_definitions) and collect the indices of every line
    # outside a fence whose stripped content is exactly the bare marker.
    # Pair those indices in document order -- first with second, third with
    # fourth -- and mark every line in each inclusive range for removal.
    marker_indices: list[int] = []
    in_fence = False
    for index, line in enumerate(lines):
        if _is_fence_delimiter(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _is_bare_comment_marker(line):
            marker_indices.append(index)

    remove: set[int] = set()
    # An odd marker count means at least one comment is unclosed, and which
    # one is the stray is unknowable from the text. Pairing positionally
    # from the top would pair an unclosed opener with the NEXT comment's
    # opening marker and delete the real prose sitting between them. So the
    # whole block pass bails on an odd count: nothing is removed and every
    # marker survives for preflight to report.
    #
    # This is the block half of the fail-safe, and it is deliberately
    # asymmetric. Deleted prose is unrecoverable and leaves nothing behind
    # to warn about; a surviving comment is recoverable and is loud. Do not
    # "improve" this into a best-effort partial strip.
    if len(marker_indices) % 2 == 0:
        for start, end in zip(marker_indices[0::2], marker_indices[1::2]):
            remove.update(range(start, end + 1))

    block_stripped = [line for index, line in enumerate(lines) if index not in remove]

    # Pass two: inline form. For each surviving line, still tracking fenced
    # state, skip fenced lines verbatim -- fenced content is never touched
    # by either pass.
    result_lines: list[str] = []
    in_fence = False
    for line in block_stripped:
        if _is_fence_delimiter(line):
            in_fence = not in_fence
            result_lines.append(line)
            continue
        if in_fence:
            result_lines.append(line)
            continue

        substituted, count = INLINE_COMMENT_PATTERN.subn(_replace_inline_comment, line)
        if count == 0:
            result_lines.append(line)
            continue

        # Only rstrip a line the substitution actually changed -- an
        # untouched line keeps a trailing markdown two-space hard line
        # break intact.
        stripped = substituted.rstrip()
        if line.strip() and not stripped:
            # A line that was non-blank before and is whitespace-only after
            # is dropped entirely rather than emitted as a blank line -- a
            # blank line here would split a lazy-continuation paragraph in
            # two.
            continue
        result_lines.append(stripped)

    return "\n".join(result_lines)


def normalize_footnote_definitions(text: str) -> str:
    """Rewrite the author's hyphen-form footnote definitions to colon form.

    The vault writes `[^1] - text` (hyphen, en dash, em dash, or double
    hyphen); python-markdown's footnotes extension only matches `[^1]: text`
    (colon), so the hyphen form degrades to plain text rather than erroring
    (F1). Rewriting is gated on the label being referenced elsewhere in the
    document \u2014 a bare `[^foo] - bar` mid-document, with nothing else pointing
    at `foo`, is not a definition, and its own leading `[^foo]` does not
    count as the reference that licenses it (that would make every
    definition self-license).

    Two passes over the document's lines, both tracking fenced-code state
    with a single toggling boolean: pass one collects referenced labels
    (skipping fenced regions and each definition line's own marker), pass
    two rewrites definition-shaped lines whose label was collected. A
    footnote-shaped line inside a fenced block, and an already-canonical
    `[^1]: text` line (the colon is not in the separator class, so it never
    matches), are both returned byte-identical.

    Pure: returns a new string, never mutates the input.
    """
    lines = text.split("\n")

    referenced_labels: set[str] = set()
    in_fence = False
    for line in lines:
        if _is_fence_delimiter(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        def_match = FOOTNOTE_DEF_PATTERN.match(line)
        exclude_span = (0, def_match.start("pre_ws")) if def_match else None
        for ref_match in FOOTNOTE_REF_PATTERN.finditer(line):
            if exclude_span is not None and ref_match.span() == exclude_span:
                continue
            referenced_labels.add(ref_match.group(1))

    result_lines: list[str] = []
    in_fence = False
    for line in lines:
        if _is_fence_delimiter(line):
            in_fence = not in_fence
            result_lines.append(line)
            continue
        if in_fence:
            result_lines.append(line)
            continue

        def_match = FOOTNOTE_DEF_PATTERN.match(line)
        if def_match and def_match.group("label") in referenced_labels:
            result_lines.append(
                f"[^{def_match.group('label')}]: {def_match.group('def_text')}"
            )
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def transform_obsidian_syntax(
    text: str,
    image_map: dict[str, str] | None = None,
) -> str:
    """Apply all Obsidian-specific syntax transformations.

    Returns a new string; the input is not mutated.
    """
    # Comment stripping runs FIRST, ahead of everything else: a footnote
    # label appearing only inside a comment would otherwise be collected by
    # normalize_footnote_definitions as a live reference and license a
    # definition that should not survive, and an embed or link written
    # inside a comment must never be transformed into markup at all.
    # Reordering this call silently re-breaks both of those cases.
    result = strip_obsidian_comments(text)

    # Footnote normalization runs next: convert_em_dashes rewrites a spaced
    # double hyphen into a bare em dash with no surrounding spaces, which
    # would destroy the " -- " separator normalize_footnote_definitions
    # keys on (F5). Reordering this call silently re-breaks hyphen-form
    # footnotes — do not move it.
    result = normalize_footnote_definitions(result)
    result = replace_image_embeds(result, image_map)
    result = replace_internal_links(result)
    result = convert_em_dashes(result)
    return result
