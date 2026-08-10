"""Platform backends for `--copy`.

Everything here runs on Linux by mocking the subprocess layer, which is the
only thing that CAN be tested from this side: there is no macOS or Windows
machine on the other end of these calls, and unlike Substack's rendering — which
the author can settle by pasting into a draft — there is nobody who can settle
these. The tests prove the right tool is invoked with the right bytes. They do
not prove a clipboard was written, and no amount of them ever will.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from obsidian_to_substack.clipboard import (
    DARWIN,
    LINUX,
    WINDOWS,
    ascii_escape,
    build_cf_html,
    copy_html,
    copy_title,
    current_platform,
)


class TestPlatformDetection:
    """Each platform reaches its own backend and no other."""

    @pytest.mark.parametrize(
        "sys_platform,expected",
        [
            ("linux", LINUX),
            ("linux2", LINUX),
            ("darwin", DARWIN),
            ("win32", WINDOWS),
            ("cygwin", WINDOWS),
        ],
    )
    def test_known_platforms(self, sys_platform, expected):
        with patch("sys.platform", sys_platform):
            assert current_platform() == expected

    def test_an_unknown_platform_is_not_guessed_at(self):
        # Fail closed: a platform nobody has tested must not be silently
        # handed to a backend built for a different one.
        with patch("sys.platform", "sunos5"):
            assert current_platform() is None


class TestAsciiEscape:
    """Windows CF_HTML carries BYTE offsets, and the upstream PowerShell bug is
    exactly the UTF-16/UTF-8 confusion that produces. Escaping the payload to
    pure ASCII first makes byte offsets and character offsets identical, so the
    whole class of bug cannot arise."""

    def test_an_em_dash_becomes_a_numeric_reference(self):
        assert ascii_escape("a — b") == "a &#8212; b"

    def test_plain_ascii_is_untouched(self):
        source = "<p>Plain ASCII &amp; markup</p>"

        assert ascii_escape(source) == source

    def test_the_result_is_encodable_as_ascii(self):
        escaped = ascii_escape("Ünïcode — “smart” quotes … ✓")

        escaped.encode("ascii")  # must not raise

    def test_pure_function_no_mutation(self):
        source = "text — with an em dash"
        copy = source

        ascii_escape(source)

        assert source == copy


class TestBuildCfHtml:
    """The header offsets have to be real byte positions or the paste is
    truncated. This is the arithmetic PowerShell's --AsHtml gets wrong."""

    def _offsets(self, payload: str) -> dict[str, int]:
        values = {}
        for line in payload.split("\n"):
            for key in ("StartHTML", "EndHTML", "StartFragment", "EndFragment"):
                if line.startswith(key + ":"):
                    values[key] = int(line.split(":", 1)[1])
        return values

    def test_offsets_point_at_the_real_byte_positions(self):
        payload = build_cf_html("<p>hello</p>")
        raw = payload.encode("utf-8")
        offsets = self._offsets(payload)

        assert raw[offsets["StartHTML"]:].startswith(b"<html>")
        assert offsets["EndHTML"] == len(raw)
        assert raw[offsets["StartFragment"]:offsets["EndFragment"]] == b"<p>hello</p>"

    def test_offsets_are_byte_positions_for_non_ascii_input(self):
        # The case the upstream bug gets wrong. Character counts and byte
        # counts diverge here, and a header built on the former truncates the
        # end of the article in the paste.
        payload = build_cf_html("<p>em — dash and Ünïcode</p>")
        raw = payload.encode("utf-8")
        offsets = self._offsets(payload)

        fragment = raw[offsets["StartFragment"]:offsets["EndFragment"]]
        assert fragment.decode("utf-8") == "<p>em &#8212; dash and &#220;n&#239;code</p>"
        assert offsets["EndHTML"] == len(raw)

    def test_the_whole_payload_is_ascii(self):
        build_cf_html("<p>Ünïcode — everywhere</p>").encode("ascii")

    def test_it_carries_the_required_header_keys(self):
        payload = build_cf_html("<p>x</p>")

        assert payload.startswith("Version:")
        for key in ("StartHTML", "EndHTML", "StartFragment", "EndFragment"):
            assert f"{key}:" in payload

    def test_the_fragment_markers_are_present(self):
        payload = build_cf_html("<p>x</p>")

        assert "<!--StartFragment-->" in payload
        assert "<!--EndFragment-->" in payload

    def test_pure_function_no_mutation(self):
        source = "<p>x</p>"
        copy = source

        build_cf_html(source)

        assert source == copy


class TestMacOsBackend:
    def test_osascript_receives_the_script_on_stdin(self):
        # Not argv: an article carries base64-inlined images and would blow
        # past the argument length limit.
        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/osascript"),
            patch("subprocess.run") as run,
        ):
            copy_html("<p>hello</p>")

        argv = run.call_args[0][0]
        assert argv[0] == "osascript"
        assert argv[1] == "-"
        assert run.call_args.kwargs.get("input") is not None
        assert not any("hello" in str(a) for a in argv)

    def test_the_payload_is_hex_encoded_html(self):
        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/osascript"),
            patch("subprocess.run") as run,
        ):
            copy_html("<p>hello</p>")

        script = run.call_args.kwargs["input"].decode("utf-8")
        assert "<p>hello</p>".encode("utf-8").hex() in script

    def test_the_text_placeholder_is_present(self):
        # Without it some paste targets take nothing at all.
        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/osascript"),
            patch("subprocess.run") as run,
        ):
            copy_html("<p>hello</p>")

        script = run.call_args.kwargs["input"].decode("utf-8")
        assert 'text:" "' in script

    def test_missing_osascript_exits_with_a_message(self, capsys):
        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value=None),
            pytest.raises(SystemExit),
        ):
            copy_html("<p>hello</p>")

        assert "osascript" in capsys.readouterr().err


class TestWindowsBackend:
    def test_powershell_is_invoked(self):
        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", side_effect=lambda name: f"C:\\{name}"),
            patch("subprocess.run") as run,
        ):
            copy_html("<p>hello</p>")

        argv = run.call_args[0][0]
        assert "powershell" in argv[0].lower() or "pwsh" in argv[0].lower()

    def test_the_payload_file_holds_cf_html_while_powershell_runs(self):
        # Read the file from inside the fake subprocess call, which is the
        # only moment it is guaranteed to exist -- copy_html deletes it in a
        # finally block. Asserting after the call would pass against a path
        # that was never written.
        seen: dict[str, str] = {}

        def capture(argv, **kwargs):
            path = kwargs["env"]["OTS_CLIPBOARD_PAYLOAD"]
            seen["payload"] = Path(path).read_text(encoding="ascii")
            seen["command"] = argv[-1]
            return None

        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", side_effect=lambda name: f"C:\\{name}"),
            patch("subprocess.run", side_effect=capture),
        ):
            copy_html("<p>hello — world</p>")

        assert seen["payload"].startswith("Version:")
        assert "<p>hello &#8212; world</p>" in seen["payload"]
        assert "TextDataFormat]::Html" in seen["command"]

    def test_the_payload_file_is_cleaned_up(self):
        captured: dict[str, str] = {}

        def capture(argv, **kwargs):
            captured["path"] = kwargs["env"]["OTS_CLIPBOARD_PAYLOAD"]
            return None

        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", side_effect=lambda name: f"C:\\{name}"),
            patch("subprocess.run", side_effect=capture),
        ):
            copy_html("<p>hello</p>")

        assert not Path(captured["path"]).exists()

    def test_the_temp_path_is_not_interpolated_into_the_command(self):
        # A path spliced into a PowerShell single-quoted string is terminated
        # by any quote inside it, and a Windows temp path runs through the
        # user's profile directory — `C:\Users\O'Brien\AppData\...` is an
        # ordinary name. That failure would happen only on the platform with
        # nobody to notice it, so the path is handed over out of band instead
        # of escaped. Structurally impossible beats carefully quoted.
        seen: dict[str, str] = {}

        def capture(argv, **kwargs):
            seen["command"] = argv[-1]
            seen["env"] = kwargs.get("env") or {}
            return None

        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", side_effect=lambda name: f"C:\\{name}"),
            patch("subprocess.run", side_effect=capture),
        ):
            copy_html("<p>hello</p>")

        assert "'" not in seen["command"].split("ReadAllText")[1][:40]
        assert any(
            "Temp" in str(value) or "tmp" in str(value)
            for value in seen["env"].values()
        ), "the payload path must reach PowerShell out of band"

    def test_the_article_never_reaches_the_command_line(self):
        # Same argument-length reason as macOS: a real article with inlined
        # images is far past any command-length limit.
        seen: dict[str, str] = {}

        def capture(argv, **kwargs):
            seen["command"] = argv[-1]
            return None

        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", side_effect=lambda name: f"C:\\{name}"),
            patch("subprocess.run", side_effect=capture),
        ):
            copy_html("<p>a distinctive sentence</p>")

        assert "distinctive" not in seen["command"]

    def test_missing_powershell_exits_with_a_message(self, capsys):
        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", return_value=None),
            pytest.raises(SystemExit),
        ):
            copy_html("<p>hello</p>")

        assert "PowerShell" in capsys.readouterr().err


class TestUnsupportedPlatform:
    def test_it_refuses_rather_than_guessing(self, capsys):
        with (
            patch("sys.platform", "sunos5"),
            pytest.raises(SystemExit),
        ):
            copy_html("<p>hello</p>")

        assert "sunos5" in capsys.readouterr().err


class TestAgainstARealArticle:
    """The unit tests above use toy fragments. A real article is 100kB of
    inlined base64 with a handful of non-ASCII characters buried in it, which
    is where offset arithmetic and argument limits actually bite."""

    def _article(self, tmp_path) -> str:
        from obsidian_to_substack.convert import _inline_images, convert_article

        fixture = (
            Path(__file__).parent / "fixtures" / "torture_test" / "torture-test.md"
        )
        result = convert_article(str(fixture), str(tmp_path))
        written = Path(result["html_path"])
        return _inline_images(written.read_text(encoding="utf-8"), written.parent)

    def test_the_macos_hex_round_trips_byte_for_byte(self, tmp_path):
        from obsidian_to_substack.clipboard import _MACOS_SCRIPT

        html = self._article(tmp_path)
        script = _MACOS_SCRIPT.format(hex=html.encode("utf-8").hex())

        payload = script.split("«data HTML")[1].rstrip("»}")
        assert bytes.fromhex(payload).decode("utf-8") == html

    def test_the_macos_script_is_too_long_for_argv(self, tmp_path):
        # The reason it goes in on stdin, asserted rather than asserted-in-a-
        # comment. Linux caps a single argument at 128kB (MAX_ARG_STRLEN); the
        # hex doubles an already-100kB article.
        from obsidian_to_substack.clipboard import _MACOS_SCRIPT

        html = self._article(tmp_path)
        script = _MACOS_SCRIPT.format(hex=html.encode("utf-8").hex())

        assert len(script.encode("utf-8")) > 131072

    def test_cf_html_offsets_are_true_of_a_real_article(self, tmp_path):
        html = self._article(tmp_path)
        payload = build_cf_html(html)
        raw = payload.encode("ascii")

        offsets = {}
        for line in payload.split("\r\n"):
            for key in ("StartHTML", "EndHTML", "StartFragment", "EndFragment"):
                if line.startswith(key + ":"):
                    offsets[key] = int(line.split(":", 1)[1])

        assert raw[offsets["StartHTML"]:].startswith(b"<html>")
        assert offsets["EndHTML"] == len(raw)
        fragment = raw[offsets["StartFragment"]:offsets["EndFragment"]].decode("ascii")
        assert fragment.startswith("<!DOCTYPE html>")
        assert fragment.endswith("</html>")

    def test_a_real_article_carries_non_ascii(self, tmp_path):
        # Guard the two tests above: if the fixture ever went pure ASCII they
        # would still pass while proving nothing about the case that matters.
        html = self._article(tmp_path)

        assert any(ord(char) > 127 for char in html)


class TestTitleHandoff:
    def test_linux_still_writes_the_primary_selection(self):
        with (
            patch("sys.platform", "linux"),
            patch("shutil.which", return_value="/usr/bin/xclip"),
            patch("subprocess.run") as run,
        ):
            copy_title("A Title")

        assert run.call_args[0][0] == ["xclip", "-selection", "primary"]

    @pytest.mark.parametrize("sys_platform", ["darwin", "win32"])
    def test_one_clipboard_platforms_print_instead_of_copying(
        self, sys_platform, capsys
    ):
        # Copying the title would clobber the body that --copy just placed on
        # the single clipboard, which is the opposite of helping.
        with (
            patch("sys.platform", sys_platform),
            patch("subprocess.run") as run,
        ):
            copy_title("A Title")

        assert not run.called
        assert "by hand" in capsys.readouterr().out

    def test_an_empty_title_does_nothing_anywhere(self):
        with (
            patch("sys.platform", "darwin"),
            patch("subprocess.run") as run,
        ):
            copy_title("")

        assert not run.called
