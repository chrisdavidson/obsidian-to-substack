# obsidian-to-substack

Convert Obsidian Markdown articles into Substack-ready HTML.

Prose moves from Obsidian to Substack fine by hand. Everything else doesn't:
tables lose their structure, SVG diagrams aren't supported at all, and Obsidian's
`![[embed]]` and `[[wikilink]]` syntax means nothing to Substack's editor. This
tool handles that payload — it rasterizes diagrams, extracts tables (optionally
publishing them as live Datawrapper charts), rewrites Obsidian-specific syntax,
and emits HTML you can paste straight into the Substack composer.

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
| `*.png` | Rasterized SVG diagrams |
| `table-N.csv` | Extracted tables |

A typical run — convert one article and put it on the clipboard:

```bash
obsidian-to-substack ~/vault/articles --file my-post.md --copy
```

Then paste into Substack with `Ctrl+V`. The clipboard copy uses the `text/html`
MIME type so the rich-text editor keeps the formatting.

### Options

| Flag | Default | Description |
| --- | --- | --- |
| `--output-dir` | `./output` | Where converted articles are written |
| `--file` | — | Process a single `.md` file instead of the whole directory |
| `--svg-dir` | `<directory>/svg/` | Override the SVG source directory |
| `--dpi` | `192` | PNG export resolution |
| `--datawrapper` | off | Publish tables as Datawrapper charts (see below) |
| `--copy` | off | Copy the HTML to the clipboard (requires `xclip`) |
| `--open` | off | Open the result in your browser |
| `--dry-run` | off | Report what would happen without writing anything |
| `-v`, `--verbose` | off | Verbose logging |

### Datawrapper charts

Without `--datawrapper`, tables are exported to CSV and replaced with a
placeholder comment in the HTML, so you can decide what to do with them.

With `--datawrapper`, each table is created, populated, and published as a
Datawrapper chart, and the article embeds the published result instead. This
requires an API token in the environment:

```bash
export DATAWRAPPER_API_TOKEN=...
obsidian-to-substack ~/vault/articles --datawrapper
```

Get a token at [app.datawrapper.de/account/api-tokens](https://app.datawrapper.de/account/api-tokens).
The token is only ever read from the environment — never from a file in this repo.

## What gets transformed

- **Frontmatter** — parsed out of the body and preserved in `metadata.json`; the
  `title` field drives the document title.
- **SVG diagrams** — every `.svg` in the article's `svg/` directory is rasterized
  to PNG and size-validated (Substack rejects oversized images).
- **Tables** — pipe tables are extracted to CSV, then either placeholdered or
  published to Datawrapper.
- **`![[image.png]]` embeds** — rewritten to `<figure>`/`<img>`, pointed at the
  rasterized PNGs.
- **`[[Wikilinks]]`** — rendered as italic text, since the destination note
  doesn't exist outside your vault.
- **` -- `** — converted to a proper em dash.
- **Unsupported HTML** — stripped, so nothing silently breaks in the composer.

## Development

```bash
uv run pytest                                    # 89 tests
uv run pytest --cov=src --cov-report=term-missing
```

## License

MIT — see [LICENSE](LICENSE).
