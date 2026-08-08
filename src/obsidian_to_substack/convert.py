"""CLI entry point for Obsidian-to-Substack conversion."""

import argparse
import base64
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from obsidian_to_substack.frontmatter import parse_frontmatter
from obsidian_to_substack.obsidian_syntax import transform_obsidian_syntax
from obsidian_to_substack.svg_export import export_all_svgs, validate_png
from obsidian_to_substack.table_handler import (
    extract_tables,
    replace_tables_with_embeds,
    replace_tables_with_placeholders,
)
from obsidian_to_substack.render_html import render_to_html, strip_unsupported_elements, wrap_html

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
    datawrapper_token: str | None = None,
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

    tables = extract_tables(body)
    if datawrapper_token and tables:
        article_title = metadata.get("title", source.stem.replace("-", " "))
        body = replace_tables_with_embeds(
            body, tables, str(article_output),
            api_token=datawrapper_token,
            article_title=article_title,
        )
    else:
        body = replace_tables_with_placeholders(body, tables, str(article_output))

    body = transform_obsidian_syntax(body, image_map=image_map)

    html_body = render_to_html(body)
    title = metadata.get("title", source.stem.replace("-", " "))
    html_doc = wrap_html(html_body, title=title)
    html_doc = strip_unsupported_elements(html_doc)

    html_path = article_output / "article.html"
    html_path.write_text(html_doc, encoding="utf-8")

    meta_path = article_output / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")

    result = {
        "slug": slug,
        "html_path": str(html_path),
        "metadata_path": str(meta_path),
        "png_files": list(image_map.values()),
        "table_count": len(tables),
        "output_dir": str(article_output),
    }

    logger.info("Converted: %s → %s", source.name, article_output)
    return result


def convert_directory(
    dir_path: str,
    output_dir: str,
    svg_dir: str | None = None,
    dpi: int = 192,
    dry_run: bool = False,
    datawrapper_token: str | None = None,
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
                datawrapper_token=datawrapper_token,
            )
            results.append(result)
        except Exception as exc:
            logger.error("Failed to convert %s: %s", md_file.name, exc)
            results.append({"file": str(md_file), "error": str(exc)})

    return results


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
        "--datawrapper",
        action="store_true",
        help="Publish tables to Datawrapper (requires DATAWRAPPER_API_TOKEN env var)",
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

    dw_token = None
    if args.datawrapper:
        dw_token = os.environ.get("DATAWRAPPER_API_TOKEN")
        if not dw_token:
            print(
                "Error: --datawrapper requires DATAWRAPPER_API_TOKEN environment variable.\n"
                "Get a token at https://app.datawrapper.de/account/api-tokens",
                file=sys.stderr,
            )
            sys.exit(1)

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
                datawrapper_token=dw_token,
            )
            results = [result]
        else:
            results = convert_directory(
                args.directory,
                args.output_dir,
                svg_dir=args.svg_dir,
                dpi=args.dpi,
                dry_run=args.dry_run,
                datawrapper_token=dw_token,
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
            print(f"  {result['slug']}/")
            print(f"    HTML:   {result['html_path']}")
            print(f"    PNGs:   {len(result['png_files'])} images")
            print(f"    Tables: {result['table_count']} CSV exports")

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

    try:
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "text/html"],
            input=html_content.encode("utf-8"),
            check=True,
        )
        print(f"  Copied to clipboard — paste into Substack with Ctrl+V")
    except subprocess.CalledProcessError as exc:
        print(f"Error: clipboard copy failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
