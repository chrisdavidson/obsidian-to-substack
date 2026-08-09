# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-08-09

Checks the other direction. Every release up to now made sure the output was
*valid*; this one makes sure it still contains what you wrote.

The reason is a real defect. On 2026-08-08 a published post carried an inline
aside and a 34-line caption block that had been written as `%%comments%%` — and
the author did not catch it by reading the post. It surfaced by accident, days
later. Then the fix for it turned out to be more dangerous than the defect: its
first cut silently deleted real prose, turning `Growth was 50%% up from 20%%
last year.` into `Growth was 50last year.` A leaked marker is visible. Deleted
text leaves nothing behind to notice, which is why it needs a machine.

### Added

- **Fidelity checking.** Every word of the source must arrive in the output or
  be attributable to a reason the converter can name — frontmatter, the title it
  stripped, a table it turned into an image, a comment it removed, a link target
  that moved into an attribute. Anything else is reported as a `fidelity_loss`
  preflight warning. It runs on every conversion; there is nothing to remember.

  Built as an accounting ledger rather than a diff with an exclusion list, which
  matters most for tables: table prose is *relocated* into the PNG and CSV, not
  vanished, so it reconciles against the extracted cells. A row the extractor
  dropped sits on a table line too, and is still reported.

- **`tools/fidelity_sweep`** — runs the same check across a whole vault at once.
  Reports findings alongside a coverage figure, because the two numbers are only
  meaningful together: every authorised removal withholds words from the
  comparison, so a check that authorised everything would also read clean.

  Baseline across the author's 46-article corpus: **46/46 clean, 0 unaccounted
  removals, 93.8% of source words compared.**

### Changed

- `preflight.check()` takes three new keyword-only arguments — `source_markdown`,
  `resolved_title` and `tables`. All are defaulted and the two-positional-argument
  call shape is unchanged. Omitting `source_markdown` disables the fidelity check
  rather than reporting that the whole document vanished.
- The README now carries a platform note under Requirements: conversion is
  cross-platform, but `--copy` shells out to `xclip` and fails immediately on
  macOS and Windows. Previously you found that out by running it.
- The torture fixture gained a digit-preceded literal percent, so the comment
  path has a standing end-to-end guard. The live corpus contains no `%%` at all,
  which means a corpus sweep alone proves nothing about that path.

### Notes

The fidelity comparator deliberately does **not** call the converter's own
transforms to decide what was legitimately removed. If it did, a bug inside one
of them would be invisible: both sides would delete the same prose and agree,
and the defect above would report clean. It re-derives those rules
independently, and says so at length in the source.

Preflight and fidelity are complementary and neither replaces the other:
preflight catches what leaked, fidelity catches what vanished. When the comment
stripper meets an unbalanced marker it fails closed and removes nothing — so a
private note leaks, preflight fires, and fidelity correctly stays silent.

325 tests pass, up from 284.

## [1.0.0] — 2026-08-09

First public release. Tables, SVG diagrams, images, wikilinks, formatting and
footnotes survive the move from Obsidian into a Substack draft without hand-repair
in the composer.

Every claim here was checked by pasting into a real Substack draft and looking at
the result. Substack has no rendering API, so nothing below is inferred.

### Added

- **Table rendering.** Pipe tables are rendered to PNG with alignment and inline
  styles preserved, plus a CSV sidecar. The placeholder comment that used to reach
  the composer is gone.
- **Diagram and image resolution.** One path for `.svg` and `.png` embeds.
  Percent-encoded names, stale vault-relative prefixes and uncopied raster files
  all resolve.
- **Title hand-off.** A duplicate leading H1 is dropped, the real title is resolved
  and carried into the document head, `metadata.json` and the CLI, then placed on
  the X11 primary selection — one middle-click into Substack's title field.
- **Footnotes**, including the vault's own `[^1] - text` hyphen form, which
  Markdown does not recognise and which previously degraded into literal `[^1]`
  in the post.
- **Obsidian comment stripping.** `%%comment%%` content is removed before
  rendering, so private notes-to-self stay private. Inline pairs and lone-marker
  blocks are both handled; code fences and inline code spans are exempt.
- **Preflight checks.** After each run the tool reports any construct known to
  break in Substack: `duplicate_title`, `footnote_marker_literal`,
  `footnote_section_missing`, `image_too_large`, `image_too_wide`, `missing_image`,
  `obsidian_comment`, `slug_title`, `table_placeholder`, `unreadable_image`.
  Preflight is advisory — it reports, it never rewrites.
- **`tools/substack_diff`** — compares archived pipeline output against published
  posts and regenerates `docs/FINDINGS.md`.

### Fixed

Nine defects were found, fixed and pinned by tests during the v1.0 milestone, plus
three more before this release. Each is recorded in
[`docs/FINDINGS-MANUAL.md`](docs/FINDINGS-MANUAL.md). The most recent:

- Obsidian `%%comment%%` content reached the pasted post as visible prose. There
  was no handler for the syntax at all.
- The comment stripper's first cut could delete real prose in two ways — an
  unclosed marker paired with the next comment's opener, and a literal doubled
  percent in prose (`50%% up from 20%%`) read as a comment. Both now fail closed:
  an odd marker count strips nothing for that document, and a digit-preceded
  marker never opens a comment. Deleted prose is unrecoverable and silent; a
  surviving comment is neither.
- The resolved title could silently fall back to the filename slug. Preflight now
  warns when it does.

### Removed

- **Datawrapper table rendering**, retired on evidence after four empirical runs:
  a worse image at Substack's column width, an extra secret to manage, and an
  external publish on every run. It also never emitted an iframe, which had been
  the entire premise for trying it.

### Known limitations

Recorded rather than absorbed — each was established by hand against a real draft:

- **The title is placed by hand.** Substack never fills its title field from
  pasted body content. `--copy` reduces this to one middle-click; it cannot be
  removed.
- **Image alignment is not controllable.** Substack centres every image itself,
  whatever markup you send.
- **`--copy` is Linux/X11 only** (it shells out to `xclip`), and the title
  hand-off additionally needs a browser that honours middle-click paste of the
  primary selection.

[1.1.0]: https://github.com/chrisdavidson/obsidian-to-substack/releases/tag/v1.1
[1.0.0]: https://github.com/chrisdavidson/obsidian-to-substack/releases/tag/v1.0
