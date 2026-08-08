"""Reduce HTML to a construct inventory that can be compared across sources.

Both sides of the diff — the pipeline's `article.html` and the published
Substack post — are reduced to the same shape so differences are attributable
to a construct type rather than to prose edits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment

# Substack injects its own chrome into the article body. These are not authored
# content and must never count as a difference.
CHROME_CLASSES = (
    "subscription-widget-wrap",
    "subscription-widget-wrap-editor",
    "subscribe-widget",
    "captioned-button-wrap",
    "button-wrapper",
    "footer",
    "paywall",
    "poll-embed",
    "comments-page",
)

CHROME_TEXT_PATTERNS = (
    re.compile(r"^thanks for reading", re.I),
    re.compile(r"subscribe for free to receive", re.I),
    re.compile(r"^share\s*$", re.I),
    re.compile(r"^leave a comment\s*$", re.I),
    re.compile(r"^give a gift subscription\s*$", re.I),
)

BLOCK_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "img", "table", "ul", "ol", "blockquote", "pre")


@dataclass
class Structure:
    """Construct inventory for one document."""

    headings: list[tuple[int, str]] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    tables: int = 0
    table_cells: int = 0
    lists: int = 0
    list_items: int = 0
    blockquotes: int = 0
    code_blocks: int = 0
    strong: int = 0
    emphasis: int = 0
    comments: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """Comparable scalar inventory."""
        return {
            "headings": len(self.headings),
            "paragraphs": len(self.paragraphs),
            "images": len(self.images),
            "tables": self.tables,
            "table_cells": self.table_cells,
            "lists": self.lists,
            "list_items": self.list_items,
            "blockquotes": self.blockquotes,
            "code_blocks": self.code_blocks,
            "strong": self.strong,
            "emphasis": self.emphasis,
            "html_comments": len(self.comments),
        }

    def heading_levels(self) -> dict[int, int]:
        levels: dict[int, int] = {}
        for level, _ in self.headings:
            levels[level] = levels.get(level, 0) + 1
        return levels


NESTING_BLOCKS = ("li", "blockquote", "table", "figure", "figcaption")


def _nested_in_block(node) -> bool:
    """True when a node sits inside another block that already counts it."""
    return any(parent.name in NESTING_BLOCKS for parent in node.parents)


def _is_chrome(node) -> bool:
    """True when a node is Substack UI rather than authored content."""
    for parent in node.parents:
        classes = parent.get("class") or []
        if any(chrome in " ".join(classes) for chrome in CHROME_CLASSES):
            return True
    text = node.get_text(" ", strip=True)
    return any(pattern.search(text) for pattern in CHROME_TEXT_PATTERNS)


def _article_root(soup: BeautifulSoup):
    """Find the authored-content container, falling back to the whole document."""
    for selector in ("div.available-content", "div.body.markup", "article", "body"):
        node = soup.select_one(selector)
        if node is not None:
            return node
    return soup


def extract(html: str, is_published: bool = False) -> Structure:
    """Reduce a document to its construct inventory."""
    soup = BeautifulSoup(html, "html.parser")
    root = _article_root(soup) if is_published else soup

    structure = Structure()

    for comment in root.find_all(string=lambda t: isinstance(t, Comment)):
        structure.comments.append(str(comment).strip())

    for node in root.find_all(BLOCK_TAGS):
        if is_published and _is_chrome(node):
            continue

        name = node.name
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            structure.headings.append((int(name[1]), node.get_text(" ", strip=True)))
        elif name == "p":
            text = node.get_text(" ", strip=True)
            # A <p> that only wraps an image is an image, not a paragraph.
            # A <p> nested inside another block is that block's content, not a
            # standalone paragraph — Substack wraps every <li> body in a <p>,
            # which would otherwise read as ~30 phantom paragraphs per article.
            if text and not node.find("img") and not _nested_in_block(node):
                structure.paragraphs.append(text)
        elif name == "img":
            structure.images.append(node.get("src", "") or node.get("alt", ""))
        elif name == "table":
            structure.tables += 1
            structure.table_cells += len(node.find_all(["td", "th"]))
        elif name in ("ul", "ol"):
            structure.lists += 1
            structure.list_items += len(node.find_all("li", recursive=False))
        elif name == "blockquote":
            structure.blockquotes += 1
        elif name == "pre":
            structure.code_blocks += 1

    structure.strong = len(root.find_all(["strong", "b"]))
    structure.emphasis = len(root.find_all(["em", "i"]))

    return structure
