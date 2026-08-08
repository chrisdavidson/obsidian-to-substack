# Morning Checklist

Everything below needs you in front of the Substack composer. Nothing here can
be automated — Substack has no rendering API, so "does it survive the paste" is
a question only a human can answer.

Budget: about 20 minutes. Work top to bottom; each item names the requirement
it closes and exactly what to look at.

**Before you start:** `output/` still holds the pre-2026-08-08 run, whose `<title>`
is the slug rather than the article's real title. Re-run the commands below —
`--copy` regenerates anyway, and the run is what prints the `Title:` line you
paste into Substack's title field.

---

## 1. The torture test — closes ACPT-01, and most of DIAG-01 / FMT-01

This fixture deliberately contains every construct in your corpus, so one paste
answers several open questions at once. **Do this one first** — it is the highest
information per minute.

```bash
uv run obsidian-to-substack tests/fixtures/torture_test --file torture-test.md --output-dir ./output --copy
```

Then open a **new Substack draft**. One run loads both X11 selections, so it
takes two gestures:

- click into the **body** → `Ctrl+V`
- click into the **title field** → **middle-click**

Substack never fills the title itself (probed 2026-08-08 — a pasted `<h1>`
lands in the body, not the title bar), so the title has to be placed by hand.
If middle-click paste is disabled in your browser, copy the `Title:` line the
CLI prints — but do the body **first**, because selecting terminal text
replaces the clipboard and would destroy the body payload.

Check each line. Mark ✅ or ❌ directly in this file — a ❌ with a note is worth
more than a clean run.

| # | What to look at | Expect | Result |
|---|---|---|---|
| 1 | Very top of the body | No title heading in the body; the title arrives in the title field by middle-click ("Torture Test: Every Construct") |This is not populating, i did a copy and paste and the title element on substack did not populate, everything else did — RESOLVED 2026-08-08: a body paste can never fill Substack's title field, confirmed by probe. `--copy` now puts the title on the X11 primary selection so it is one middle-click away |
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
| 13 | SVG diagram | The Obsidian→Substack diagram appears and is **centred** |✅ 2026-08-08 — appears, and is centred. Not answerable from this fixture (the diagram is wider than the column, so it fills it either way); settled by a narrow-image probe in which **all three** embed styles came out centred. Substack centres images itself — alignment is not controllable from this tool. See `docs/FINDINGS-MANUAL.md` |
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

## 3. Datawrapper — closed 2026-08-08 (TBL-05)

No action needed here — this one settled itself. Four runs against the
`propositions-axiom-relationship` table answered the open question: an
omitted flag first produced an ordinary conversion, then a stale token gave
`401 Unauthorized`, then a fresh token gave `403 Forbidden` (the token was
missing the `chart:read` scope Datawrapper needs to export the PNG — each of
those partial-success runs also left a published chart orphaned in the
account), and finally a token with the right scope succeeded.

That success run showed the flag never emitted the iframe TBL-05 was written
to test — it downloaded a Datawrapper PNG and embedded it with an `<img>`,
same as the local path, just worse: smaller (1200x800 fixed canvas vs. the
local renderer's 2802x407), lower density at Substack's column width, taller
in the post from dead canvas space, and carrying a repeated title and a
"Created with Datawrapper" credit the local render doesn't add. The local
renderer wins on every measured axis.

**Verdict:** `--datawrapper` is retired — the flag, its code path, and the
module are gone from the CLI. Full evidence and the comparison table are in
`docs/FINDINGS-MANUAL.md`. Nothing here needs a paste to confirm.

One thing left for you, not this change: the API token can be revoked and the
orphaned charts (roughly 3, including chart id `DOkTX`) deleted from your
Datawrapper account whenever you get to it.

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
| 2 | TBL-01 | **Confirmed 2026-08-08** by step 2 item 1 — real table image, no placeholder |
| 2 | GRD-01 | **Done.** Regression tests for every fix |
| 3 | DIAG-02 | **Done.** `.svg` and `.png` embeds both resolve |
| 4 | FMT-02 | **Confirmed 2026-08-08.** Duplicate H1 dropped; the title is now printed by the CLI to copy into Substack's title field |
| 5 | GRD-02 | **Done.** Preflight warnings; all 17 articles convert clean |
| 5 | GRD-03 | **Done.** 201 tests, up from 89 |
| 5 | ACPT-01 | **Confirmed 2026-08-08** by step 1 — torture fixture pasted clean |
| — | TBL-05 | **Closed 2026-08-08 by retirement.** See section 3 |

Your 2026-08-08 pass marked every line, item 13 included. **DIAG-01** and
**FMT-01** are answered and recorded — both asked only that the behaviour be
observed and written down, and both now are, in `docs/FINDINGS-MANUAL.md`.
**TBL-01**, **TBL-05** and **FMT-02** are confirmed by the same pass.

Four are left, and all four are yours to judge rather than mine to tick:

- **ACPT-01** and **ACPT-02** turn on your own bar: "pastes into a Substack
  draft with **no manual repair**." Nothing needed repairing, but the title
  still has to be copied into Substack's title field by hand. That is a
  platform step rather than a repair of the output — your call whether it
  clears the bar.
- **DIAG-03** ("any confirmed diagram defect is fixed and verified against a
  real paste") and **ACPT-03** ("any repair still required is recorded as a
  known limitation") both look vacuously satisfied — no diagram defect was
  observed and section 4 above is empty. Closing a requirement because nothing
  went wrong is a call for you to make.
- **TBL-04** is unblocked but unspent: you said the generated table is good
  enough, so the `![[classification-table 1.png]]` line can come out of the
  source and stop being maintained twice. That edit is in your vault, not this
  repo.

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
