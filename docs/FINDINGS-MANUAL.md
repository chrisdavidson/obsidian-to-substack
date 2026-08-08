### The stripped H1's text never reached the output

**Requirement:** FMT-02

The head title of `output/torture-test/article.html` was the filename slug
(`torture test`) while its source H1 reads `# Torture Test: Every
Construct`; the head title of
`output/propositions-axiom-relationship/article.html` was likewise the slug
(`propositions axiom relationship`) while its source H1 reads
`# Propositions: How One Axiom Becomes a Framework`. Both files contain
zero `h1` elements — correct, that is the FMT-02 strip working.
`metadata.json` for `torture-test` held only `tags` and `series`, no title
key at all.

Root cause: `strip_duplicate_title` extracted the dropped heading's text
only to write a log line, then discarded it, so the filename-slug fallback
fired for every article regardless of whether it had a real title.

Fix: `strip_duplicate_title` now returns the dropped text; `convert_article`
resolves one title (H1, then frontmatter title, then slug) and feeds it to
the head title element, `metadata.json`, and a new Title line in the CLI's
success output.

Note: Substack's own title field is still filled by hand — this fix
supplies the text the author needs to paste, not the paste itself.

### Step 3's command never entered the Datawrapper code path

**Requirement:** TBL-05

The step-3 command in `docs/MORNING-CHECKLIST.md` omitted the
`--datawrapper` flag, so `dw_token` stayed `None` and the Datawrapper branch
in `convert_article` was never entered. Consequently
`output-dw/propositions-axiom-relationship/` is an ordinary conversion — it
holds `table-1.png` with no iframe and no Datawrapper URL. The run produced
zero information and TBL-05 remains fully open.

Fix: the `--datawrapper` flag has been added to the command in
`docs/MORNING-CHECKLIST.md`. The author decides whether to re-run it;
nothing in this change re-runs it.

### TBL-05 closed: the local renderer beats Datawrapper on every measured axis

**Requirement:** TBL-05

The prior entry is attempt 1 of this timeline. Three further runs, 2026-08-08,
settled TBL-05 empirically:

2. Second run, flag present: `401 Unauthorized` — stale token.
3. Third run, fresh token: `403 Forbidden — Insufficient scope`. The token
   carried `chart:write folder:write team:write theme:read visualization:read
   user:write auth:read` but not `chart:read`, which Datawrapper requires for
   `GET /charts/{id}/export/{format}`. Because `chart:write` was present,
   chart creation, data upload, and publish all succeeded and only the final
   PNG export failed — so each failed run left a published chart orphaned in
   the author's account (roughly 3, including chart id `DOkTX`).
4. Fourth run, `chart:read` added: succeeded, emitting a Datawrapper URL in an
   HTML comment followed by an `<img>` pointing at the locally written
   `table-1.png`.

**The premise correction.** TBL-05 assumed the flag emitted an iframe that
Substack would strip on paste. It never did. `replace_tables_with_embeds`
downloaded a PNG from Datawrapper and emitted an `<img>`, keeping the public
chart URL only in an HTML comment, which Substack drops on paste. So the real
comparison is Datawrapper's table PNG against the local renderer's, same
table:

| | Local renderer | Datawrapper |
|---|---|---|
| Pixels | 2802 x 407 | 1200 x 800 (fixed canvas) |
| Density at Substack's 680px column | ~4.1x | ~1.8x |
| Rendered height in the post | ~99px | ~453px |
| Title | none | repeats the article title above the table, under Substack's own title |
| Branding | none | "Created with Datawrapper" credit |
| Dead space | none | ~150px of empty canvas |
| Styling | header shading + cell rules | header rule only |

The local renderer wins on every axis.

Fix: the `--datawrapper` flag and its entire code path have been retired.
`replace_tables_with_images` is the sole table path; the CSV sidecar keeps
exporting independently of any external service. The orphaned Datawrapper
charts from the 403 runs and the API token itself are left for the author to
clean up by hand — this change makes no network call to do either.

### Substack centres every image, so alignment is not controllable

**Requirement:** DIAG-01

SVG embeds survive the paste. Observed directly in a Substack draft on
2026-08-08: the rasterized diagram renders, and so does the second copy
embedded with `![alt](path)` Markdown syntax.

Whether the `| center` hint does anything took a purpose-built probe, because
**the torture fixture cannot answer it.** `torture-diagram.svg` is 600x200 and
rasterizes to 1200x400 at the default 192 DPI — wider than Substack's ~680px
body column, so the image is scaled to full width and centred-versus-left is
literally unobservable. That is why checklist item 13 sat unanswered while
every line around it was marked.

The probe used one 200x120 SVG, rendered to 400x240 — 59% of the column, so
alignment is unmistakable — embedded three ways in a single paste:

| | Written as | Emitted as |
|---|---|---|
| A | `![[narrow-box.svg \| center]]` | `<figure style="text-align: center;"><img></figure>` |
| B | `![[narrow-box.svg]]` | `<p><img></p>` |
| C | `![A narrow box](narrow-box.png)` | `<p><img></p>` |

**All three rendered centred.** Substack centres images itself; the inline
`text-align: center` is not what produced the result and B and C had no
alignment markup at all.

The corollary matters more than the pass: **image alignment is not
controllable from this tool.** No markup this pipeline emits can produce a
left- or right-aligned image in a Substack post. The `| center` hint is
retained because it is meaningful in the standalone HTML output, but it is
inert in the composer and must not be relied on there.

No diagram defect was observed, so there is nothing for DIAG-03 to fix.

### Formatting survives the paste intact

**Requirement:** FMT-01

The author pasted the torture fixture into a live Substack draft on
2026-08-08 and marked every formatting line as surviving: bold, italic, bold
italic, inline code and links; the em dash rendering as one long dash rather
than `--`; H2/H3/H4 visibly distinct with the hierarchy intact; unordered
lists with visible nesting; ordered lists numbered rather than bulleted;
blockquotes rendering as quotes; and `[[wikilinks]]` arriving as italic text
rather than broken links.

No formatting defect was observed. The one failure in that pass was the
missing title, recorded as the first finding in this file and fixed — and it
was never a formatting defect. It was a title that existed nowhere the author
could reach.
