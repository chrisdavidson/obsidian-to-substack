// Loads tools/obsidian-plugin/main.js against stub `obsidian` and
// `child_process` modules and replays a scenario. Deliberately dumb: it only
// records what the plugin did; every assertion lives in test_obsidian_plugin.py.
//
// Usage: node obsidian_plugin_harness.js <scenario.json>
// The scenario names the plugin file to load, so the test can point it at a
// fake repo layout instead of whatever this checkout happens to contain.
const fs = require("fs");
const os = require("os");
const path = require("path");
const Module = require("module");

const scenario = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

const notices = [];
const execCalls = [];
const execCallbacks = [];
const commands = [];
const events = [];
const registered = [];

class Plugin {
  constructor(app, manifest) { this.app = app; this.manifest = manifest; }
  addCommand(cmd) { commands.push(cmd); }
  registerEvent(ref) { registered.push(ref); }
}
class Notice {
  constructor(message, timeout) {
    this.entry = { message, timeout: timeout === undefined ? null : timeout, hidden: false };
    notices.push(this.entry);
  }
  hide() { this.entry.hidden = true; }
  setMessage() {}
}
class TFile {
  constructor(p) {
    this.path = p;
    this.basename = path.basename(p, path.extname(p));
    this.extension = path.extname(p).replace(/^\./, "");
  }
}
class FileSystemAdapter {
  constructor(base) { this.base = base; }
  getBasePath() { return this.base; }
  getFullPath(p) { return path.join(this.base, p); }
}

const childProcess = {
  // Records the call and keeps the callback so the scenario decides when (and
  // with what) the "process" finishes. It never invokes it on its own.
  execFile(file, args, opts, cb) {
    execCalls.push({ file, args, opts: JSON.parse(JSON.stringify(opts)) });
    execCallbacks.push(cb);
  },
};

const realLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === "obsidian") return { Plugin, Notice, TFile, FileSystemAdapter };
  if (request === "child_process") return childProcess;
  return realLoad.call(this, request, parent, isMain);
};

let active = scenario.activeFile ? new TFile(scenario.activeFile) : null;
const app = {
  vault: { adapter: new FileSystemAdapter(scenario.vaultBase) },
  workspace: {
    getActiveFile: () => active,
    on: (name, cb) => { events.push({ name, cb }); return { name }; },
  },
};

const PluginClass = require(scenario.pluginMain);
const plugin = new PluginClass(app, { dir: scenario.manifestDir });

const results = [];
for (const step of scenario.steps) {
  const noticeStart = notices.length;
  const execStart = execCalls.length;
  const out = { op: step.op };
  if (step.op === "onload") {
    plugin.onload();
  } else if (step.op === "check") {
    const cmd = commands.find((c) => c.id === step.id);
    out.result = cmd.checkCallback(true);
  } else if (step.op === "fileMenu") {
    const items = [];
    const menu = {
      addItem(fn) {
        const item = { title: null, icon: null, onClick: null };
        const api = {
          setTitle(t) { item.title = t; return api; },
          setIcon(i) { item.icon = i; return api; },
          onClick(cb) { item.onClick = cb; return api; },
        };
        fn(api);
        items.push(item);
      },
    };
    events.filter((e) => e.name === "file-menu").forEach((e) => e.cb(menu, new TFile(step.path)));
    out.items = items.map((i) => ({ title: i.title, icon: i.icon }));
  } else if (step.op === "run") {
    plugin.run(new TFile(step.path), !!step.force);
  } else if (step.op === "callback") {
    const err = step.err === null || step.err === undefined ? null : new Error(step.err);
    execCallbacks[step.index](err, step.stdout || "", step.stderr || "");
  }
  out.notices = notices.slice(noticeStart);
  out.execDelta = execCalls.length - execStart;
  results.push(out);
}

process.stdout.write(JSON.stringify({
  tmpdir: os.tmpdir(),
  commands: commands.map((c) => ({ id: c.id, name: c.name, hotkeys: c.hotkeys })),
  eventNames: events.map((e) => e.name),
  registeredCount: registered.length,
  execCalls,
  results,
}));
