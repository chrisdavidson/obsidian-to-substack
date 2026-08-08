"""Convert SVG files to PNG for Substack upload."""

import logging
import subprocess
from pathlib import Path

import cairosvg
from PIL import Image

logger = logging.getLogger(__name__)


def export_svg_to_png(
    svg_path: str,
    output_dir: str,
    scale: float = 2.0,
    dpi: int = 192,
) -> str:
    """Convert a single SVG to PNG. Uses CairoSVG with Inkscape fallback.

    Returns the path to the generated PNG file.
    Raises FileNotFoundError if the SVG does not exist.
    """
    svg = Path(svg_path)
    if not svg.exists():
        raise FileNotFoundError(f"SVG not found: {svg_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / svg.with_suffix(".png").name

    try:
        cairosvg.svg2png(
            url=str(svg.resolve()),
            write_to=str(png_path),
            scale=scale,
        )
        logger.info("CairoSVG exported: %s → %s", svg.name, png_path.name)
    except Exception as cairo_exc:
        logger.warning("CairoSVG failed for %s: %s. Trying Inkscape.", svg.name, cairo_exc)
        try:
            subprocess.run(
                [
                    "inkscape",
                    str(svg.resolve()),
                    f"--export-type=png",
                    f"--export-dpi={dpi}",
                    f"--export-filename={png_path}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Inkscape exported: %s → %s", svg.name, png_path.name)
        except (subprocess.CalledProcessError, FileNotFoundError) as ink_exc:
            raise RuntimeError(
                f"Both CairoSVG and Inkscape failed for {svg.name}"
            ) from ink_exc

    return str(png_path)


def export_all_svgs(
    svg_dir: str,
    output_dir: str,
    scale: float = 2.0,
) -> dict[str, str]:
    """Export all SVGs in a directory to PNG.

    Returns a mapping of {original_filename: png_path}.
    """
    svg_directory = Path(svg_dir)
    if not svg_directory.is_dir():
        logger.warning("SVG directory not found: %s", svg_dir)
        return {}

    image_map: dict[str, str] = {}
    for svg_file in sorted(svg_directory.glob("*.svg")):
        try:
            png_path = export_svg_to_png(str(svg_file), output_dir, scale=scale)
            image_map[svg_file.name] = png_path
        except (FileNotFoundError, RuntimeError) as exc:
            logger.error("Failed to export %s: %s", svg_file.name, exc)

    return image_map


def validate_png(png_path: str, max_mb: float = 10.0) -> bool:
    """Validate a PNG file is a real image and under the size limit."""
    path = Path(png_path)
    if not path.exists():
        return False

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        logger.warning("PNG exceeds %.1f MB limit: %s (%.2f MB)", max_mb, path.name, size_mb)
        return False

    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False
