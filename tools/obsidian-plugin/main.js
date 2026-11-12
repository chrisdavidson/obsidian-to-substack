// A private plugin with no build step and no npm dependencies. Obsidian loads
// this file as-is, through a symlink from
// <vault>/.obsidian/plugins/substack-convert to <repo>/tools/obsidian-plugin.
const { Plugin, Notice, TFile, FileSystemAdapter } = require("obsidian");
const { execFile } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

// Output must be outside the vault: the vault is unversioned and never
// bulk-written. The system temp dir is disposable, and the HTML written there
// is only a staging copy for the clipboard.
const OUTPUT_DIR = path.join(os.tmpdir(), "obsidian-to-substack");

module.exports = class SubstackConvert extends Plugin {
  onload() {
    // Command palette + bindable hotkey, acting on the open note.
    this.addCommand({
      id: "convert-copy",
      name: "Convert current note and copy",
      hotkeys: [{ modifiers: ["Mod", "Alt"], key: "S" }],
      checkCallback: (checking) => this.forActive(checking, false),
    });
    // The escape hatch for a refused run gets no default hotkey on purpose:
    // overriding the gate should never be one keystroke away.
    this.addCommand({
      id: "convert-copy-force",
      name: "Convert current note and copy despite warnings (--force)",
      checkCallback: (checking) => this.forActive(checking, true),
    });
    // Right-click in the core file explorer, and the note's "..." / tab menu.
    this.registerEvent(
      this.app.workspace.on("file-menu", (menu, file) => {
        if (!(file instanceof TFile) || file.extension !== "md") return;
        menu.addItem((item) =>
          item.setTitle("Convert to Substack").setIcon("send")
            .onClick(() => this.run(file, false)));
      }),
    );
  }

  forActive(checking, force) {
    const file = this.app.workspace.getActiveFile();
    if (!file || file.extension !== "md") return false;
    if (!checking) this.run(file, force);
    return true;
  }

  // Ask the filesystem where the repo is rather than encoding one machine's
  // home directory: the real path of this plugin's own directory IS
  // <repo>/tools/obsidian-plugin, so the repo root is two levels up.
  //
  // The tool is the venv entry point, not `uv run`: Obsidian launched from a
  // desktop launcher may not inherit a shell PATH, so `uv` may not resolve,
  // while the venv script is an editable install that always runs the repo's
  // current code.
  toolPath(adapter) {
    try {
      const pluginDir = fs.realpathSync(adapter.getFullPath(this.manifest.dir));
      const root = path.resolve(pluginDir, "..", "..");
      return { root, tool: path.join(root, ".venv", "bin", "obsidian-to-substack") };
    } catch (e) {
      new Notice(`Convert to Substack could not locate its own directory:\n${e.message}`, 0);
      return null;
    }
  }

  run(file, force) {
    const adapter = this.app.vault.adapter;
    if (!(adapter instanceof FileSystemAdapter)) {
      new Notice("Convert to Substack needs the desktop app.");
      return;
    }
    // Two --copy runs would race for the same clipboard and the same output dir.
    if (this.running) {
      new Notice("Convert to Substack is already running.");
      return;
    }
    const located = this.toolPath(adapter);
    if (!located) return;
    const { root, tool } = located;
    // Fail closed and be loud: do not guess another location.
    if (!fs.existsSync(tool)) {
      new Notice(`Convert to Substack: ${tool} does not exist.\nRun \`uv sync\` in ${root}.`, 0);
      return;
    }
    const abs = adapter.getFullPath(file.path);
    const args = [path.dirname(abs), "--file", path.basename(abs),
                  "--output-dir", OUTPUT_DIR, "--copy"];
    if (force) args.push("--force");

    this.running = true;
    const pending = new Notice(`Converting “${file.basename}”…`, 0);
    // execFile passes argv directly with no shell, so note titles containing
    // quotes, spaces, `$` or backticks reach the CLI as data and cannot be
    // interpreted.
    //
    // Safe to capture pipes: the tool gives wl-copy/xclip stdout=DEVNULL and
    // stderr=tempfile (_run_selection_owner in clipboard.py), so no clipboard
    // daemon holds our pipe open and the v1.4.1 hang cannot recur here.
    execFile(tool, args, { cwd: root, timeout: 120000, maxBuffer: 16 * 1024 * 1024 },
      (err, stdout, stderr) => {
        this.running = false;
        pending.hide();
        const errLines = (stderr || "").split("\n")
          .filter((l) => !l.startsWith("INFO:")).join("\n").trim();
        const out = (stdout || "").trim();
        if (err) {
          // A refusal or failure stays on screen until dismissed: the v1.2
          // gate exists so a broken run cannot end looking like success.
          // Fail closed and be loud. The preflight warnings are on stdout.
          new Notice(`✗ Not copied\n\n${out}\n\n${errLines || err.message}`, 0);
          console.error("[substack-convert]", err, stdout, stderr);
          return;
        }
        // The CLI's own stdout already prints the per-platform paste
        // instructions; repeating them here would be a second, staler copy.
        new Notice(`✓ ${out}`, 15000);
      });
  }
};
