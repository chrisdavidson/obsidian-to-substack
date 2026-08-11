"""Tests for the fidelity sweep's corpus rule.

The sweep used to select its corpus with `rglob("*.md")`, which meant it swept
anything carrying the extension. The 2026-08-10 preflight census established
what that cost: four of the twelve corpus warnings came from companion LinkedIn
promo posts -- 139-480 words, no frontmatter -- sitting *inside* their parent
article's directory, which were never going to be pasted into Substack.

Because the same selection defines the fidelity baseline, "46/46 clean at 93.8%
word coverage" was measured over a set that is not the set of things this tool
converts. The rule here is the fix: an article is a file whose author wrote a
frontmatter block.

The load-bearing test is `test_malformed_frontmatter_is_still_an_article`. The
obvious implementation reaches for `parse_frontmatter` and checks for a
non-empty dict, and that is wrong: it returns `({}, text)` for *both* "no
frontmatter" and "frontmatter present but broken YAML", collapsing two cases
that are identical for its own purpose and are not identical here. An article
with a broken header is still an article, and it is precisely the kind this
tool should be measured against rather than excused from.
"""

from __future__ import annotations

from pathlib import Path

from tools.fidelity_sweep.__main__ import find_articles


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


ARTICLE = "---\ntitle: Real Article\n---\n\nBody text here.\n"
COMPANION = "A LinkedIn promo post. No frontmatter, never pasted into Substack.\n"


def test_an_article_with_frontmatter_is_in_the_corpus(tmp_path: Path) -> None:
    _write(tmp_path / "real.md", ARTICLE)

    corpus = find_articles(tmp_path)

    assert [p.name for p in corpus.articles] == ["real.md"]
    assert corpus.skipped == []


def test_a_companion_without_frontmatter_is_not(tmp_path: Path) -> None:
    """The defect this rule exists to close, in its real shape.

    The companion sits inside the parent article's own directory, which is why
    a path-based rule could not have told them apart.
    """
    _write(tmp_path / "taxonomy/taxonomy.md", ARTICLE)
    _write(tmp_path / "taxonomy/linkedin-taxonomy.md", COMPANION)

    corpus = find_articles(tmp_path)

    assert [p.name for p in corpus.articles] == ["taxonomy.md"]
    assert [p.name for p in corpus.skipped] == ["linkedin-taxonomy.md"]


def test_malformed_frontmatter_is_still_an_article(tmp_path: Path) -> None:
    """Fail closed by INCLUDING the uncertain file.

    For a corpus filter the fail-closed direction is inclusion: an excluded
    article vanishes from the census with nothing left to notice, while an
    included non-article is visible noise. So the rule keys on the delimiter
    block, not on the YAML parsing successfully.

    `parse_frontmatter` cannot answer this -- it returns `({}, text)` here,
    exactly as it does for a file with no frontmatter at all.
    """
    broken = "---\ntitle: [unclosed\n  bad: : indent\n---\n\nReal prose.\n"
    _write(tmp_path / "broken-header.md", broken)

    corpus = find_articles(tmp_path)

    assert [p.name for p in corpus.articles] == ["broken-header.md"]
    assert corpus.skipped == []


def test_empty_frontmatter_block_is_still_an_article(tmp_path: Path) -> None:
    """A block the author opened and left empty is a block they wrote."""
    _write(tmp_path / "empty-header.md", "---\n---\n\nReal prose.\n")

    corpus = find_articles(tmp_path)

    assert [p.name for p in corpus.articles] == ["empty-header.md"]


def test_a_delimiter_below_the_first_line_does_not_count(tmp_path: Path) -> None:
    """`---` is also a horizontal rule and a table separator in Markdown.

    Frontmatter is only frontmatter at the very top of the file, which is what
    the shared pattern's `\\A` anchor enforces. Without this the rule would
    re-admit every companion carrying a thematic break.
    """
    _write(tmp_path / "rule.md", "Some prose first.\n\n---\ntitle: not really\n---\n")

    corpus = find_articles(tmp_path)

    assert corpus.articles == []
    assert [p.name for p in corpus.skipped] == ["rule.md"]


def test_skipped_files_are_reported_not_discarded(tmp_path: Path) -> None:
    """No silent caps.

    A census that drops from 46 to 42 must say why. Silently narrowing what is
    measured is the same failure class as 260811-dx4 -- a number that
    under-reports without saying so -- and this rule must not introduce a
    second one while fixing a denominator.
    """
    _write(tmp_path / "a.md", ARTICLE)
    for name in ("x.md", "y.md", "z.md"):
        _write(tmp_path / name, COMPANION)

    corpus = find_articles(tmp_path)

    assert len(corpus.articles) == 1
    assert [p.name for p in corpus.skipped] == ["x.md", "y.md", "z.md"]


def test_nested_articles_are_found_in_stable_order(tmp_path: Path) -> None:
    """Both corpus layouts still work: bare `article.md` and directory-with-svg."""
    _write(tmp_path / "b-flat.md", ARTICLE)
    _write(tmp_path / "a-dir/a-dir.md", ARTICLE)
    _write(tmp_path / "c-dir/c-dir.md", ARTICLE)

    corpus = find_articles(tmp_path)

    assert [p.name for p in corpus.articles] == ["a-dir.md", "b-flat.md", "c-dir.md"]
    assert corpus.articles == sorted(corpus.articles)


def test_pure_function_no_mutation(tmp_path: Path) -> None:
    """Two calls over an unchanged tree agree, and neither writes to it."""
    _write(tmp_path / "real.md", ARTICLE)
    _write(tmp_path / "promo.md", COMPANION)
    before = sorted(p.name for p in tmp_path.rglob("*"))

    first = find_articles(tmp_path)
    second = find_articles(tmp_path)

    assert first == second
    assert sorted(p.name for p in tmp_path.rglob("*")) == before
