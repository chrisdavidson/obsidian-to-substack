<!-- GSD:project-start source:PROJECT.md -->

## Project

**obsidian-to-substack**

A Python CLI that converts Obsidian Markdown articles into Substack-ready HTML. Prose
moves from Obsidian to Substack fine by hand; everything else doesn't — tables lose their
structure, SVG diagrams aren't supported at all, and Obsidian's `![[embed]]` and
`[[wikilink]]` syntax means nothing to Substack's composer. The tool handles that payload.

It serves its author, publishing to <https://foxglenacres.substack.com> from
`~/Obsidian/BrainBank/4_Archive/Published Articles`. It serves exactly one person, and as
of 2026-08-09 that is a decision rather than a stage — release to other Obsidian writers is
**closed, not deferred**. The code is public; the audience is not. Do not propose packaging
or PyPI work without a named person asking for it. **Cross-platform `--copy` was re-entered
on 2026-08-10** — the author asked for macOS and Windows in those words, which is exactly
the named-person condition this rule sets. The gate worked as designed; it is not a licence
to reopen the rest.

**Core Value 1 — Transport (satisfied by v1.0):** Tables, SVG diagrams, and charts survive
the move from Obsidian into a Substack post **without manual repair in the composer.**

**Core Value 2 — Integrity (live):** What reaches the composer is what the author wrote —
**nothing added, nothing silently removed.** Named 2026-08-09 on evidence: every defect
found since the v1.0 audit was a content-integrity defect, and one of them (leaked `%%`
comment content) reached a live published post without the author noticing on review.

### Current State

**v1.3.1 shipped 2026-08-11**, the current release. Five public releases so far, each one
tagged with a wheel and sdist attached, none of them on PyPI:

- **v1.0 (2026-08-08)** — 21/21 requirements, audit passed. Core Value 1 met: tables, SVG
  diagrams, images, wikilinks, formatting and footnotes all survive into a Substack draft,
  verified by live paste rather than inference.
- **v1.1 (2026-08-09)** — Core Value 2 gets a default-on guard, the `fidelity_loss`
  preflight check. Its original baseline (46/46 clean, 93.8% coverage) was restated
  2026-08-11 once the corpus was defined: **43/43 clean, 93.0%, 5 skipped.**
- **v1.2 (2026-08-10)** — the gate. A run that knows its output is broken can no longer
  end by reporting success: `--copy` refuses on any preflight warning, `--force` is the
  stated escape hatch.
- **v1.3 (2026-08-10)** — `--copy` reaches macOS and Windows. See the Platform constraint
  below before describing either as working.
- **v1.3.1 (2026-08-11)** — `png_files` names every image the run writes. The rendered
  table PNGs were written and referenced but reported nowhere; a Core Value 2 defect in
  the reporting surface, found from the consumer side because preflight's `missing_image`
  only fires for a src *absent* from the output directory. First three-part tag.

The fix history that once lived only in the author's memory is `docs/FINDINGS-MANUAL.md`,
regenerated into `docs/FINDINGS.md` by `tools/substack_diff`.

No milestone is active and none is coming. **Standing maintenance is a recorded decision as
of 2026-08-11**, not a lull: the vault is an interface the author edits for unrelated
reasons, so defects arrive on a schedule no roadmap controls. Separately, **quick tasks, not
the phase pipeline, is also a recorded decision** — `.planning/phases/` will not exist and
audits verify from primary evidence. What would change either is evidence — a report from a
macOS or Windows user, a defect in a live paste — not planning. One live backlog item exists
(define the fidelity corpus); it is maintenance work with a decision attached.

**The 2026-08-11 altitude check returned PAUSE, and it is open.** Nothing has been published
through the pipeline since v1.2, while v1.2, v1.3 and v1.3.1 all shipped. Every genuine
defect in this project's history was found by a live paste or a real run, so Core Value 2's
claim currently rests on fixtures and a corpus sweep with a known-wrong denominator. It lifts
when a real article goes through and the author records whether the composer needed touching.
Take small maintenance work if asked; do not cut another release against it without saying
this out loud.

Three limitations are recorded rather than absorbed: the title is placed by hand (Substack
never fills its title field from pasted body content), image alignment is not controllable
(Substack centres every image itself), and the macOS/Windows `--copy` backends are
unverified on their target platforms.

**A standing pattern worth knowing before you change a code path:** the tool's
self-description does not travel with it. `__version__` sat at `1.0.0` through two
releases, and a help string has now gone stale twice — `--svg-dir` at `96ff451`,
`--copy` at v1.3. Nothing in the suite asserts on either, by choice.

### Constraints

- **Tech stack**: Python ≥3.11; CairoSVG, Pillow, Markdown, BeautifulSoup4, PyYAML —
  established and working, no reason to churn it

- **Verification**: split — do not restate this as blanket "unautomatable." Substack's
  *rendering* has no API, so any rendering question needs the author to paste and report.
  The pipeline's *own output fidelity* is mechanically checkable, and most of the defect
  history lived there — literal `[^1]` markers, placeholder comments, unresolved image
  paths, leaked `%%` comments, inline HTML drawn into PNGs were all visible in
  `article.html`. Reach for the cheap mechanical check first

- **Platform**: `--copy` dispatches per platform in `clipboard.py` — `xclip` on Linux/X11,
  `osascript` on macOS, PowerShell CF_HTML on Windows (2026-08-10, author's request).
  **Only the Linux path is verified.** The other two have never run on their target
  platforms; the author has neither machine, so unlike Substack's rendering there is no
  human who can settle them. Their tests prove the right bytes reach the right tool and
  nothing more — do not describe them as working. The title hand-off stays Linux-only by
  design: macOS and Windows have one clipboard and it holds the body. **Do not extend these
  backends** (decided 2026-08-11): shipping them was the named-person gate working, but
  building further on permanently unverifiable code is that gate lapsing. Re-opens on a
  report from someone who runs one

- **Vault as a changing interface**: the vault is not a fixed input. DIAG-02 was the author
  reorganizing their own vault into per-article `svg/<slug>/` subdirectories and the tool
  breaking as a consequence — not a coding error. Assume layout assumptions rot, and put
  them in a preflight check rather than a comment

- **Secrets**: `*.key` is gitignored

- **Planning artifacts**: `.planning/` is gitignored by deliberate choice — this repo is
  headed to GitHub and planning is local workflow state. GSD commit steps on planning
  files are expected no-ops.

- **Testing**: 406 tests currently pass (`uv run pytest -q`); new defects get pinned by
  tests, per the author's "fixes + automated guards" decision. This count goes stale —
  run the suite rather than trusting the number.

- **Vault content**: article prose never enters this repo; tests use synthetic fixtures.
  The vault is also unversioned — never bulk-write to it.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->

## Technology Stack

**Python ≥3.11.** CairoSVG (SVG→PNG), Pillow (PNG validation, table images), Markdown
(extensions: `tables`, `footnotes`, `fenced_code`, `smarty`), BeautifulSoup4 (HTML
post-processing and every preflight check), PyYAML (frontmatter). Dev: pytest ≥8.0,
pytest-cov. No linter or formatter is wired in — match the surrounding style by hand.

`render_html.strip_unsupported_elements` removes exactly `{div, u, script}` — narrow on
purpose, after a past defect where a wider strip ate the footnotes subtree.

**Run everything through `uv`** — there is no bare `python` on this machine:

```bash
uv run pytest -q                                  # the suite
uv run python -m obsidian_to_substack.convert <dir> [--file X.md] [--output-dir …]
uv run python -m tools.substack_diff --all        # regenerate docs/FINDINGS.md
uv run python -m tools.fidelity_sweep [--show]    # corpus fidelity census
```

External surfaces: the clipboard, via one native tool per platform (`xclip` on Linux —
body to CLIPBOARD as `text/html`, resolved title to PRIMARY; `osascript` on macOS;
PowerShell on Windows, both body-only); the Obsidian vault, read-only and outside the
repo; and Substack itself, which has **no API for rendering checks** — that is the binding
constraint on the whole project.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Observed in the codebase and its history, not aspirations. Full detail in
`.planning/CONVENTIONS.md`.

**The test lands first.** The commit history is a `test:` commit that fails, then a
`feat:`/`fix:` commit that makes it pass. Do not merge the two. Conventional types in use:
`docs`, `test`, `feat`, `fix`, `refactor`, `chore`. No attribution trailer. A defect is not
fixed until it is pinned by a unit test, a preflight check, or the torture fixture.

**Fail closed, and be loud.** The recurring rule across `obsidian_syntax.py` and
`preflight.py`: a transformation that cannot be certain does nothing and lets preflight
report it. Mangled or deleted prose is unrecoverable and leaves nothing to warn about; an
untransformed construct is recoverable and visible. So transformations are deliberately
narrow and refuse ambiguous input — `normalize_footnote_definitions` only rewrites labels
referenced elsewhere, `strip_obsidian_comments` bails entirely on an unbalanced marker
count and never reads a digit-preceded `%%` as an opener, `_check_slug_title` fires only on
a measured condition. **Do not generalize any of them.** Each carries an in-code comment
saying what regresses if you do.

Where a transform and a check make the same judgement, they share the rule and say so —
change one and you must change the other. Preflight checks skip `code`/`pre` parents and
HTML `Comment` nodes, because an article that *documents* a syntax is correct output.

**Comments explain why.** Long explanatory comments are the house style and they earn their
length: which ordering is load-bearing, which narrowness is intentional. When you make a
call a later reader would plausibly undo, say so in the code.

**Purity.** Transformations take a string and return a new one; nothing is mutated in
place. Several modules carry a `test_pure_function_no_mutation` test — add one with any new
transformation. Type-annotate every signature.

**`docs/FINDINGS.md` is generated.** Edit `docs/FINDINGS-MANUAL.md` and regenerate via
`tools/substack_diff`. If the vault is unreachable, leave the generated file alone and say
so rather than hand-editing it.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

One package, `src/obsidian_to_substack/`, ~2,400 lines across eleven focused modules.
`convert.py` is the orchestrator and CLI; everything else is a transformation it calls in
sequence. Full detail in `.planning/ARCHITECTURE.md`.

**The pipeline order is load-bearing** — several past defects were ordering bugs, not logic
bugs. `convert_article()` runs: frontmatter split → title resolution (authored H1 wins,
else the filename slug, with `title_from_slug` passed to preflight because the rendered
`<title>` looks identical either way) → `export_all_svgs` + `validate_png` →
`copy_raster_embeds` + `rewrite_image_refs` → `extract_tables` +
`replace_tables_with_images` → `transform_obsidian_syntax` → `render_to_html` →
`strip_duplicate_title` → `wrap_html` → `strip_unsupported_elements` → write
`article.html`/`metadata.json` → `preflight.check` on the written HTML → optional `--copy`.

Two ordering hazards, both commented in-code — read the comments before reordering:

- **Inside `transform_obsidian_syntax()`**: strip comments → normalize footnotes → embeds →
  wikilinks → em dashes. Comment stripping must be first, or a footnote label appearing
  only inside a comment licenses a definition that should not survive, and embeds inside a
  comment become real `<img>` tags. Footnote normalization must precede em-dash conversion,
  which destroys the ` -- ` separator the footnote pattern keys on.
- **Across `convert.py`**: raster copying and table extraction run *before*
  `transform_obsidian_syntax`, so an embed or table inside a comment still rasterizes to
  disk. It never reaches the pasted HTML, but it leaves orphan files. Accepted and recorded.

**Preflight is advisory, never corrective.** `preflight.check(html, base_dir, *,
title_from_slug, source_markdown, resolved_title, tables)` returns
`Warning_(check, requirement, message)` and changes nothing — it is the other half of every
narrow transformation. Everything after `base_dir` is keyword-only and defaulted, so the
two-positional-arg shape still works. Current checks: `duplicate_title`, `fidelity_loss`,
`footnote_marker_literal`, `footnote_section_missing`, `image_too_large`, `image_too_wide`,
`missing_image`, `obsidian_comment`, `slug_title`, `table_placeholder`, `unreadable_image`.

`fidelity_loss` is gated on `source_markdown` — omit it and the check is inert, because
without the source there is nothing to compare and reporting that the whole document
vanished would be worse than reporting nothing. It emits **one warning per document**, not
one per lost run: the corpus sweep's first pass had 18 of 20 findings sharing a root cause.

**`fidelity.py` is the other axis.** Preflight asks
whether the output is valid; `fidelity.compare(source_md, html, ...)` asks whether the
output still contains what the author wrote. It is an accounting ledger — every removed run
must be attributable to a named reason whose evidence is held in hand (frontmatter, the
resolved title, the extracted table cells, a comment span), and anything left over is
reported. Tables are *reconciled* against `extract_tables`' cells rather than excused by
sitting on a table line, because a dropped row sits on one too.

**It must never call the pipeline's transforms**, and the module says so at length. Calling
`strip_obsidian_comments` to decide what was legitimately removed makes a bug inside it
invisible by construction — both sides delete the same prose and agree. So `comment_spans`
re-derives the rule from scratch. This is a *considered departure* from the convention two
paragraphs up: sharing is right for preflight, which inspects output for surviving markers
and where sharing prevents false positives; it is wrong here, where the subject is what was
deleted and sharing produces false negatives. Do not tidy it by importing the shared
constant.

The two checks are complementary and neither replaces the other — **preflight catches what
leaked, fidelity catches what vanished.** With an odd marker count the stripper fails closed
and strips nothing, so a comment leaks (loudly, into preflight) while fidelity correctly
reports clean.

**There is a third axis and nothing guards it: what was written but never reported.** Both
checks above inspect *content* — the HTML and the source text. `convert_article` also returns
a manifest (`png_files`, `svg_count`, `table_count`, `metadata.json`), and v1.3.1 fixed a case
where that manifest had been wrong for four releases: the rendered table PNGs were written to
disk and referenced by the body and named by nothing. `missing_image` could not see it by
construction — it fires on a src *absent* from the output directory, and these were present.
It surfaced only because a downstream repo consumed the manifest and built a bundle
referencing images it never copied.

So: **the result dict is a self-description with no ledger behind it**, and the one part of
it anyone has checked turned out to be wrong. If you change what the pipeline writes, check
what it *says* it wrote. `convert.py:259`'s comment asserted the fixed behaviour since before
it was true, which is how this stayed unexamined.

**The library API is not a supported surface** (decided 2026-08-11). A second repo,
`article-workflow`, consumes `convert_article`'s result dict via an editable path dependency.
The clipboard remains the real publishing path, so the result dict carries no compatibility
promise and that repo tracks it at its own risk — but know it exists before you change a
return shape, because the guards above will not tell you.

It runs on every conversion, via `preflight`'s `fidelity_loss` check —
`convert_article` hands it the **raw file text** (not `body`, which by then has been through
frontmatter splitting and image rewriting, so comparing against it would exempt whatever
those stages dropped) plus the table rows captured before `replace_tables_with_images`
consumed them.

`tools/fidelity_sweep` runs it across the corpus. Baseline 2026-08-11: **43/43 clean, 0
unaccounted removals, 93.0% word coverage, 5 files skipped.** Always quote the coverage
beside the zero — every authorized span withholds words, so a check that authorized
everything reads clean too. The corpus currently contains no `%%` at all, so a corpus-wide
probe proves nothing about the comment path; validate that one by injecting a trigger into a
temp copy.

**The corpus is defined by frontmatter presence**, not by file extension (`260811-crp`).
The previous baseline — 46/46 at 93.8% — was measured over a set selected by `rglob("*.md")`
that included companion LinkedIn promo posts, so its denominator was never the set of things
this tool converts. Coverage moved 93.8% → 93.0% because the companions are short and
header-less and were inflating it.

The first run of the rule skipped **six** files, one of which — `Data, Information,
Knowledge, and Wisdom one data source at a time.md`, 2,344 words — was a genuine article that
simply had no header. It got a `title:` block in the vault the same day (per VAULT-CONVENTIONS:
`title:` is reserved for notes opening at `##` with no H1, which is exactly that file), which
re-admitted it and took the census to 43/43. **All five remaining skips are LinkedIn companion
posts**, so the corpus is now exactly the set of real articles.

**Read the skipped list on every run.** That casualty was found by reading it and by nothing
else — the census total showed a tidy `42/42 clean` either way. It is the reason the list is
printed per file rather than counted.

**The pipeline and Obsidian disagree about which embeds resolve** — a known divergence,
recorded rather than fixed. Obsidian resolves `![[embed]]` vault-wide including the central
attachment folder; `search_dirs` covers the article directory and the resolved SVG directory
only. The corpus's five `missing_image` warnings are all this, and every referenced file
exists. Read that warning as "this pipeline cannot see your attachment folder," not as "the
file is missing."

`tests/fixtures/torture_test/` is one synthetic article carrying every construct that has
ever broken. Adding to it is the cheapest end-to-end guard available.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
