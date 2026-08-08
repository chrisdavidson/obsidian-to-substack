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
the head title element, `metadata.json`, the Datawrapper chart title, and a
new Title line in the CLI's success output.

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
