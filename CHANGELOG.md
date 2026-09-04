# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.3] — 2026-09-03

The PAUSE is lifted. **No code changed in this release** — it records a
verification, which for this project is the thing that has always been scarce.

### The evidence

The 2026-08-11 altitude check returned PAUSE and had stayed open through five
releases. Its terms were specific: it lifts when a real article goes through the
pipeline and the author records whether the composer needed touching.

On 2026-09-03 that happened. *Proactively manage regression(s)* — selected by
sweeping the published-articles folder for an article that converts with **zero
preflight warnings** and contains a table — was converted, copied to the
clipboard, and pasted into a Substack draft. It **needed no modification in the
composer.**

That matters more than a passing suite. Every genuine defect in this project's
history was found by a live paste or a real run, and the two fixed earlier the
same day make the point: the Wayland hang was found by running the tool, and the
font fallback by *looking at a rendered table*. Both were invisible to all 438
tests. Core Value 2's claim no longer rests only on fixtures and a corpus sweep,
and Core Value 1 is confirmed on the same evidence — the article carried a 13x5
table that survived as an image without repair.

### Also on the record from that day

- **The v1.2 gate proved itself unprompted.** During the sweep it refused
  `equipment-qualification-taxonomy` on a `slug_title` warning without being
  asked to. That is the gate working in the wild rather than in a test.
- **v1.4.1 and v1.4.2 were cut while the PAUSE was still open**, knowingly and
  at the author's direction after it was surfaced. A decision, on the record.

### Changed

- **`CLAUDE.md` describes the project as it currently is.** It had called v1.3.1
  the current release through three further releases — the same
  self-description-goes-stale pattern the file itself warns about two sections
  lower. Corrected against measured values: the release list now runs to v1.4.2,
  the test count 406 -> 438, the module count eleven -> twelve, ~2,400 lines ->
  ~3,900. The documented test command was `uv run pytest -q`, which **fails to
  spawn** — there is no bare `pytest` on this machine; it is now
  `uv run --extra dev pytest -q`. The GSD entry points named `/gsd-*` where this
  install uses `/bm:*`. A backlog item closed on 2026-08-11 was still listed as
  live.

- **One standing pattern added**, earned twice in one day: *an assumption about
  the machine is a defect waiting for a different machine.* Hardcoded font paths
  were one distribution's layout; seven tests read the host's display server.
  Both passed everywhere they had been run and failed the moment the environment
  changed. Ask the system, or neutralize it — do not encode one machine's answer.

### Still open

Tables published **before v1.4.2** may carry replacement boxes wherever the
source used U+2011 or another glyph the bitmap default lacks —
`equipment-qualification-taxonomy` alone has 27. Nothing in the pipeline can
detect this after the fact, and the 2026-09-03 paste does not settle it: that
check is about the back catalogue, not a fresh conversion.

## [1.4.2] — 2026-09-03

Table images are rendered in a real typeface again.

`table_render.FONT_CANDIDATES` is Debian's font layout plus one macOS path.
Arch keeps the same Liberation faces in `/usr/share/fonts/liberation/` rather
than `/usr/share/fonts/truetype/liberation/`, so every candidate missed, all
four style variants fell to `ImageFont.load_default()`, and tables were
published in Pillow's bitmap face on a machine with 798 fonts installed.

**This was not cosmetic.** One bitmap font served all four styles, so a bold
header row was not bold — and `load_default()` has no glyph for U+2011
NON-BREAKING HYPHEN, which the corpus uses. A real published article rendered
`Off‑the‑shelf`, `Non‑configurable`, `AI‑driven` and `End‑to‑end` as
replacement boxes. Characters the author wrote did not reach the reader, which
makes this a Core Value 2 failure sitting inside a Core Value 1 one.

`FontSet` had no test coverage at all, which is how the assumption went
unexamined for seven releases.

### Fixed

- **Fonts are resolved by asking fontconfig, not by guessing paths.** The order
  is cheapest first: the known paths, then `fc-match` for DejaVu and Liberation
  by name, then `fc-match` for whatever the machine calls `sans-serif`, then the
  bitmap default. Layouts that already worked still cost no subprocess.

  `fc-match` always answers — handed a family nobody has installed it returns a
  substitute rather than nothing — so the reply is checked against the request.
  Without that the first name in `FONT_FAMILIES` appears to win everywhere and
  the preference order means nothing. Non-TrueType matches are refused before
  Pillow can raise on them, and every failure path degrades rather than throws:
  a table in a plainer font is a degraded article, an exception there is a lost
  one.

- **The bitmap warning survives as the loud last resort**, now fired once per
  run rather than once per style variant, and naming what to install.

### Changed

- **The torture fixture carries a U+2011**, with a test pinning that it stays.
  It is the construct that made this defect visible, and without it every font
  test still passes while proving nothing about the case that actually shipped.

### Technical Details

- New `_fc_match(pattern, *, require_family=None)`; `FontSet._load` takes the
  style so each variant is queried with its own fontconfig pattern bits. A bold
  cell rendered in the regular face is a silent fidelity loss of exactly the
  kind this project keeps finding.
- Verified by rendering, not inference. On `equipment-qualification-taxonomy.md`
  from the published-articles folder: 4 fallback warnings and a 1358×319 table
  before, 0 warnings and a correct 2804×748 one after, with the non-breaking
  hyphens rendering as hyphens.
- 438 tests pass.

## [1.4.1] — 2026-09-03

`--copy` no longer hangs forever on Wayland.

v1.4 shipped the Wayland backend with `stderr=subprocess.PIPE`. A Wayland
selection is owned by a live client, so wl-copy forks a daemon to serve the
clipboard and the parent exits — and that daemon inherits the pipe and holds it
open for as long as it owns the selection. `subprocess.run` waits for an EOF
that cannot arrive, so every non-interactive `--copy` stalled after
`article.html` was already written: the run looked finished and simply never
returned. It only bites when stdout is not a terminal, which is why an
interactive run looked fine and a piped or redirected one never came back.

This is the hazard the X11 path was built around from the start, reintroduced
verbatim because nothing asserted the rule on the Wayland side. v1.4's note
about "comprehensive test coverage" for the Wayland backend was wrong in
exactly that spot.

### Fixed

- **`--copy` completes on Wayland.** Both wl-copy calls — body to CLIPBOARD and
  title to PRIMARY — now route through the same runner the X11 backend uses,
  which sends stderr to a temp file rather than a pipe. Diagnostics still
  survive; the descriptor the daemon inherits is no longer one anybody waits on.

- **Two test assertions that were not asserting.**
  `test_missing_wl_copy_exits_with_a_message` called `capsys.readouterr()`
  twice, so its second check compared against an empty string and had never
  run. `test_the_macos_script_is_too_long_for_argv` measured the torture
  fixture against a fixed byte count, but the fixture shrinks when no TrueType
  font resolves and `table_render` falls back to the bitmap default.

### Changed

- **The suite no longer reads the host's display server.** Seven tests patched
  `sys.platform` to `"linux"` and asserted on xclip, but `_is_wayland()` reads
  the real environment, so they were handed the wl-copy backend whenever the
  suite ran on a Wayland desktop — passing under X11 and failing on the
  author's own machine. An autouse fixture in a new `tests/conftest.py` clears
  `WAYLAND_DISPLAY` and `XDG_SESSION_TYPE` suite-wide; the Wayland tests opt
  back in explicitly. The suite is now 426 passing under Wayland, under X11,
  and with neither variable set.

### Technical Details

- `_run_xclip` is renamed `_run_selection_owner` and is now shared by both
  Linux backends. Two copies of the same judgement drifting apart is what
  produced this defect, so the handling is one function rather than two.
- New guards pin that neither Linux backend may hand a pipe to a
  selection-owning tool, on body and title alike.
- Verified end-to-end on a Wayland session: the command that hung now exits 0,
  with the body on CLIPBOARD as `text/html` and the title on PRIMARY.

## [1.4] — 2026-08-30

Native Wayland clipboard support with full PRIMARY/CLIPBOARD selection parity.

### Added

- **Wayland clipboard backend via wl-copy/wl-paste.** Linux systems running
  Wayland can now use `--copy` with full feature parity to X11: the article
  body goes to CLIPBOARD (Ctrl+V) and the title goes to PRIMARY (middle-click),
  matching the X11 experience. Requires `wl-clipboard` package.

- **Automatic platform detection.** The tool detects whether the system is
  running X11 or Wayland via environment variables (`XDG_SESSION_TYPE`,
  `WAYLAND_DISPLAY`) and routes to the correct clipboard backend. No manual
  configuration needed.

### Changed

- **Updated README and help text** to document Wayland support alongside X11.
  The two-gesture title hand-off is now documented as available on "Linux
  (X11 and Wayland)" rather than "X11 only."

### Technical Details

- Wayland detection in `clipboard.py:_is_wayland()`
- New `LINUX_WAYLAND` platform constant
- New `_copy_html_wayland()` and `_copy_title_wayland()` functions using
  `wl-copy --type text/html` for body and `wl-copy --primary` for title
- Comprehensive test coverage for Wayland platform detection and selection handling

## [1.3.1] — 2026-08-11

`png_files` now names every image the run writes.

A converted article's result listed its exported SVGs and its copied rasters, but
never the table PNGs — even though the run wrote them and the body it returned
pointed straight at them. Nothing in the output was wrong; what the run *said*
about its own output was incomplete, which is a Core Value 2 defect in the
reporting surface rather than in the article.

### Fixed

- **Rendered table PNGs are reported in `convert_article`'s `png_files`.**
  `replace_tables_with_images` wrote `table-N.png` and rewrote the body to
  reference it, then told its caller nothing. Tables were the one image class the
  result never named.

  Found from the consumer side rather than from here. A downstream tool assembles
  a publishable directory by copying every `png_files` entry next to
  `article.html`, and had built one referencing two images it never copied. The
  converter's own preflight could not see it: `missing_image` fires for a `src`
  *absent* from the output directory, and these files were present — written,
  referenced, and simply unmentioned.

  Only PNGs that were actually rendered are reported. A table whose render fails
  writes no file and leaves a placeholder comment; naming a path that does not
  exist would fail harder than the omission being fixed.

### Changed

- **`replace_tables_with_images` returns `TableReplacement(text, png_files)`**
  instead of a bare string. Internal to `table_handler.py` — `convert_article`'s
  result dict is unchanged in shape, and `png_files` is the same key holding the
  same type, now merely complete. Noted here for anyone importing that function
  directly.

  The paths are merged at the result rather than into `image_map`, which is keyed
  by Obsidian embed name and handed to the syntax transformer. A table PNG was
  never an embed.

### Not verified

Unchanged from 1.3.0 and repeated rather than assumed: **the macOS and Windows
clipboard paths have still never been run on their target platforms.** Nothing
this release touched `clipboard.py`, and no report has arrived from either.

406 tests pass, up from 403.

## [1.3.0] — 2026-08-10

`--copy` reaches macOS and Windows. Built from the documented mechanisms and
checked byte for byte — not proven on either platform, and not claimed to be.

### Added

- **`--copy` works on macOS and Windows.** It was Linux/X11 only; each platform
  now gets its native tool — `xclip`, `osascript`, and PowerShell respectively.
  The Linux path is unchanged, including the file-descriptor handling that
  stops a piped run from stalling.

  On macOS the article goes to the HTML clipboard flavour via `osascript`, with
  the script on stdin: a real article is 100kB of inlined base64 and its hex
  encoding is 205kB, past the per-argument limit.

  On Windows the CF_HTML payload is built here rather than by
  `Set-Clipboard -AsHtml`, which corrupts non-ASCII text and is closed
  **won't-fix** upstream. That is not an edge case for this pipeline: it
  converts ` -- ` into a real em dash and runs `smarty`, so a corpus article
  with no non-ASCII does not exist. CF_HTML offsets are byte counts, which is
  the arithmetic the upstream bug gets wrong, so the fragment is escaped to
  ASCII numeric references first — with a pure-ASCII payload, byte offsets and
  character offsets cannot diverge at all.

### Changed

- **The title hand-off is Linux-only, by design.** It relies on X11 having two
  independent selections. macOS and Windows have one clipboard and it holds the
  body, so writing the title there would destroy the article just placed. Those
  platforms print the title for you to copy by hand instead.

### Fixed

- `--copy`'s own `--help` text still said "requires xclip" after the backends
  landed, and `__version__` had been stuck at `1.0.0` since the first release.
  Both are self-description rather than behaviour, which is why two releases
  went by without either being noticed.

### Not verified

Stated here rather than buried, because it is the honest state of this release:
**the macOS and Windows clipboard paths have never been run on their target
platforms.** There is no such machine on the author's side. This is the
project's verification split taken a step further — Substack's rendering needs a
human to paste and report, and the author can be that human, but for these two
backends there is nobody at all.

What *is* verified is that the right bytes reach the right tool: the payloads
are checked byte for byte against a real converted article, including that the
macOS hex round-trips exactly and that the CF_HTML offsets land on the fragment.
That is not the same as a clipboard being written, and it is not claimed to be.

403 tests pass, up from 368.

## [1.2.0] — 2026-08-10

A run that knows its output is broken can no longer end by reporting success.

v1.1 taught the converter to notice problems. It still announced them and then
did exactly what it was going to do anyway — printed six warnings and loaded the
clipboard regardless. That is the shape of the 2026-08-08 incident: the warning
fired, and the `%%comment%%` reached a published post because nothing stood
between the warning and the paste.

### Added

- **`--copy` refuses when preflight warned.** It exits non-zero and writes to
  neither X11 selection, naming the warning count and the article. `--force`
  copies anyway and says so, because not every warning is a reason to stop —
  `slug_title` in particular is noise-controlled against the corpus and still
  fires on a few legitimate titles.

  The gate lives in the CLI, not in `preflight.check`, which stays advisory and
  non-corrective. `main()` is the only layer that owns "did this run succeed."

- **`--dry-run` names unresolvable image references.** It returns before
  conversion and so never reached the result formatter, which meant the one
  check most worth having before a real run was the one it could not report.
  Exit stays 0 — dry-run reports, `--copy` refuses.

### Fixed

- **Footnote definitions written mid-document were reported as vanished prose.**
  Rendering relocates every definition to the end of the document, and the
  fidelity comparator aligns in order, so a definition written under the
  paragraph that cites it — Obsidian's normal habit — traded places with the
  text below it and read as a deletion.

  It compounds with the gate above: `--copy` refuses on any warning, so a
  correctly written article was pushed onto `--force`, which is the bypass whose
  absence caused the incident this release exists to prevent. **A check that
  fires on correct input teaches you to walk around it.**

  Reconciled rather than authorised, as tables already were, and per-footnote
  rather than per-document: a word is excused only when it reached that
  definition's own rendered entry, so a body the renderer dropped is still
  reported and a sibling footnote sharing its vocabulary cannot vouch for it.

- **The per-article `svg/<slug>/` directory is now preferred when defaulting.**
  The vault moved to per-article SVG subdirectories; the flat `svg/` parent
  still passed `is_dir()` while the non-recursive glob found nothing in it, so
  six `<img>` tags were written for PNGs nobody generated. Hit in the composer,
  not in a test.

- **`--dry-run` and a real run agree about SVGs.** The dry-run branch carried its
  own copy of the directory logic and reported 0 SVGs whenever `--svg-dir` was
  omitted. The duplication *was* the defect; there is now one rule.

- **The `--copy` refusal no longer prints above the warnings it points at.** The
  refusal goes to unbuffered stderr while stdout is block-buffered off a tty, so
  under `> run.log` or `| tee` its "(see above)" pointed downward — misleading in
  exactly the runs an author keeps.

### Notes

First release where a defect was found by grounding the project against its own
purpose rather than by a failure in the field. The footnote fix above came out
of that review; every prior fix came after something had already cost something.

Two measurements worth keeping, because a clean report means nothing without
them. Across the author's 46-article corpus: **46/46 convert with zero failures,
37 fully clean**, and the only warnings are 7 `slug_title` and 5 `missing_image`
— no leaked comments, no literal footnote markers, no table placeholders, no
fidelity loss. And fidelity coverage held at **93.8%** through the footnote fix
(20 words withheld in total), which is what separates a narrow reconciliation
from an amnesty that would also read clean.

368 tests pass, up from 325.

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

[1.3.1]: https://github.com/chrisdavidson/obsidian-to-substack/releases/tag/v1.3.1
[1.3.0]: https://github.com/chrisdavidson/obsidian-to-substack/releases/tag/v1.3
[1.2.0]: https://github.com/chrisdavidson/obsidian-to-substack/releases/tag/v1.2
[1.1.0]: https://github.com/chrisdavidson/obsidian-to-substack/releases/tag/v1.1
[1.0.0]: https://github.com/chrisdavidson/obsidian-to-substack/releases/tag/v1.0
