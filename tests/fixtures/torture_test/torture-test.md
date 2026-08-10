---
tags:
  - fixture
  - torture-test
series: verification
---
# Torture Test: Every Construct

This fixture exercises every Markdown and Obsidian construct found in the
article corpus. It exists to be pasted into a Substack draft so each construct
can be checked in one pass, rather than discovered article by article.

The H1 above should **not** appear in the pasted body — Substack renders its
own title. If you see the title twice, `strip_duplicate_title` regressed.

## Emphasis and inline marks

Plain text, then **bold**, then *italic*, then ***bold italic***, then
`inline code`, then a [link to Substack](https://substack.com).

Underscores too: _italic_ and __bold__.

An em dash written the Obsidian way -- it should render as a single long dash,
not two hyphens.

Smart quotes: "double quoted" and 'single quoted'.

## Headings

### Third level

#### Fourth level

Text under the fourth level, to confirm the hierarchy survives.

## Lists

Unordered:

- First item
- Second item with **bold inside**
- Third item
    - Nested item one
    - Nested item two
- Fourth item

Ordered:

1. Step one
2. Step two
3. Step three

## A table with alignment and inline styles

| Left aligned | Centered | Right aligned |
| :----------- | :------: | ------------: |
| Plain cell | `code` | 1.00 |
| **Bold cell** | *italic* | 22.50 |
| A deliberately long cell that must wrap inside its column rather than stretching the table off the page | x | 333.75 |

## A second table, minimal

| Term | Meaning |
| --- | --- |
| Axiom | Accepted without derivation |
| Proposition | Derived from an axiom |

## Blockquote

> A quoted passage, to confirm blockquotes survive the paste.
> It runs across two lines.

## Obsidian embeds

An SVG embed, which the pipeline rasterizes:

![[torture-diagram.svg | center]]

A wikilink to a note that does not exist outside the vault: [[Some Other Note]].
It should render as italic text, not a broken link.

## A Markdown image

![A caption for the markdown-style image](torture-diagram.png)

## Obsidian comments

This paragraph carries a private aside inline %% This inline note must never reach Substack %% and it should read as one continuous sentence once the note is gone — if `strip_obsidian_comments` regressed, the note text above will be visible in the pasted body.

Growth was 50%% up from 20%% last year, and both literal percent signs plus
every word between them must survive — a doubled percent in prose is not a
comment opener. This is the shape that silently deleted " up from 20" before
the digit lookbehind landed, and `tools.fidelity_sweep` is what now catches it:
the live corpus carries no `%%` at all, so this fixture is the only standing
end-to-end guard on the comment path.

Before the block: this paragraph must survive with the block below removed
around it.

%%
This working note must never reach Substack either. It documents caption
and alt-text ideas for a diagram, exactly like the real defect that prompted
this fix — an opening marker alone on its own line, a body that

spans a blank line, and a closing marker alone on its own line.
%%

After the block: this paragraph must also survive, proving the block took
only itself and not its neighbours.

A fenced example documents the syntax rather than using it, and must survive
visibly — this is the only end-to-end proof that the `code`/`pre` exemption
in the preflight check holds, since it leaves a real marker in the written
HTML that must not trigger a GRD-02 warning:

```
%% this literal marker documents the syntax and must survive visibly %%
```

## A footnote defined where it was cited

Obsidian's habit is to put the definition directly under the paragraph that
cites it[^mid] rather than at the end of the file.

[^mid]: Rendering moves this definition to the bottom of the document, so an
    in-order comparison sees it and the paragraph below swap places. This
    continuation line is indented, and belongs to the same relocated block.

The paragraph after the definition is the load-bearing part of this section:
without it there is nothing for the definition to trade places with, and the
fixture would pass whether or not the reconciliation works.

## Closing

If every construct above survived the paste with no manual repair, ACPT-01
passes, including this footnote reference[^1] written in the vault's own
hyphen form.

[^1] - Guidelines for the Construction, Format, and Management of Controlled
Vocabularies, per ANSI/NISO Z39.19-2005 (R2010) standard.
