"""Integration tests for the full conversion pipeline."""

import json
import re
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from obsidian_to_substack.convert import (
    _inline_images,
    convert_article,
    convert_directory,
    copy_html_to_clipboard,
    copy_title_to_primary,
    slugify,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSlugify:
    def test_basic(self):
        assert slugify("My Article Title.md") == "my-article-title"

    def test_special_chars(self):
        assert slugify("What's the Deal?.md") == "whats-the-deal"

    def test_multiple_spaces(self):
        assert slugify("Too   Many   Spaces.md") == "too-many-spaces"

    def test_already_slugged(self):
        assert slugify("already-a-slug.md") == "already-a-slug"


class TestConvertArticle:
    def test_full_pipeline(self):
        article = str(FIXTURES_DIR / "sample_article.md")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_article(
                article, tmpdir, svg_dir=str(FIXTURES_DIR)
            )
            assert "slug" in result
            assert Path(result["html_path"]).exists()
            assert Path(result["metadata_path"]).exists()

            html = Path(result["html_path"]).read_text()
            assert "<!DOCTYPE html>" in html
            assert "![[" not in html
            assert "[[" not in html

            # The fixture's sole `# Sample Article Title` H1 is the article
            # title. Substack renders its own title above the body, so it must
            # survive in <title> but not as a duplicate heading in the body.
            assert "<title>" in html
            assert "<h1>Sample Article Title</h1>" not in html

            metadata = json.loads(Path(result["metadata_path"]).read_text())
            assert "tags" in metadata

    def test_png_files_generated(self):
        article = str(FIXTURES_DIR / "sample_article.md")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_article(
                article, tmpdir, svg_dir=str(FIXTURES_DIR)
            )
            assert len(result["png_files"]) >= 1
            for png in result["png_files"]:
                assert Path(png).exists()

    def test_table_csv_generated(self):
        article = str(FIXTURES_DIR / "sample_article.md")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_article(
                article, tmpdir, svg_dir=str(FIXTURES_DIR)
            )
            assert result["table_count"] == 1
            csv_files = list(Path(result["output_dir"]).glob("*.csv"))
            assert len(csv_files) == 1

    def test_missing_article_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                convert_article("/nonexistent/article.md", tmpdir)

    def test_dry_run(self):
        article = str(FIXTURES_DIR / "sample_article.md")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_article(
                article, tmpdir, svg_dir=str(FIXTURES_DIR), dry_run=True
            )
            assert result["dry_run"] is True
            assert not list(Path(tmpdir).rglob("*.html"))


class TestFootnoteEndToEnd:
    def test_torture_fixture_footnote_survives_to_written_html(self, tmp_path):
        # The shipped file is the artifact — asserting on render_to_html
        # output alone would have missed F2 (the footnotes section getting
        # deleted downstream by strip_unsupported_elements).
        article = str(FIXTURES_DIR / "torture_test" / "torture-test.md")
        result = convert_article(article, str(tmp_path))
        html = Path(result["html_path"]).read_text(encoding="utf-8")
        assert "Z39.19-2005" in html
        assert "fnref" in html
        assert "[^1]" not in html


class TestObsidianCommentEndToEnd:
    def test_torture_fixture_comments_are_absent_from_written_html(self, tmp_path):
        # The shipped file is the artifact -- asserting on
        # transform_obsidian_syntax output alone would miss a downstream
        # stage silently reintroducing the comment text, or the preflight
        # check firing on the fenced counter-example it must stay silent on.
        article = str(FIXTURES_DIR / "torture_test" / "torture-test.md")
        result = convert_article(article, str(tmp_path))
        html = Path(result["html_path"]).read_text(encoding="utf-8")

        assert "This inline note must never reach Substack" not in html
        assert "This working note must never reach Substack either" not in html

        # The prose immediately around each comment survives untouched.
        assert "Before the block: this paragraph must survive" in html
        assert "After the block: this paragraph must also survive" in html

        # The fenced counter-example is exempt from stripping and survives
        # visibly -- the only end-to-end proof of the code/pre skip.
        assert (
            "this literal marker documents the syntax and must survive visibly"
            in html
        )

        assert not any(w.check == "obsidian_comment" for w in result["warnings"])


class TestSlugTitleEndToEnd:
    """convert_article must hand preflight the fact that the fallback fired.

    Preflight sees only the rendered HTML, which cannot distinguish a title
    taken from the filename from one the author set deliberately.
    """

    def _write(self, directory, name, body):
        source = Path(directory) / name
        source.write_text(body, encoding="utf-8")
        return str(source)

    def test_slug_filename_with_no_title_source_warns(self, tmp_path):
        # No frontmatter title, and no H1 at all -- opens at H2.
        article = self._write(
            tmp_path, "article-with-no-title.md", "## Introduction\n\nBody.\n"
        )
        result = convert_article(article, str(tmp_path / "out"))
        assert result["title"] == "article with no title"
        assert any(w.check == "slug_title" for w in result["warnings"])

    def test_several_h1s_also_reaches_the_fallback_and_warns(self, tmp_path):
        # The other fallback path: a leading H1 that is not the sole H1.
        # 19 of the 25 published articles look like this.
        article = self._write(
            tmp_path, "several-h1-headings.md", "# One\n\na\n\n# Two\n\nb\n"
        )
        result = convert_article(article, str(tmp_path / "out"))
        assert any(w.check == "slug_title" for w in result["warnings"])

    def test_filename_that_reads_as_a_title_does_not_warn(self, tmp_path):
        article = self._write(
            tmp_path, "A Capitalised Filename.md", "## Introduction\n\nBody.\n"
        )
        result = convert_article(article, str(tmp_path / "out"))
        assert not any(w.check == "slug_title" for w in result["warnings"])

    def test_frontmatter_title_suppresses_the_warning(self, tmp_path):
        article = self._write(
            tmp_path,
            "article-with-no-title.md",
            '---\ntitle: "A Title Set In Frontmatter"\n---\n\n## Introduction\n\nBody.\n',
        )
        result = convert_article(article, str(tmp_path / "out"))
        assert result["title"] == "A Title Set In Frontmatter"
        assert not any(w.check == "slug_title" for w in result["warnings"])

    def test_sole_h1_suppresses_the_warning(self, tmp_path):
        article = self._write(
            tmp_path, "article-with-no-title.md", "# A Real Title\n\nBody.\n"
        )
        result = convert_article(article, str(tmp_path / "out"))
        assert not any(w.check == "slug_title" for w in result["warnings"])


class TestConvertDirectory:
    def test_processes_md_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = convert_directory(
                str(FIXTURES_DIR), tmpdir, svg_dir=str(FIXTURES_DIR)
            )
            md_files = list(FIXTURES_DIR.glob("*.md"))
            assert len(results) == len(md_files)

    def test_invalid_directory_raises(self):
        with pytest.raises(NotADirectoryError):
            convert_directory("/nonexistent/dir", "/tmp/out")


class TestInlineImages:
    def test_replaces_local_src_with_data_uri(self, tmp_path):
        # Create a tiny 1x1 red PNG
        from PIL import Image

        img = Image.new("RGB", (1, 1), color="red")
        img.save(tmp_path / "chart.png")

        html = '<html><body><img src="chart.png" alt="chart"></body></html>'
        result = _inline_images(html, tmp_path)

        assert 'src="data:image/png;base64,' in result
        assert 'src="chart.png"' not in result

    def test_skips_http_urls(self, tmp_path):
        html = '<img src="https://example.com/img.png">'
        result = _inline_images(html, tmp_path)
        assert 'src="https://example.com/img.png"' in result

    def test_skips_data_uris(self, tmp_path):
        html = '<img src="data:image/png;base64,abc">'
        result = _inline_images(html, tmp_path)
        assert 'src="data:image/png;base64,abc"' in result

    def test_missing_image_left_unchanged(self, tmp_path):
        html = '<img src="missing.png">'
        result = _inline_images(html, tmp_path)
        assert 'src="missing.png"' in result

    def test_multiple_images_inlined(self, tmp_path):
        from PIL import Image

        for name in ("a.png", "b.png"):
            img = Image.new("RGB", (1, 1), color="blue")
            img.save(tmp_path / name)

        html = '<img src="a.png"><img src="b.png">'
        result = _inline_images(html, tmp_path)

        assert result.count("data:image/png;base64,") == 2


class TestCopyHtmlToClipboard:
    def test_xclip_not_installed(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(SystemExit):
                copy_html_to_clipboard("/tmp/fake.html")

    def test_calls_xclip_with_html_mime_type(self, tmp_path):
        html_file = tmp_path / "article.html"
        html_file.write_text("<p>Hello</p>", encoding="utf-8")

        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as mock_run,
        ):
            copy_html_to_clipboard(str(html_file))
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == ["xclip", "-selection", "clipboard", "-t", "text/html"]
            assert call_args[1]["check"] is True

    def test_xclip_stdio_is_not_inherited(self, tmp_path):
        """xclip must not inherit our stdout/stderr.

        X11 selections are owned by a live process: xclip forks a background
        child to serve the clipboard and the parent exits. That child holds any
        inherited descriptor open for as long as it owns the selection, so if
        our output is a pipe the reader never sees EOF and the caller stalls
        forever — even though this process has already exited.
        """
        html_file = tmp_path / "article.html"
        html_file.write_text("<p>Hello</p>", encoding="utf-8")

        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as mock_run,
        ):
            copy_html_to_clipboard(str(html_file))
            kwargs = mock_run.call_args[1]
            assert kwargs["stdout"] is subprocess.DEVNULL
            # Not None (inherit), and not PIPE — reading a pipe to EOF would
            # reintroduce the same stall, since the daemon child holds it open.
            assert kwargs["stderr"] is not None
            assert kwargs["stderr"] is not subprocess.PIPE

    def test_reports_xclip_stderr_on_failure(self, tmp_path, capsys):
        html_file = tmp_path / "article.html"
        html_file.write_text("<p>Hello</p>", encoding="utf-8")

        def fail(*args, **kwargs):
            kwargs["stderr"].write(b"Error: Can't open display:\n")
            raise subprocess.CalledProcessError(1, "xclip")

        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run", side_effect=fail),
        ):
            with pytest.raises(SystemExit):
                copy_html_to_clipboard(str(html_file))

        assert "Can't open display" in capsys.readouterr().err

    def test_inlines_images_before_copy(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (1, 1), color="green")
        img.save(tmp_path / "photo.png")

        html_file = tmp_path / "article.html"
        html_file.write_text(
            '<html><body><img src="photo.png"></body></html>',
            encoding="utf-8",
        )

        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as mock_run,
        ):
            copy_html_to_clipboard(str(html_file))
            copied_html = mock_run.call_args[1]["input"].decode("utf-8")
            assert "data:image/png;base64," in copied_html
            assert 'src="photo.png"' not in copied_html


class TestCopyTitleToPrimary:
    """The title rides X11's PRIMARY selection, not the clipboard.

    Substack does not hoist a leading H1 into its title field (probed
    2026-08-08), so the title must be pasted by hand. X11 holds one clipboard,
    so copying the printed title out of the terminal would destroy the body
    HTML that --copy just placed there. PRIMARY is independent of CLIPBOARD, so
    one run can hand over both: Ctrl+V for the body, middle-click for the title.
    """

    def test_uses_primary_selection_as_plain_text(self, tmp_path):
        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as mock_run,
        ):
            copy_title_to_primary("Torture Test: Every Construct")
            argv = mock_run.call_args[0][0]
            assert argv == ["xclip", "-selection", "primary"]
            # No -t text/html: the title field takes plain text.
            assert "-t" not in argv
            assert mock_run.call_args[1]["input"] == b"Torture Test: Every Construct"

    def test_stdio_is_not_inherited(self, tmp_path):
        # Same daemon-holds-the-pipe stall as the clipboard copy; see
        # TestCopyHtmlToClipboard.test_xclip_stdio_is_not_inherited.
        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as mock_run,
        ):
            copy_title_to_primary("A Title")
            kwargs = mock_run.call_args[1]
            assert kwargs["stdout"] is subprocess.DEVNULL
            assert kwargs["stderr"] is not None
            assert kwargs["stderr"] is not subprocess.PIPE

    def test_failure_is_not_fatal(self, capsys):
        """A lost title is an inconvenience; a lost body is a wasted run."""

        def fail(*args, **kwargs):
            kwargs["stderr"].write(b"Error: Can't open display:\n")
            raise subprocess.CalledProcessError(1, "xclip")

        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run", side_effect=fail),
        ):
            copy_title_to_primary("A Title")  # must not raise SystemExit

        assert "Can't open display" in capsys.readouterr().err

    def test_empty_title_is_skipped(self):
        with (
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as mock_run,
        ):
            copy_title_to_primary("")
            mock_run.assert_not_called()


class TestFidelityWiring:
    """convert_article must surface a fidelity loss, not just be able to detect one.

    The unit tests prove the comparator works; these prove it is actually
    reached from the pipeline with the right evidence in hand.
    """

    def _write(self, tmp_path: Path, text: str) -> Path:
        source = tmp_path / "article.md"
        source.write_text(text, encoding="utf-8")
        return source

    def test_faithful_conversion_raises_no_fidelity_warning(self, tmp_path):
        source = self._write(
            tmp_path,
            "# A Title\n\nA paragraph that survives.\n\nAnother one.\n",
        )

        result = convert_article(str(source), str(tmp_path / "out"))

        assert not [w for w in result["warnings"] if w.check == "fidelity_loss"]

    def test_a_regressed_stripper_is_caught_end_to_end(self, tmp_path):
        # The 260809-a1o defect, driven through the real pipeline: a doubled
        # percent in prose read as a comment deletes " up from 20".
        source = self._write(
            tmp_path,
            "# A Title\n\nGrowth was 50%% up from 20%% last year.\n",
        )

        def buggy(text: str) -> str:
            return re.sub(r"%%.*?%%[ \t]*", "", text)

        with patch("obsidian_to_substack.obsidian_syntax.strip_obsidian_comments", buggy):
            result = convert_article(str(source), str(tmp_path / "out"))

        # Guard the fixture itself. If the patch ever stops binding -- the name
        # is resolved at call time inside transform_obsidian_syntax, which is
        # not guaranteed to stay that way -- the pipeline would run clean and
        # this test would quietly assert nothing.
        html = Path(result["html_path"]).read_text(encoding="utf-8")
        assert "up from" not in html, "fixture invalid: the patch did not bite"

        fidelity_warnings = [
            w for w in result["warnings"] if w.check == "fidelity_loss"
        ]
        assert fidelity_warnings, "the pipeline lost prose and said nothing"
        assert "up" in fidelity_warnings[0].message

    def test_table_text_does_not_warn_when_it_reached_the_cells(self, tmp_path):
        # Tables are replaced by images, so their prose leaves the HTML. It
        # must be accounted for by the extracted rows, not reported.
        source = self._write(
            tmp_path,
            "# A Title\n\n| Region | Revenue |\n|---|---|\n| North | 1200 |\n",
        )

        result = convert_article(str(source), str(tmp_path / "out"))

        assert not [w for w in result["warnings"] if w.check == "fidelity_loss"]
