"""CLI for diffing pipeline output against published Substack posts.

    python -m tools.substack_diff --build-map
    python -m tools.substack_diff --all
    python -m tools.substack_diff --article propositions-axiom-relationship
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import logging
import sys
from pathlib import Path

from . import diagnose, mapping, report
from .fetch import DEFAULT_CACHE, FetchError, fetch_archive, fetch_post
from .structure import extract

logger = logging.getLogger("substack_diff")

DEFAULT_VAULT = Path.home() / "Obsidian/BrainBank/4_Archive/Published Articles"
DEFAULT_PUBLICATION = "foxglenacres.substack.com"
DEFAULT_OUTPUT = Path("docs/FINDINGS.md")


def build_map(vault: Path, publication: str, map_path: Path) -> int:
    archive = fetch_archive(publication)
    proposals = mapping.propose(vault, archive)
    mapping.save(proposals, map_path)

    print(f"Wrote {len(proposals)} mappings to {map_path}")
    low = {k: v for k, v in proposals.items() if v["confidence"] < 0.75}
    if low:
        print("\nLow-confidence matches — review these by hand:")
        for name, entry in sorted(low.items()):
            print(f"  {entry['confidence']:.2f}  {name}\n        -> {entry['title']}")
    missing = [k for k, v in proposals.items() if not v["has_article_html"]]
    if missing:
        print("\nNo archived article.html (re-run the converter for these):")
        for name in missing:
            print(f"  {name}")
    return 0


def run_diff(
    vault: Path,
    publication: str,
    map_path: Path,
    output: Path,
    only: str | None,
    cache_dir: Path,
    refresh: bool,
) -> int:
    entries = mapping.load(map_path)
    if only:
        if only not in entries:
            print(f"Error: '{only}' is not in {map_path}", file=sys.stderr)
            return 1
        entries = {only: entries[only]}

    findings: list[report.Finding] = []
    compared: list[str] = []
    skipped: dict[str, str] = {}
    patterns_by_article: dict[str, list] = {}

    for name, entry in sorted(entries.items()):
        directory = vault / name
        article_html = mapping.find_article_html(directory)
        if article_html is None:
            skipped[name] = "no archived `article.html` — re-run the converter (EVID-04)"
            continue

        try:
            published_html = fetch_post(
                publication, entry["slug"], cache_dir=cache_dir, refresh=refresh
            )
        except FetchError as exc:
            skipped[name] = f"fetch failed: {exc}"
            continue

        pipeline_structure = extract(
            article_html.read_text(encoding="utf-8"), is_published=False
        )
        published_structure = extract(published_html, is_published=True)

        findings.extend(report.compare(name, pipeline_structure, published_structure))
        patterns = diagnose.detect(
            pipeline_structure, published_structure, entry.get("title", "")
        )
        if patterns:
            patterns_by_article[name] = patterns
        compared.append(name)
        logger.info("compared %s (%d pattern(s))", name, len(patterns))

    generated = _datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        report.render(findings, compared, skipped, generated, patterns_by_article),
        encoding="utf-8",
    )

    print(f"Compared {len(compared)} articles, {len(findings)} differences.")
    if skipped:
        print(f"Skipped {len(skipped)}: {', '.join(sorted(skipped))}")
    print(f"Wrote {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="substack_diff",
        description="Diff pipeline output against published Substack posts",
    )
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--publication", default=DEFAULT_PUBLICATION)
    parser.add_argument("--map", dest="map_path", type=Path, default=mapping.DEFAULT_MAP)
    parser.add_argument("--out", dest="output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--build-map", action="store_true", help="Regenerate the article map")
    parser.add_argument("--all", action="store_true", help="Diff every mapped article")
    parser.add_argument("--article", help="Diff a single article directory by name")
    parser.add_argument("--refresh", action="store_true", help="Bypass the fetch cache")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not args.vault.is_dir():
        print(f"Error: vault not found: {args.vault}", file=sys.stderr)
        return 1

    try:
        if args.build_map:
            return build_map(args.vault, args.publication, args.map_path)
        if args.all or args.article:
            return run_diff(
                args.vault,
                args.publication,
                args.map_path,
                args.output,
                args.article,
                args.cache_dir,
                args.refresh,
            )
    except FetchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
