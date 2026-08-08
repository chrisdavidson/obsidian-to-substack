"""CLI entry point for Obsidian-to-Substack conversion."""

import argparse
import base64
import json
import logging
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

from obsidian_to_substack.frontmatter import parse_frontmatter
from obsidian_to_substack.image_assets import copy_raster_embeds, rewrite_image_refs
from obsidian_to_substack import preflight
from obsidian_to_substack.obsidian_syntax import transform_obsidian_syntax
from obsidian_to_substack.svg_export import export_all_svgs, validate_png
from obsidian_to_substack.table_handler import (
    extract_tables,
    replace_tables_with_images,
)
from obsidian_to_substack.render_html import (
    extract_leading_title,
    render_to_html,
    strip_duplicate_title,
    strip_unsupported_elements,
    wrap_html,
)

logger = logging.getLogger(__name__)


def slugify(name: str) -> str:
    """Convert a filename to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"\.md$", "", slug)
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def convert_article(
    input_path: str,
    output_dir: str,
    svg_dir: str | None = None,
    dpi: int = 192,
    dry_run: bool = False,
) -> dict:
    """Run the full conversion pipeline on a single article.

    Returns a dict with paths to all generated files and metadata.
    """
    source = Path(input_path)
    if not source.exists():
        raise FileNotFoundError(f"Article not found: {input_path}")

    raw_text = source.read_text(encoding="utf-8")
    slug = slugify(source.name)
    article_output = Path(output_dir) / slug

    if dry_run:
        metadata, body = parse_frontmatter(raw_text)
        tables = extract_tables(body)
        svg_count = 0
        if svg_dir:
            svg_path = Path(svg_dir)
            svg_count = len(list(svg_path.glob("*.svg"))) if svg_path.is_dir() else 0
        return {
            "slug": slug,
            "metadata": metadata,
            "table_count": len(tables),
            "svg_count": svg_count,
            "dry_run": True,
        }

    article_output.mkdir(parents=True, exist_ok=True)

    metadata, body = parse_frontmatter(raw_text)

    # Resolution order: the stripped leading H1, then a frontmatter title,
    # then the filename slug. The H1 outranks a frontmatter title because
    # Obsidian sources in this corpus carry no frontmatter title and the H1
    # is the live, author-maintained heading; the frontmatter key stays as
    # the deliberate override for a source that does set one. This single
    # resolved value feeds the head title element, wrap_html, the written
    # metadata.json, and the CLI's Title line, so none of them can drift
    # apart.
    authored_title = extract_leading_title(body) or metadata.get("title", "")
    resolved_title = authored_title or source.stem.replace("-", " ")

    # Preflight cannot see which source won — the rendered <title> looks the
    # same either way — so the fallback is reported to it explicitly (GRD-02).
    title_from_slug = not authored_title

    image_map: dict[str, str] = {}
    if svg_dir is None:
        svg_dir = str(source.parent / "svg")
    if Path(svg_dir).is_dir():
        image_map = export_all_svgs(svg_dir, str(article_output), scale=dpi / 96)

    valid_pngs = {}
    for name, png_path in image_map.items():
        if validate_png(png_path):
            valid_pngs[name] = png_path
        else:
            logger.warning("Invalid PNG generated for %s, skipping", name)
    image_map = valid_pngs

    # Embeds that already name a raster file are not rasterized by
    # export_all_svgs, so copy them in — otherwise the <img src> points at a
    # file that is not next to article.html and pastes broken (DIAG-02).
    search_dirs = [source.parent, Path(svg_dir)] if svg_dir else [source.parent]
    copied = copy_raster_embeds(body, search_dirs, str(article_output))
    image_map.update(copied)
    body = rewrite_image_refs(body, copied)

    tables = extract_tables(body)
    body = replace_tables_with_images(
        body, tables, str(article_output), scale=dpi / 96
    )

    body = transform_obsidian_syntax(body, image_map=image_map)

    html_body = render_to_html(body)
    html_body, _ = strip_duplicate_title(html_body, resolved_title)
    html_doc = wrap_html(html_body, title=resolved_title)
    html_doc = strip_unsupported_elements(html_doc)

    html_path = article_output / "article.html"
    html_path.write_text(html_doc, encoding="utf-8")

    # New dict — never mutate the parsed metadata in place. This overwrites a
    # frontmatter title in the emitted metadata.json; no corpus article has
    # one, so this is theoretical, and the emitted file should describe the
    # article as converted.
    written_metadata = {**metadata, "title": resolved_title}
    meta_path = article_output / "metadata.json"
    meta_path.write_text(
        json.dumps(written_metadata, indent=2, default=str), encoding="utf-8"
    )

    warnings = preflight.check(
        html_doc, article_output, title_from_slug=title_from_slug
    )

    result = {
        "slug": slug,
        "title": resolved_title,
        "html_path": str(html_path),
        "metadata_path": str(meta_path),
        "png_files": list(image_map.values()),
        "table_count": len(tables),
        "output_dir": str(article_output),
        "warnings": warnings,
    }

    logger.info("Converted: %s → %s", source.name, article_output)
    return result


def convert_directory(
    dir_path: str,
    output_dir: str,
    svg_dir: str | None = None,
    dpi: int = 192,
    dry_run: bool = False,
) -> list[dict]:
    """Convert all .md files in a directory."""
    directory = Path(dir_path)
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {dir_path}")

    results = []
    for md_file in sorted(directory.glob("*.md")):
        try:
            result = convert_article(
                str(md_file),
                output_dir,
                svg_dir=svg_dir,
                dpi=dpi,
                dry_run=dry_run,
            )
            results.append(result)
        except Exception as exc:
            logger.error("Failed to convert %s: %s", md_file.name, exc)
            results.append({"file": str(md_file), "error": str(exc)})

    return results


def format_result_lines(result: dict) -> list[str]:
    """Format the per-article success output as a list of printable lines.

    Extracted from main()'s success branch so the line order can be pinned
    by a test without spawning a subprocess. Order: slug, Title (directly
    below the slug and ahead of any preflight warnings — a noisy preflight
    run would otherwise bury the one line the author is here to copy),
    preflight report (appended only when non-empty; it embeds its own
    newlines), HTML, PNGs, Tables. Labels are padded to a shared column so
    all four values line up.
    """
    lines = [f"  {result['slug']}/"]
    lines.append(f"    {'Title:':<8}{result.get('title', '')}")

    report_text = preflight.report(result.get("warnings", []))
    if report_text:
        lines.append(report_text)

    lines.append(f"    {'HTML:':<8}{result['html_path']}")
    lines.append(f"    {'PNGs:':<8}{len(result['png_files'])} images")
    lines.append(f"    {'Tables:':<8}{result['table_count']} CSV exports")
    return lines


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="obsidian-to-substack",
        description="Convert Obsidian Markdown articles to Substack-compatible HTML",
    )
    parser.add_argument(
        "directory",
        help="Path to Obsidian article directory to process",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory (default: ./output/)",
    )
    parser.add_argument(
        "--svg-dir",
        default=None,
        help="SVG source directory override (default: <directory>/svg/)",
    )
    parser.add_argument(
        "--file",
        default=None,
        dest="single_file",
        help="Process a single .md file instead of whole directory",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=192,
        help="PNG export DPI (default: 192)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open HTML output in default browser",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy HTML to clipboard for pasting into Substack (requires xclip)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        if args.single_file:
            input_path = str(Path(args.directory) / args.single_file)
            result = convert_article(
                input_path,
                args.output_dir,
                svg_dir=args.svg_dir,
                dpi=args.dpi,
                dry_run=args.dry_run,
            )
            results = [result]
        else:
            results = convert_directory(
                args.directory,
                args.output_dir,
                svg_dir=args.svg_dir,
                dpi=args.dpi,
                dry_run=args.dry_run,
            )
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    for result in results:
        if "error" in result:
            print(f"  FAILED: {result['file']} — {result['error']}")
        elif result.get("dry_run"):
            print(f"  [DRY RUN] {result['slug']}: {result['table_count']} tables, {result['svg_count']} SVGs")
        else:
            for line in format_result_lines(result):
                print(line)

    if args.open_browser and not args.dry_run:
        for result in results:
            html_path = result.get("html_path")
            if html_path:
                webbrowser.open(f"file://{Path(html_path).resolve()}")
                break

    if args.copy and not args.dry_run:
        for result in results:
            html_path = result.get("html_path")
            if html_path:
                copy_html_to_clipboard(html_path)
                copy_title_to_primary(result.get("title", ""))
                break


def _inline_images(html_content: str, base_dir: Path) -> str:
    """Replace local <img src="..."> references with base64 data URIs.

    This ensures images survive clipboard paste into rich-text editors
    like Substack, which cannot resolve local file paths.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith(("http://", "https://", "data:")):
            continue
        img_path = base_dir / src
        if not img_path.is_file():
            logger.warning("Image not found for inlining: %s", img_path)
            continue
        mime_type = mimetypes.guess_type(str(img_path))[0] or "image/png"
        encoded = base64.b64encode(img_path.read_bytes()).decode("ascii")
        img["src"] = f"data:{mime_type};base64,{encoded}"

    return str(soup)


def copy_html_to_clipboard(html_path: str) -> None:
    """Copy HTML file content to the system clipboard as rich text.

    Uses xclip with text/html MIME type so Substack's editor
    pastes it as formatted content rather than raw markup.
    Images are inlined as base64 data URIs so they survive the paste.
    """
    if not shutil.which("xclip"):
        print(
            "Error: xclip is required for --copy. Install it with:\n"
            "  sudo apt install xclip",
            file=sys.stderr,
        )
        sys.exit(1)

    html_path_obj = Path(html_path)
    html_content = html_path_obj.read_text(encoding="utf-8")
    html_content = _inline_images(html_content, html_path_obj.parent)

    failure = _run_xclip(
        ["xclip", "-selection", "clipboard", "-t", "text/html"],
        html_content.encode("utf-8"),
    )
    if failure is not None:
        print(f"Error: clipboard copy failed: {failure}", file=sys.stderr)
        sys.exit(1)

    print("  Body on the clipboard — Ctrl+V into Substack's body")


def copy_title_to_primary(title: str) -> None:
    """Put the resolved title on X11's PRIMARY selection as plain text.

    Substack does not hoist a leading H1 into its title field — probed
    directly on 2026-08-08, the heading lands in the body and the title bar
    stays empty. So the title has to be pasted by hand, and X11 holds only one
    clipboard: copying the printed title out of the terminal would destroy the
    body HTML that `--copy` just placed there.

    PRIMARY is independent of CLIPBOARD, so a single run can hand over both —
    Ctrl+V for the body, middle-click for the title.

    Failure is deliberately non-fatal: a missing title is an inconvenience, a
    lost body payload is a wasted run.
    """
    if not title:
        return

    if not shutil.which("xclip"):
        return

    failure = _run_xclip(
        ["xclip", "-selection", "primary"],
        title.encode("utf-8"),
    )
    if failure is not None:
        print(
            f"Warning: could not put the title on the primary selection: {failure}\n"
            f"         Copy it from the Title line above instead.",
            file=sys.stderr,
        )
        return

    print("  Title on the primary selection — middle-click into the title field")


def _run_xclip(argv: list[str], payload: bytes) -> str | None:
    """Hand `payload` to xclip. Returns None on success, else the error text.

    xclip must not inherit our stdout/stderr. An X11 selection is owned by a
    live process: xclip forks a background child to serve the selection and the
    parent exits immediately. That child keeps any inherited descriptor open
    for as long as it owns the selection, so when our output is a pipe the
    reader never sees EOF and the caller stalls indefinitely — even though this
    process has already exited. A terminal has no EOF to wait for, which is why
    this only bites scripted use.

    stderr goes to a temp file rather than DEVNULL so xclip's own diagnostics
    survive, and rather than PIPE because reading a pipe to EOF would
    reintroduce the very stall being avoided.
    """
    with tempfile.TemporaryFile() as err_file:
        try:
            subprocess.run(
                argv,
                input=payload,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=err_file,
            )
        except subprocess.CalledProcessError as exc:
            err_file.seek(0)
            detail = err_file.read().decode("utf-8", "replace").strip()
            return detail or str(exc)

    return None


if __name__ == "__main__":
    main()
