# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/chrisdavidson/obsidian-to-substack/releases/tag/v1.0
