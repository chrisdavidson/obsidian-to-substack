# obsidian-to-substack

Convert Obsidian Markdown articles into Substack-ready HTML.

Prose moves from Obsidian to Substack fine by hand. Everything else doesn't:
tables lose their structure, SVG diagrams aren't supported at all, and Obsidian's
`![[embed]]` and `[[wikilink]]` syntax means nothing to Substack's editor. This
tool handles that payload — it rasterizes diagrams, renders tables to images,
rewrites Obsidian-specific syntax, and emits HTML you can paste straight into
the Substack composer.

## Requirements

- Python 3.11+
- [Cairo](https://www.cairographics.org/) — for SVG rasterization (via CairoSVG;
  falls back to Inkscape if available)
- `xclip` — only for `--copy` on Linux

## Install

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

## Usage

Point it at a directory of Obsidian articles:

```bash
obsidian-to-substack ~/vault/articles
```

Each `.md` file becomes a folder under `./output/<slug>/` containing:

| File | What it is |
| --- | --- |
| `article.html` | The Substack-ready document |
| `metadata.json` | Frontmatter, preserved |
| `*.png` | Rasterized SVG diagrams and copied raster embeds |
| `table-N.png` | Tables, rendered as images |
| `table-N.csv` | The same tables as data |

After each run, a preflight check reports any construct known to break in
Substack — a leaked table placeholder, a missing or oversized image, a heading
that will paste as a duplicate title. Each warning cites the requirement it
came from.

A typical run — convert one article and put it on the clipboard:

```bash
obsidian-to-substack ~/vault/articles --file my-post.md --copy
```

That loads both X11 selections, so pasting into Substack takes two gestures:

- click into the **body** and press `Ctrl+V` — the article, copied as
  `text/html` so the rich-text editor keeps the formatting
- click into the **title field** and **middle-click** — the article's title as
  plain text

Substack never fills its title field from pasted body content, so the title has
to be placed by hand. Putting it on the primary selection rather than the
clipboard means one run covers both, instead of the title copy clobbering the
article. If middle-click paste is disabled in your browser, the title is also
printed on the `Title:` line — but paste the body first, or selecting that text
will replace the clipboard.

### Options

| Flag | Default | Description |
| --- | --- | --- |
| `--output-dir` | `./output` | Where converted articles are written |
| `--file` | — | Process a single `.md` file instead of the whole directory |
| `--svg-dir` | `<directory>/svg/` | Override the SVG source directory |
| `--dpi` | `192` | PNG export resolution |
| `--copy` | off | Body HTML to the clipboard, title to the primary selection (requires `xclip`) |
| `--open` | off | Open the result in your browser |
| `--dry-run` | off | Report what would happen without writing anything |
| `-v`, `--verbose` | off | Verbose logging |

### Tables

Substack's composer will not accept a pasted HTML table. Each Markdown table
is rendered to a PNG — honoring column alignment and inline bold/italic — and
embedded as an image, which is what the composer does accept. The same table
is also written out as a CSV, a standalone data sidecar you can open in a
spreadsheet or reuse elsewhere.

## What gets transformed

- **Frontmatter** — parsed out of the body and preserved in `metadata.json`; the
  `title` field drives the document title.
- **SVG diagrams** — every `.svg` in the article's `svg/` directory is rasterized
  to PNG and size-validated (Substack rejects oversized images).
- **Tables** — pipe tables are rendered to PNG and exported to CSV.
- **`![[image.svg]]` and `![[image.png]]` embeds** — rewritten to
  `<figure>`/`<img>`. SVGs are rasterized; raster files are copied into the
  output directory so the reference resolves. Markdown `![alt](path)` images
  work too, including percent-encoded and stale vault-relative paths.
- **A leading `# Title`** — dropped when it is the document's only H1, since
  Substack renders its own title above the body.
- **`[[Wikilinks]]`** — rendered as italic text, since the destination note
  doesn't exist outside your vault.
- **` -- `** — converted to a proper em dash.
- **Unsupported HTML** — stripped, so nothing silently breaks in the composer.

## Non-goals

Datawrapper was evaluated as a table-rendering route and retired on
2026-08-08: worse image at Substack's column width, an extra secret to
manage, and an external publish on every run. Full evidence is in
[docs/FINDINGS-MANUAL.md](docs/FINDINGS-MANUAL.md).

## Development

```bash
uv run pytest                                    # 201 tests, 93% coverage
uv run pytest --cov=src --cov-report=term-missing
```

### Verifying against real Substack posts

`tools/substack_diff` compares the pipeline's output against articles already
published, to recover what needed fixing by hand:

```bash
uv run python -m tools.substack_diff --build-map   # match vault dirs to posts
uv run python -m tools.substack_diff --all         # writes docs/FINDINGS.md
```

Findings live in [docs/FINDINGS.md](docs/FINDINGS.md). Each defect it surfaces
becomes a regression test and, where it can be detected before pasting, a
preflight warning.

## License

MIT — see [LICENSE](LICENSE).
