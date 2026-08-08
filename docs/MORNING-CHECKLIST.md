# Morning Checklist

Everything below needs you in front of the Substack composer. Nothing here can
be automated — Substack has no rendering API, so "does it survive the paste" is
a question only a human can answer.

Budget: about 20 minutes. Work top to bottom; each item names the requirement
it closes and exactly what to look at.

**Before you start:** the outputs are already generated in `output/`. You do not
need to re-run the converter unless you want to.

---

## 1. The torture test — closes ACPT-01, and most of DIAG-01 / FMT-01

This fixture deliberately contains every construct in your corpus, so one paste
answers several open questions at once. **Do this one first** — it is the highest
information per minute.

```bash
uv run obsidian-to-substack tests/fixtures/torture_test --file torture-test.md --output-dir ./output --copy
```

Then open a **new Substack draft** and press `Ctrl+V`.

Check each line. Mark ✅ or ❌ directly in this file — a ❌ with a note is worth
more than a clean run.

| # | What to look at | Expect | Result |
|---|---|---|---|
| 1 | Very top of the body | The title "Torture Test: Every Construct" appears **once** (Substack's own title), not twice |This is not populating, i did a copy and paste and the title element on substack did not populate, everything else did |
| 2 | "Emphasis and inline marks" | bold, *italic*, ***bold italic***, `inline code`, and the link all render |X |
| 3 | Same section | The em dash renders as one long dash, not `--` |X |
| 4 | Headings | H2/H3/H4 are visibly different sizes and the hierarchy is intact |X |
| 5 | Unordered list | Bullets render, and the two nested items are visibly indented |X |
| 6 | Ordered list | Numbered 1/2/3, not bulleted |X |
| 7 | First table image | Renders as an image; left/centre/right columns are visibly aligned differently |X |
| 8 | First table image | The long cell **wrapped** inside its column instead of running off the page |X |
| 9 | First table image | "Bold cell" is bold, "italic" is italic, and `code` shows **without** backticks |X |
| 10 | Second table image | Renders, 2 columns, readable at normal zoom |X |
| 11 | Both table images | Text is **sharp**, not blurry or shrunken |X |
| 12 | Blockquote | Renders as a quote, not plain text |X |
| 13 | SVG diagram | The Obsidian→Substack diagram appears and is **centred** | |
| 14 | Markdown image | The second copy of the diagram appears (tests `![alt](path)` syntax) |X |
| 15 | Wikilink | "Some Other Note" is *italic text*, not a broken link |X |

**If items 1, 7–11, 13, or 14 pass**, the fixes I made overnight are confirmed
working. If any fail, note what you saw — that is a finding, and it goes in
`docs/FINDINGS.md`.

---

## 2. The real article — closes ACPT-02, TBL-01, TBL-04

`propositions-axiom-relationship` is the article that proved the table defect:
its source contains the Markdown table **and** a hand-drawn image of the same
table, because the tool used to emit only a placeholder comment.

```bash
uv run obsidian-to-substack ~/Obsidian/BrainBank/4_Archive/"Published Articles"/propositions-axiom-relationship \
  --file propositions-axiom-relationship.md --output-dir ./output --copy
```

Paste into a **new draft** (do not overwrite the published post).

| # | What to look at | Expect | Result |
|---|---|---|---|
| 1 | Where the table belongs | A real, readable table image appears — **no** blank gap, no stray comment |X |
| 2 | Immediately below it | Your old hand-drawn `classification-table` image also appears |X |
| 3 | Compare the two | The generated table should be at least as readable as your hand-drawn one |X |
| 4 | Top of body | Title appears once, not twice |X |
| 5 | All three diagrams | `three-statements`, `derivation-tree`, `classification-table` all render |X |

**The decision this unlocks (TBL-04):** if item 3 says the generated table is
good enough, you can delete the `![[classification-table 1.png]]` line from the
source and stop maintaining the table twice. That is the whole point of the fix.
If it is not good enough, tell me what is wrong with it.

---

## 3. Datawrapper — closes TBL-05

This is the one genuinely open question I could not touch. The `--datawrapper`
path publishes each table as a Datawrapper chart and embeds it. My expectation
is that Substack strips the iframe on paste and you get nothing — but that is an
assumption, and TBL-05 exists to settle it.

```bash
export DATAWRAPPER_API_TOKEN=...   # your token
uv run obsidian-to-substack ~/Obsidian/BrainBank/4_Archive/"Published Articles"/propositions-axiom-relationship \
  --file propositions-axiom-relationship.md --output-dir ./output-dw --datawrapper --copy
```

| # | What to look at | Expect | Result |
|---|---|---|---|
| 1 | Where the table belongs | Does *anything* appear? A chart, a link, or nothing at all? |X |
| 2 | If something appears | Is it interactive, a static image, or a bare URL? |X |

**Then decide:** if the embed survives and looks good, `--datawrapper` stays and
gets documented. If it pastes as nothing, we retire the flag rather than leave a
trap in the CLI. Either answer closes TBL-05 — there is no wrong outcome, only
an unrecorded one.

---

## 4. Anything still needing repair — closes ACPT-03

If you had to fix *anything* by hand in steps 1–3, write it here rather than
just fixing it. That is the habit this whole milestone exists to establish.

```
Construct:
What the tool produced:
What you changed it to:
```

---

## What I did overnight

Committed, tested, and verified as far as it can be without you:

| Phase | Requirement | State |
|---|---|---|
| 1 | EVID-01…05 | **Done.** `tools/substack_diff` + `docs/FINDINGS.md`, all 17 articles |
| 2 | TBL-02, TBL-03, TBL-04 | **Built.** Tables render to PNG with alignment and inline styles |
| 2 | TBL-01 | **Built, needs step 2.** Placeholder no longer emitted |
| 2 | GRD-01 | **Done.** Regression tests for every fix |
| 3 | DIAG-02 | **Done.** `.svg` and `.png` embeds both resolve |
| 4 | FMT-02 | **Built, needs step 1.** Duplicate title heading dropped |
| 5 | GRD-02 | **Done.** Preflight warnings; all 17 articles convert clean |
| 5 | GRD-03 | **Done.** 192 tests, up from 89 |
| 5 | ACPT-01 | **Fixture built, needs step 1** |

Still fully open, because they are yours: **TBL-05** (step 3), **DIAG-01**
(step 1, items 13–14), **FMT-01** (step 1, items 1–6, 12, 15), **DIAG-03** and
**FMT-02**'s verification, **ACPT-02** (step 2), **ACPT-03** (step 4).

### Defects found and fixed

1. **Table placeholder** — `<!-- TABLE N: ... -->` reached the composer; 2 articles. Now renders a PNG.
2. **Duplicate title H1** — 5 of 17 articles. Now dropped when it is the document's only H1.
3. **Raster embeds never copied** — `![[name.png]]` pointed at a missing file and pasted broken. `axiom-load-bearing` emitted 0 images despite 3 embeds; now 3.
4. **Percent-encoded paths** — `saas-two-boxes%201.png` never resolved to `saas-two-boxes 1.png`.
5. **Stale path prefixes** — archived articles kept `2_Areas/articles/drafts/svg/…` paths from where they were drafted; now falls back to basename.
6. **Literal HTML in table images** — cells rendered as `<strong>Bold cell</strong>`. Found by looking at the rendered PNG, not by a test.

### One thing to know

Two articles (`axiom-load-bearing`, `Taxonom_Supports_Strategic_Decisions`)
never had their pipeline output kept, so EVID-04 regenerates them on demand
into `.cache/regen/` — inside this repo, gitignored. **Your vault is never
written to.** Because that regeneration uses today's code rather than the code
that produced the published post, `FINDINGS.md` flags those two rows.
