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
