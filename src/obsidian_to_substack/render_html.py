"""Render cleaned Markdown to HTML suitable for Substack paste."""

import logging
import re

import markdown
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MARKDOWN_EXTENSIONS = [
    "tables",
    "footnotes",
    "fenced_code",
    "smarty",
]

UNSUPPORTED_TAGS = {"div", "u", "script"}

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{
    font-family: 'Charter', 'Georgia', serif;
    max-width: 680px;
    margin: 2em auto;
    padding: 0 1em;
    line-height: 1.7;
    color: #333;
    font-size: 18px;
}}
h1, h2, h3, h4, h5, h6 {{
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    margin-top: 1.8em;
    margin-bottom: 0.5em;
    line-height: 1.3;
}}
h1 {{ font-size: 2em; }}
h2 {{ font-size: 1.5em; }}
h3 {{ font-size: 1.25em; }}
blockquote {{
    border-left: 3px solid #ccc;
    margin-left: 0;
    padding-left: 1.2em;
    color: #555;
}}
figure {{
    margin: 1.5em 0;
    padding: 0;
}}
figure img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
}}
code {{
    font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
    font-size: 0.9em;
    background: #f5f5f5;
    padding: 0.15em 0.3em;
    border-radius: 3px;
}}
pre code {{
    display: block;
    padding: 1em;
    overflow-x: auto;
    background: #f5f5f5;
}}
hr {{
    border: none;
    border-top: 1px solid #ddd;
    margin: 2em 0;
}}
</style>
</head>
<body>
{body}
</body>
</html>"""


def _fix_list_breaks(text: str) -> str:
    """Ensure blank lines before list items so markdown parses them as lists."""
    lines = text.split("\n")
    fixed: list[str] = []
    for i, line in enumerate(lines):
        if i > 0 and re.match(r"^- ", line) and fixed and fixed[-1].strip() and not fixed[-1].startswith("- "):
            fixed.append("")
        fixed.append(line)
    return "\n".join(fixed)


def render_to_html(text: str) -> str:
    """Convert Markdown text to HTML body content."""
    text = _fix_list_breaks(text)
    md = markdown.Markdown(extensions=MARKDOWN_EXTENSIONS)
    return md.convert(text)


def wrap_html(body: str, title: str = "") -> str:
    """Wrap HTML body in a complete document with Substack-friendly styling."""
    return HTML_TEMPLATE.format(title=title, body=body)


def _normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def strip_duplicate_title(body_html: str, title: str = "") -> tuple[str, str]:
    """Drop a leading H1 that acts as the article's title.

    Obsidian sources often open with `# The Article Title`. Substack renders
    its own title above the post body, so pasting that H1 produces a duplicate
    heading the author has to delete by hand — observed in 5 of 17 published
    articles (docs/FINDINGS.md, `duplicate_title_h1`).

    A leading H1 is treated as a title when it is the document's *only* H1.
    Articles that use `#` for every section have many H1s, and there the first
    one is a real section heading. That rule classifies all 17 articles in the
    corpus correctly; matching against `title` alone does not, because Obsidian
    sources carry no frontmatter title and authors reword titles when
    publishing.

    Returns a `(body, dropped_heading_text)` tuple. The second element is the
    text of the heading that was dropped — it is the article's title. Every
    early-return path (no headings, non-H1 leading heading, or a leading H1
    that fails both the sole-H1 and title-match tests) returns the body
    untouched paired with an empty string, not None — callers chain it with
    `or`.
    """
    soup = BeautifulSoup(body_html, "html.parser")
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if not headings or headings[0].name != "h1":
        return body_html, ""

    first = headings[0]
    sole_h1 = len([h for h in headings if h.name == "h1"]) == 1
    matches_title = bool(title) and _normalize_title(
        first.get_text(" ", strip=True)
    ) == _normalize_title(title)

    if not (sole_h1 or matches_title):
        return body_html, ""

    dropped_text = first.get_text(" ", strip=True)
    logger.info("Dropped duplicate title heading: %s", dropped_text)
    first.decompose()
    return str(soup), dropped_text


def extract_leading_title(markdown_text: str) -> str:
    """Return the text of a leading sole-H1 heading in Markdown, or "".

    Delegates to `strip_duplicate_title` rather than regexing for a leading
    `# ` line: that inherits the single sole-H1 rule, and it will not
    miscount a hash-prefixed line that happens to sit inside a fenced code
    block (the article corpus's torture-test fixture contains fenced code).
    """
    return strip_duplicate_title(render_to_html(markdown_text))[1]


def strip_unsupported_elements(html: str) -> str:
    """Remove HTML elements that Substack cannot render.

    `div` is in UNSUPPORTED_TAGS, and the generic loop below unwraps a div
    only when it has `.string` (a single text-ish child) — a multi-child div
    takes the decompose branch and its whole subtree is deleted. python-
    markdown's footnotes extension emits `<div class="footnote"><hr /><ol>
    ...</ol></div>`, which has two children and no `.string`, so without this
    exception the entire footnotes section — marker AND text — is silently
    destroyed (F2). That is strictly worse than the unconverted `[^1]`
    literal it replaces: at least the literal shows the author *something*.
    The footnotes section is the one subtree this pipeline is required to
    keep, so it is unwrapped (not decomposed) before the generic loop runs,
    and the generic loop needs no other special-casing.
    """
    soup = BeautifulSoup(html, "html.parser")

    for backref in soup.find_all("a", class_="footnote-backref"):
        # Removed outright, not unwrapped: the generic anchor-unwrap loop
        # below would otherwise strip its "#fnref:N" href and leave its "↩"
        # glyph stranded as stray text in the footnote body (F6).
        backref.decompose()

    for footnote_div in soup.find_all("div", class_="footnote"):
        footnote_div.unwrap()

    for tag_name in UNSUPPORTED_TAGS:
        for tag in soup.find_all(tag_name):
            tag.unwrap() if tag.string else tag.decompose()

    for a_tag in soup.find_all("a"):
        href = a_tag.get("href", "")
        if href.startswith("#"):
            a_tag.unwrap()

    return str(soup)
