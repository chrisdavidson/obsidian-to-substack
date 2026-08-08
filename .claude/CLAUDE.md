<!-- GSD:project-start source:PROJECT.md -->

## Project

**obsidian-to-substack**

A Python CLI that converts Obsidian Markdown articles into Substack-ready HTML. Prose
moves from Obsidian to Substack fine by hand; everything else doesn't — tables lose their
structure, SVG diagrams aren't supported at all, and Obsidian's `![[embed]]` and
`[[wikilink]]` syntax means nothing to Substack's composer. The tool handles that payload.

It serves its author today, publishing to <https://foxglenacres.substack.com> from
`~/Obsidian/BrainBank/4_Archive/Published Articles`. Release to other Obsidian writers is
an aspiration, not a current requirement.

**Core Value:** Tables, SVG diagrams, and charts survive the move from Obsidian into a Substack post
**without manual repair in the composer.**

The "without manual repair" clause is the whole milestone. A v1 already exists and
produces output that reaches publication — but only after hand-fixing that has never been
recorded, and that varies article to article.

### Constraints

- **Tech stack**: Python ≥3.11; CairoSVG, Pillow, Markdown, BeautifulSoup4, PyYAML —
  established and working, no reason to churn it

- **Verification**: Human-in-the-loop and unautomatable — Substack has no API for
  rendering checks, so every verification cycle needs the author to paste and report

- **Platform**: `--copy` shells out to `xclip`, so clipboard support is Linux/X11 only —
  acceptable while the audience is one person

- **Secrets**: `DATAWRAPPER_API_TOKEN` is read from the environment only; `*.key` is
  gitignored

- **Planning artifacts**: `.planning/` is gitignored by deliberate choice — this repo is
  headed to GitHub and planning is local workflow state. GSD commit steps on planning
  files are expected no-ops.

- **Testing**: 89 tests currently pass; new defects get pinned by tests, per the author's
  "fixes + automated guards" decision
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->

## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
