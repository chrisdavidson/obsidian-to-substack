"""CLI entry point for Obsidian-to-Substack conversion."""

import argparse
import base64
import json
import logging
import mimetypes
import re
import sys
import webbrowser
from pathlib import Path

from obsidian_to_substack.frontmatter import parse_frontmatter
from obsidian_to_substack.image_assets import (
    copy_raster_embeds,
    find_image,
    referenced_images,
    referenced_svgs,
    rewrite_image_refs,
)
from obsidian_to_substack import clipboard, preflight
from obsidian_to_substack.obsidian_syntax import (
    strip_obsidian_comments,
    transform_obsidian_syntax,
)
from obsidian_to_substack.svg_export import export_all_svgs, svg_sources, validate_png
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


def _resolve_default_svg_dir(source_dir: Path, slug: str) -> Path:
    """Pick the default SVG source directory when the caller supplies none.

    Pure: reads the filesystem, returns a new Path, mutates nothing.

    (a) Why the per-slug directory is preferred. The vault moved to
    per-article subdirectories, <source_dir>/svg/<slug>/*.svg. The flat
    parent <source_dir>/svg/ still exists (it holds every article's
    subdirectory), so a caller's is_dir() check on the flat directory still
    passes even though this article's diagrams are not directly inside it.
    export_all_svgs globs *.svg non-recursively, so it finds nothing there,
    image_map comes back empty, and replace_image_embeds still performs the
    .svg -> .png embed swap unconditionally — the written HTML ends up with
    <img> tags for files nobody generated. Measured on a real article: six
    such missing_image warnings (DIAG-02). Preferring the per-slug directory
    when it exists closes the gap at the source.

    (b) Why export_all_svgs' glob stays non-recursive. It flattens every SVG
    to its basename in the output directory. A recursive sweep over the flat
    svg/ would export every article's diagrams into every article's output
    dir and collide on any shared basename. The per-slug preference here is
    the whole fix — the glob itself is deliberately untouched.

    (c) Why an explicit svg_dir is never probed. It is the operator's
    override; the caller of this helper only reaches it on the None branch.
    Probing an explicit path for a same-named per-slug sibling would let a
    stale nested directory silently outrank a directory the caller named on
    purpose.

    (d) Why the flat directory stays in convert_article's search_dirs for
    raster embeds even after this helper picks the per-slug directory. Only
    SVGs moved into per-slug subdirectories — a raster image the article
    embeds directly may still sit in the flat svg/. Dropping the flat
    directory from the raster search would reintroduce the same
    broken-<img src> defect this fix closes, from the other side.

    is_dir() is the sole test — not "exists and holds at least one .svg". A
    contains-check would silently fall back to the flat directory on a
    typo'd per-slug directory name, hiding the mistake; is_dir() lets that
    empty case surface loudly instead, as a missing_image preflight warning.
    """
    nested = source_dir / "svg" / slug
    if nested.is_dir():
        return nested
    return source_dir / "svg"


def _resolve_search_dirs(
    source_dir: Path, svg_dir: Path, svg_dir_was_explicit: bool
) -> list[Path]:
    """The directories a raster embed is looked up in, real path and dry-run alike.

    Lifted verbatim from convert_article's raster-copy step, where it used
    to be built inline. 260809-plg existed because `dry_run` carried its own
    copy of the SVG-directory-resolution rule instead of calling
    `_resolve_default_svg_dir`; extracting this rule the same way keeps
    `unresolved_image_refs` from growing a second copy of THIS one.

    Embeds that already name a raster file are not rasterized by
    export_all_svgs, so they still need to be found some other way —
    otherwise the <img src> points at a file that is not next to
    article.html and pastes broken (DIAG-02).

    The result is a strict superset of just [source_dir, svg_dir]: the
    article's own directory and the resolved svg_dir are always included;
    the flat <article dir>/svg is folded in too, but only when svg_dir was
    defaulted (an explicit --svg-dir is the operator's override and gets
    nothing added) and only when it differs from the already-resolved
    directory (avoiding a redundant duplicate when the default resolved to
    the flat directory in the first place). This is what keeps a flat
    raster embed findable even when the per-slug SVG directory wins — see
    _resolve_default_svg_dir's point (d). It does not reintroduce the
    non-recursive-glob hazard: copy_raster_embeds and find_image only look
    for files an embed actually names, so a shared flat directory can never
    pull another article's diagrams into this article's output.
    """
    search_dirs = [source_dir, svg_dir]
    if not svg_dir_was_explicit:
        flat_svg_dir = source_dir / "svg"
        if flat_svg_dir not in search_dirs:
            search_dirs.append(flat_svg_dir)
    return search_dirs


def unresolved_image_refs(
    body: str, source_dir: Path, svg_dir: Path, svg_dir_was_explicit: bool
) -> list[str]:
    """Return every embed name --dry-run predicts will paste broken (D-02).

    Pure: reads the filesystem via svg_sources/find_image, returns a new
    list, mutates nothing.

    Extracts from `strip_obsidian_comments(body)`, not from `body` itself —
    this is the call a later reader will most plausibly undo, so it is
    commented at length. The real path's raster copying runs pre-strip and
    that is deliberate and already recorded elsewhere (an embed inside a
    comment still rasterizes to disk, leaving an orphan file, and the
    project accepted that). But the question THIS function answers is which
    references will *paste* broken, and the pasted <img> set is decided by
    `replace_image_embeds`, which runs INSIDE `transform_obsidian_syntax`
    AFTER `strip_obsidian_comments`. Extracting pre-strip would report a
    commented-out embed that never becomes an <img> — a false positive, and
    this is a check, not a transformation: "fail closed and be loud"
    governs transformations, but every check in preflight.py refuses false
    positives on purpose, and this function follows that half of the house
    convention instead. What regresses if someone switches this to `body`
    to "match the real path": the check starts reporting defects the
    author cannot act on, and the noise preflight was noise-controlled to
    avoid comes back through the side door.

    The strongest argument FOR sharing the transform, stated here because
    it is easy to miss: the fail-closed path composes correctly for free.
    With an odd marker count `strip_obsidian_comments` strips nothing, so
    this function extracts the commented embed and reports it — and the
    real run also strips nothing, so that embed genuinely does become an
    <img> and genuinely does paste broken. A hand-rolled "skip anything
    between %% markers" shortcut would get that case wrong in the silent
    direction.

    SVG half: a referenced_svgs() name is unresolved when its basename is
    not among svg_sources(svg_dir)'s basenames — exactly the image_map keys
    export_all_svgs would produce, which is exactly what
    replace_image_embeds looks up before falling back to the unconditional
    .svg -> .png rewrite. That fallback is the DIAG-02 mechanism, and this
    membership test is its predicate. Basenames are compared, not the raw
    embed text: replace_image_embeds ends with
    `src = os.path.basename(raw_src)` — it basenames unconditionally,
    AFTER the fallback. So `![[svg/diagram.svg]]` misses the image_map
    lookup, falls back to `svg/diagram.png`, and is emitted as
    `diagram.png` — which exists when `diagram.svg` was in the resolved
    directory. Comparing the raw name would report that as broken: a false
    positive of exactly the class the paragraph above argues against.
    (Measured today: 0 of the 45 distinct `![[...svg]]` embeds across the
    two vault article directories carry a path prefix, so the bug is
    latent, not live.)

    Raster half: a referenced_images() name is unresolved when
    find_image(name, _resolve_search_dirs(...)) returns None — the same
    function copy_raster_embeds uses to make the same judgement. Sharing it
    is correct even though find_image's basename fallback does a `**/`
    recursive glob per directory, the most expensive thing dry-run does —
    if that cost ever bites, the fix is to measure it, not to fork the
    rule.

    One boundary this function cannot see, recorded here so a later reader
    files it as a limit rather than a bug: an SVG that exports but fails
    validate_png is dropped from image_map at convert_article's PNG
    validation step, and the real run then emits a broken <img> that this
    function called fine. Detecting it would require actually exporting,
    which D-02 rules out. preflight's missing_image check still catches it
    on the real run.

    Never calls copy_raster_embeds, export_all_svgs, or any other writing
    function — D-02 requires dry-run to write nothing.
    """
    stripped = strip_obsidian_comments(body)
    svg_basenames = {p.name for p in svg_sources(svg_dir)}
    search_dirs = _resolve_search_dirs(source_dir, svg_dir, svg_dir_was_explicit)

    unresolved: list[str] = []
    for name in referenced_svgs(stripped):
        if Path(name).name not in svg_basenames and name not in unresolved:
            unresolved.append(name)
    for name in referenced_images(stripped):
        if find_image(name, search_dirs) is None and name not in unresolved:
            unresolved.append(name)

    return unresolved


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
        # dry_run answers the same question the real path answers at
        # convert_article's line ~155 -- which directory holds this
        # article's SVGs -- so it asks _resolve_default_svg_dir instead of
        # deciding for itself. The two branches used to disagree: this one
        # counted only an explicitly supplied --svg-dir and reported 0 for
        # every default case, including the pre-a364bc5 flat layout. If a
        # later edit re-inlines directory logic here instead of calling the
        # shared helper, that divergence returns; check the real path's call
        # site (same helper, same two arguments) before changing either.
        #
        # svg_count means every *.svg in the resolved directory -- the exact
        # set export_all_svgs would export on the real run, orphans
        # included, because dry-run's contract is to predict that run
        # rather than to be cleverer than it. It does NOT mean raster
        # embeds (it never has) and it does NOT mean the real run's
        # png_files length -- that also includes table PNGs and copied
        # rasters, and validate_png can drop an export, so the two are
        # different quantities by construction and no test should
        # cross-compare them.
        #
        # The guard below moved from `if svg_dir:` to `if svg_dir is None:`.
        # One honest semantic change rides along: a caller passing
        # svg_dir="" used to get 0; it now resolves to Path("."), which
        # is_dir() passes, and globs the working directory -- because that
        # is precisely what the real path already does at line ~154. No
        # test pins the empty-string case; it is a consequence of sharing
        # the rule, not a feature in its own right.
        #
        # svg_dir_was_explicit has to be captured BEFORE the defaulting
        # line immediately below, exactly like the real path does — it
        # feeds unresolved_image_refs' directory-resolution rule, and
        # capturing it after defaulting would always read True.
        svg_dir_was_explicit = svg_dir is not None
        if svg_dir is None:
            svg_dir = str(_resolve_default_svg_dir(source.parent, slug))
        svg_path = Path(svg_dir)
        svg_count = len(svg_sources(svg_path))

        # unresolved_images is the D-02 finding: every embed name that will
        # not resolve, and so will paste broken, computed the same way
        # (and sharing the same directory-resolution rule) as the real
        # run — see unresolved_image_refs' docstring.
        unresolved_images = unresolved_image_refs(
            body, source.parent, svg_path, svg_dir_was_explicit
        )
        return {
            "slug": slug,
            "metadata": metadata,
            "table_count": len(tables),
            "svg_count": svg_count,
            "unresolved_images": unresolved_images,
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
    svg_dir_was_explicit = svg_dir is not None
    if svg_dir is None:
        svg_dir = str(_resolve_default_svg_dir(source.parent, slug))
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
    # See _resolve_search_dirs' docstring for the shape of the rule; the
    # long comment that used to live inline here moved with the code when
    # it was extracted so dry-run's unresolved_image_refs could share it.
    search_dirs = _resolve_search_dirs(source.parent, Path(svg_dir), svg_dir_was_explicit)
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

    # The fidelity check gets the RAW file text, not `body` — `body` has
    # already been through frontmatter splitting and image rewriting by now,
    # and comparing against it would silently exempt anything those stages
    # dropped. fidelity re-derives the frontmatter block itself.
    #
    # `tables` still holds the rows extracted above, before
    # replace_tables_with_images consumed them. That is the evidence that lets
    # table prose count as relocated into the PNG rather than lost — a row
    # extraction dropped is not in here, and is reported.
    warnings = preflight.check(
        html_doc,
        article_output,
        title_from_slug=title_from_slug,
        source_markdown=raw_text,
        resolved_title=resolved_title,
        tables=[rows for _start, _end, _raw, rows in tables],
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
        help=(
            "SVG source directory override "
            "(default: <directory>/svg/<slug>/ when it exists, "
            "otherwise <directory>/svg/)"
        ),
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
        help=(
            "Show what would be done without writing files, including "
            "which embedded image references will not resolve"
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help=(
            "Copy HTML to clipboard for pasting into Substack (needs xclip "
            "on Linux, osascript on macOS, PowerShell on Windows). Refuses "
            "when preflight found a warning; see --force."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Copy anyway when preflight warned (only meaningful with "
            "--copy)"
        ),
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
            # D-02: report unresolvable image references, the one finding
            # that would have caught the DIAG-02 incident before a real
            # conversion ran. Exit stays 0 here -- D-01 says "exit
            # non-zero" for --copy, D-02 says "report" for --dry-run, and
            # the author chose those two different verbs on purpose.
            unresolved = result.get("unresolved_images") or []
            if unresolved:
                print(
                    f"    {len(unresolved)} image reference(s) will not "
                    "resolve and will paste broken:"
                )
                for name in unresolved:
                    print(f"      {name}")
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
        # Select the article this run is about ONCE, and feed that single
        # object to both the warning gate below and the copy itself — never
        # scan `results` twice for two notions of "the article this run is
        # about". That duplication is exactly what 260809-plg had to unpick
        # when `dry_run` carried its own copy of the SVG-directory logic;
        # writing it twice here would just recreate the same class of bug in
        # a new place.
        selected = next((r for r in results if r.get("html_path")), None)

        if selected is not None:
            warning_count = len(selected.get("warnings", []))

            # D-01: `--copy` refuses to write anything when preflight found
            # a warning on the selected article, with `--force` as the
            # escape hatch.
            #
            # Why the gate lives here and not in preflight.py or
            # convert_article: preflight.check is advisory and
            # non-corrective by a convention with history behind it (see
            # preflight.py's module docstring), and convert_article is
            # called directly by tools/ and by tests that need a result dict
            # back regardless of whether it warned. The CLI's main() is the
            # only layer that owns "did this run succeed" — it is where the
            # decision to write to the clipboard is made, so it is where the
            # decision to refuse belongs.
            #
            # Why the gate reads only the SELECTED article's warnings, not
            # every result in the run: `--copy` copies exactly one article.
            # Refusing because an unrelated article elsewhere in the same
            # directory has a warning would be the false-positive noise
            # _check_slug_title was measured down to 3/25 to avoid — and it
            # would wear the --force hatch smooth until it stopped meaning
            # anything. What regresses if a later reader "hardens" this into
            # an all-results scan: a clean single-article paste starts
            # getting refused for a neighbour's defect.
            #
            # Why the refusal also covers copy_title, not just
            # copy_html_to_clipboard: PRIMARY is a clipboard write too, and
            # D-01 says write no clipboard — CLIPBOARD and PRIMARY both.
            #
            # Why exit 1 and not a distinct code: it matches the existing
            # xclip-failure exit below (copy_html_to_clipboard,
            # _run_xclip's caller) and nothing downstream scripts a
            # distinction between the two failure reasons.
            #
            # Why --force exists at all: some warnings are known noise —
            # `slug_title` was noise-controlled to 3/25 against the
            # published corpus specifically because it cannot be eliminated
            # without also silencing genuinely bad titles. A hard block
            # here would stop a legitimate paste on exactly that noise.
            if warning_count and not args.force:
                # format_result_lines already printed the individual
                # warnings above, via preflight.report — this message names
                # only the count and the escape hatch, not the warnings
                # themselves.
                #
                # The flush is load-bearing, not tidiness. This message says
                # "(see above)" and goes to stderr, which is unbuffered;
                # stdout is block-buffered whenever it is not a tty. Without
                # the flush, a redirected or piped run (`> run.log`, `| tee`)
                # emits the refusal *before* the warnings it points at — the
                # message misdirects in precisely the runs an author keeps and
                # re-reads. Measured on the real vault article: refusal on
                # line 4, warnings from line 9. Pinned by
                # test_refusal_flushes_stdout_before_the_stderr_message, which
                # records both streams into one ordered log because capsys
                # buffers them separately and cannot see the interleaving.
                sys.stdout.flush()
                print(
                    f"Error: --copy refused — {warning_count} preflight "
                    f"warning(s) on {selected['slug']!r} (see above). "
                    "Re-run with --force to copy anyway.",
                    file=sys.stderr,
                )
                sys.exit(1)

            if warning_count:
                print(
                    f"  Copying despite {warning_count} preflight "
                    "warning(s) (--force)"
                )

            copy_html_to_clipboard(selected["html_path"])
            copy_title(selected.get("title", ""))


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
    """Copy the written article to the system clipboard as rich text.

    Reads the file, inlines its images as base64 data URIs so they survive the
    paste, and hands the result to whichever clipboard backend this platform
    has. The per-platform mechanics live in `clipboard.py`; what belongs here
    is the pipeline's own step — the file on disk is the source of truth for
    what gets copied, so what the author pastes is exactly what was written.
    """
    # Checked before the file is read so a missing tool is reported as a
    # missing tool, not as a failure three stages downstream.
    clipboard.ensure_backend()

    html_path_obj = Path(html_path)
    html_content = html_path_obj.read_text(encoding="utf-8")
    html_content = _inline_images(html_content, html_path_obj.parent)

    clipboard.copy_html(html_content)


def copy_title(title: str) -> None:
    """Hand the resolved title over for Substack's title field.

    Thin by design: the platforms differ in whether they can do this at all,
    and that judgement belongs in `clipboard.py` next to the backends.
    """
    clipboard.copy_title(title)


if __name__ == "__main__":
    main()
