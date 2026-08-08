"""Map local article directories to published Substack slugs.

The mapping is generated once by fuzzy-matching vault directory names against
archive titles, then written to JSON so it can be hand-corrected. Matching is a
convenience; the JSON file is the authority.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

DEFAULT_MAP = Path("tools/article_map.json")


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def find_article_html(directory: Path) -> Path | None:
    """Return the pipeline output for an article directory, if present.

    Prefers the archived `article.html` alongside the source. Falls back to a
    `_regen/` subtree, which is where EVID-04 re-runs land for the articles
    whose original output was never kept.
    """
    candidate = directory / "article.html"
    if candidate.exists():
        return candidate

    regenerated = sorted(directory.glob("_regen/*/article.html"))
    return regenerated[0] if regenerated else None


def find_source_markdown(directory: Path) -> Path | None:
    """Return the article's source Markdown, ignoring LinkedIn side-posts."""
    candidates = [
        path
        for path in sorted(directory.glob("*.md"))
        if not path.name.lower().startswith("linkedin")
    ]
    return candidates[0] if candidates else None


def propose(vault: Path, archive: list[dict], cutoff: float = 0.45) -> dict[str, dict]:
    """Fuzzy-match article directories to archive entries."""
    titles = {_normalize(entry["title"]): entry for entry in archive}
    proposals: dict[str, dict] = {}

    for directory in sorted(p for p in vault.iterdir() if p.is_dir()):
        source = find_source_markdown(directory)
        if source is None:
            continue

        keys = [_normalize(directory.name), _normalize(source.stem)]
        best_entry, best_score = None, 0.0
        for key in keys:
            for title_key, entry in titles.items():
                score = difflib.SequenceMatcher(None, key, title_key).ratio()
                if score > best_score:
                    best_entry, best_score = entry, score

        if best_entry and best_score >= cutoff:
            proposals[directory.name] = {
                "slug": best_entry["slug"],
                "title": best_entry["title"],
                "confidence": round(best_score, 3),
                "source_markdown": source.name,
                "has_article_html": find_article_html(directory) is not None,
            }

    return proposals


def load(path: Path = DEFAULT_MAP) -> dict[str, dict]:
    if not Path(path).exists():
        raise FileNotFoundError(
            f"No article map at {path}. Run with --build-map first."
        )
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(mapping: dict[str, dict], path: Path = DEFAULT_MAP) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
