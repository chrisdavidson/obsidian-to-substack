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
**closed, not deferred**. The code is public; the audience is not. Do not propose packaging,
PyPI or cross-platform work without a named person asking for it.

**Core Value 1 — Transport (satisfied by v1.0):** Tables, SVG diagrams, and charts survive
the move from Obsidian into a Substack post **without manual repair in the composer.**

**Core Value 2 — Integrity (live):** What reaches the composer is what the author wrote —
**nothing added, nothing silently removed.** Named 2026-08-09 on evidence: every defect
found since the v1.0 audit was a content-integrity defect, and one of them (leaked `%%`
comment content) reached a live published post without the author noticing on review.

### Current State

**v1.0 shipped 2026-08-08** — 21/21 requirements, audit passed. The core value is met:
tables, SVG diagrams, images, wikilinks, formatting and footnotes all survive into a
Substack draft, verified by live paste rather than inference. The fix history that once
lived only in the author's memory is now `docs/FINDINGS-MANUAL.md`, regenerated into
`docs/FINDINGS.md` by `tools/substack_diff`.

No milestone is active, and none is warranted — the 2026-08-09 altitude check pruned the
Backlog to a single live item (a source-to-output fidelity diff, `/gsd-quick`-sized).
**Quick tasks, not the phase pipeline, is now a recorded decision**, not an accident:
`.planning/phases/` will not exist and audits verify from primary evidence.

Three limitations are recorded rather than absorbed: the title is placed by hand (Substack
never fills its title field from pasted body content), image alignment is not controllable
(Substack centres every image itself), and `--copy` is Linux/X11 only.

### Constraints

- **Tech stack**: Python ≥3.11; CairoSVG, Pillow, Markdown, BeautifulSoup4, PyYAML —
  established and working, no reason to churn it

- **Verification**: split — do not restate this as blanket "unautomatable." Substack's
  *rendering* has no API, so any rendering question needs the author to paste and report.
  The pipeline's *own output fidelity* is mechanically checkable, and most of the defect
  history lived there — literal `[^1]` markers, placeholder comments, unresolved image
  paths, leaked `%%` comments, inline HTML drawn into PNGs were all visible in
  `article.html`. Reach for the cheap mechanical check first

- **Platform**: `--copy` shells out to `xclip`, so clipboard support is Linux/X11 only. The
  audience is one person, so this stands — but the 2026-08-09 public release means a
  non-Linux downloader can now reach the failure, so the README carries a platform note.
  Accepted failure mode, recorded rather than fixed

- **Secrets**: `*.key` is gitignored

- **Planning artifacts**: `.planning/` is gitignored by deliberate choice — this repo is
  headed to GitHub and planning is local workflow state. GSD commit steps on planning
  files are expected no-ops.

- **Testing**: 284 tests currently pass (`uv run pytest -q`); new defects get pinned by
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

External surfaces: `xclip` for `--copy` (Linux/X11 only — body to CLIPBOARD as
`text/html`, resolved title to PRIMARY); the Obsidian vault, read-only and outside the
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

**Preflight is advisory, never corrective.** `preflight.check(html, base_dir)` returns
`Warning_(check, requirement, message)` and changes nothing — it is the other half of every
narrow transformation. Current checks: `duplicate_title`, `footnote_marker_literal`,
`footnote_section_missing`, `image_too_large`, `image_too_wide`, `missing_image`,
`obsidian_comment`, `slug_title`, `table_placeholder`, `unreadable_image`.

**`fidelity.py` is the other axis, and it is not part of the pipeline.** Preflight asks
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

`tools/fidelity_sweep` runs it across the corpus. Baseline 2026-08-09: **46/46 clean, 0
unaccounted removals, 93.8% word coverage.** Always quote the coverage beside the zero —
every authorized span withholds words, so a check that authorized everything reads clean
too. The corpus currently contains no `%%` at all, so a corpus-wide probe proves nothing
about the comment path; validate that one by injecting a trigger into a temp copy.

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
