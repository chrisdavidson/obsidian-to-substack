"""Tests for SVG to PNG export."""

import os
import tempfile
from pathlib import Path

import pytest

from obsidian_to_substack.svg_export import export_all_svgs, export_svg_to_png, validate_png

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestExportSvgToPng:
    def test_converts_svg_to_png(self):
        svg_path = str(FIXTURES_DIR / "sample-diagram.svg")
        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = export_svg_to_png(svg_path, tmpdir)
            assert Path(png_path).exists()
            assert png_path.endswith(".png")

    def test_missing_svg_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                export_svg_to_png("/nonexistent/file.svg", tmpdir)

    def test_output_is_valid_png(self):
        svg_path = str(FIXTURES_DIR / "sample-diagram.svg")
        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = export_svg_to_png(svg_path, tmpdir)
            assert validate_png(png_path)


class TestExportAllSvgs:
    def test_exports_all_svgs_in_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_map = export_all_svgs(str(FIXTURES_DIR), tmpdir)
            assert "sample-diagram.svg" in image_map
            assert Path(image_map["sample-diagram.svg"]).exists()

    def test_missing_directory_returns_empty(self):
        result = export_all_svgs("/nonexistent/dir", "/tmp/out")
        assert result == {}


class TestValidatePng:
    def test_valid_png(self):
        svg_path = str(FIXTURES_DIR / "sample-diagram.svg")
        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = export_svg_to_png(svg_path, tmpdir)
            assert validate_png(png_path) is True

    def test_nonexistent_file(self):
        assert validate_png("/nonexistent/file.png") is False

    def test_size_limit(self):
        svg_path = str(FIXTURES_DIR / "sample-diagram.svg")
        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = export_svg_to_png(svg_path, tmpdir)
            assert validate_png(png_path, max_mb=0.000001) is False
