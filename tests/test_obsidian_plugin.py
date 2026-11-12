"""Guard for the private Obsidian plugin in ``tools/obsidian-plugin``.

The plugin is plain JavaScript with no build step, so the proportionate check
is: the manifest is sane, the file parses, and its behaviour holds under a node
stub of the two modules it touches (``obsidian`` and ``child_process``). What
happens inside a running Obsidian is not claimed here.

Run scenarios build their own fake repo/vault under ``tmp_path`` so the result
never depends on whether this checkout has a ``.venv``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "tools" / "obsidian-plugin"
HARNESS = Path(__file__).resolve().parent / "obsidian_plugin_harness.js"
MANIFEST_DIR = ".obsidian/plugins/substack-convert"
NOTE = "Articles/Post.md"


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    return node


def _layout(tmp_path: Path, *, with_tool: bool) -> tuple[Path, Path]:
    """Fake repo + vault, with the plugin symlinked in as the real install is."""
    repo = tmp_path / "repo"
    plugin_dir = repo / "tools" / "obsidian-plugin"
    plugin_dir.mkdir(parents=True)
    for name in ("main.js", "manifest.json"):
        shutil.copy(PLUGIN / name, plugin_dir / name)
    vault = tmp_path / "vault"
    (vault / ".obsidian" / "plugins").mkdir(parents=True)
    (vault / ".obsidian" / "plugins" / "substack-convert").symlink_to(plugin_dir)
    (vault / "Articles").mkdir()
    (vault / NOTE).write_text("# Post\n", encoding="utf-8")
    if with_tool:
        tool = repo / ".venv" / "bin" / "obsidian-to-substack"
        tool.parent.mkdir(parents=True)
        tool.write_text("", encoding="utf-8")
        tool.chmod(0o755)
    return repo, vault


def _play(
    tmp_path: Path,
    steps: list[dict[str, Any]],
    *,
    with_tool: bool = True,
    active: str | None = NOTE,
) -> tuple[dict[str, Any], Path, Path]:
    node = _node()
    repo, vault = _layout(tmp_path, with_tool=with_tool)
    scenario = {
        "pluginMain": str(repo / "tools" / "obsidian-plugin" / "main.js"),
        "manifestDir": MANIFEST_DIR,
        "vaultBase": str(vault),
        "activeFile": active,
        "steps": steps,
    }
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    proc = subprocess.run(
        [node, str(HARNESS), str(scenario_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout), repo, vault


def test_manifest_is_sane() -> None:
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "substack-convert"
    assert manifest["isDesktopOnly"] is True
    for key in ("name", "version", "minAppVersion"):
        assert manifest[key]


def test_main_js_has_no_hardcoded_home_path() -> None:
    # A literal home directory is one machine's answer; the tool is found from
    # the plugin's own real location instead.
    assert "/home/" not in (PLUGIN / "main.js").read_text(encoding="utf-8")


def test_main_js_parses() -> None:
    node = _node()
    proc = subprocess.run(
        [node, "--check", str(PLUGIN / "main.js")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_onload_registers_commands_and_file_menu(tmp_path: Path) -> None:
    out, _, _ = _play(tmp_path, [{"op": "onload"}])
    by_id = {c["id"]: c for c in out["commands"]}
    assert set(by_id) == {"convert-copy", "convert-copy-force"}
    assert by_id["convert-copy"]["hotkeys"] == [{"modifiers": ["Mod", "Alt"], "key": "S"}]
    assert not by_id["convert-copy-force"].get("hotkeys")
    assert out["eventNames"] == ["file-menu"]
    assert out["registeredCount"] == 1


def test_file_menu_item_only_for_markdown(tmp_path: Path) -> None:
    out, _, _ = _play(
        tmp_path,
        [
            {"op": "onload"},
            {"op": "fileMenu", "path": NOTE},
            {"op": "fileMenu", "path": "Attachments/pic.png"},
        ],
    )
    md, png = out["results"][1], out["results"][2]
    assert [i["title"] for i in md["items"]] == ["Convert to Substack"]
    assert png["items"] == []


@pytest.mark.parametrize(
    ("active", "expected"),
    [(NOTE, True), ("Attachments/pic.png", False), (None, False)],
)
def test_check_callback_follows_active_file(
    tmp_path: Path, active: str | None, expected: bool
) -> None:
    out, _, _ = _play(
        tmp_path,
        [{"op": "onload"}, {"op": "check", "id": "convert-copy"}],
        active=active,
    )
    assert out["results"][1]["result"] is expected


def test_missing_tool_is_a_sticky_notice_and_runs_nothing(tmp_path: Path) -> None:
    out, repo, _ = _play(
        tmp_path, [{"op": "onload"}, {"op": "run", "path": NOTE}], with_tool=False
    )
    assert out["execCalls"] == []
    notices = out["results"][1]["notices"]
    assert len(notices) == 1
    assert notices[0]["timeout"] == 0
    expected_tool = os.path.realpath(repo) + "/.venv/bin/obsidian-to-substack"
    assert expected_tool in notices[0]["message"]
    assert "uv sync" in notices[0]["message"]


@pytest.mark.parametrize("force", [False, True])
def test_run_invokes_tool_with_argv_array(tmp_path: Path, force: bool) -> None:
    out, repo, vault = _play(
        tmp_path, [{"op": "onload"}, {"op": "run", "path": NOTE, "force": force}]
    )
    assert len(out["execCalls"]) == 1
    call = out["execCalls"][0]
    root = os.path.realpath(repo)
    assert call["file"] == f"{root}/.venv/bin/obsidian-to-substack"
    expected = [
        os.path.realpath(vault / "Articles"),
        "--file",
        "Post.md",
        "--output-dir",
        os.path.join(out["tmpdir"], "obsidian-to-substack"),
        "--copy",
    ]
    if force:
        expected.append("--force")
    # The vault path is symlink-free here, so compare through realpath.
    assert [os.path.realpath(a) if i == 0 else a for i, a in enumerate(call["args"])] == expected
    assert os.path.realpath(call["opts"]["cwd"]) == root
    assert call["opts"]["timeout"] == 120000
    # No shell: note titles with quotes, spaces or `$` must reach the CLI as data.
    assert not call["opts"].get("shell")


def test_second_run_while_running_starts_nothing(tmp_path: Path) -> None:
    out, _, _ = _play(
        tmp_path,
        [
            {"op": "onload"},
            {"op": "run", "path": NOTE},
            {"op": "run", "path": NOTE},
        ],
    )
    assert len(out["execCalls"]) == 1
    assert out["results"][2]["execDelta"] == 0
    assert len(out["results"][2]["notices"]) == 1


def test_failure_is_sticky_filters_info_and_releases_guard(tmp_path: Path) -> None:
    out, _, _ = _play(
        tmp_path,
        [
            {"op": "onload"},
            {"op": "run", "path": NOTE},
            {
                "op": "callback",
                "index": 0,
                "err": "Command failed",
                "stdout": "W1 warning",
                "stderr": "INFO: x\nError: --copy refused",
            },
            {"op": "run", "path": NOTE},
        ],
    )
    failure = out["results"][2]["notices"]
    assert len(failure) == 1
    assert failure[0]["timeout"] == 0
    assert "W1 warning" in failure[0]["message"]
    assert "--copy refused" in failure[0]["message"]
    assert "INFO:" not in failure[0]["message"]
    assert out["results"][3]["execDelta"] == 1


def test_success_notice_is_timed_and_shows_stdout(tmp_path: Path) -> None:
    out, _, _ = _play(
        tmp_path,
        [
            {"op": "onload"},
            {"op": "run", "path": NOTE},
            {"op": "callback", "index": 0, "err": None, "stdout": "Copied 1 article"},
        ],
    )
    success = out["results"][2]["notices"]
    assert len(success) == 1
    assert "Copied 1 article" in success[0]["message"]
    assert success[0]["timeout"] and success[0]["timeout"] > 0
