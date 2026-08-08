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


def strip_unsupported_elements(html: str) -> str:
    """Remove HTML elements that Substack cannot render."""
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in UNSUPPORTED_TAGS:
        for tag in soup.find_all(tag_name):
            tag.unwrap() if tag.string else tag.decompose()

    for a_tag in soup.find_all("a"):
        href = a_tag.get("href", "")
        if href.startswith("#"):
            a_tag.unwrap()

    return str(soup)
