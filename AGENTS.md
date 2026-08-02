# AGENTS.md — rules for working on markdown-to-pdf

Rules for any human or agent modifying this repo. This file is canonical;
`CLAUDE.md` and `.cursorrules` symlink to it, and Codex/opencode read `AGENTS.md`
directly.

## What this repo is

A small, self-contained tool that converts a Markdown file to a styled PDF,
built on [ReportLab](https://pypi.org/project/reportlab/). See
[`docs/architecture.md`](docs/architecture.md).

## Entry point

- **`run.sh` is the stable entry point.** It must run the tool and keep working
  when called directly from any location — it resolves its own directory (via
  `BASH_SOURCE`) rather than assuming a working directory or a fixed install
  path. Keep its name and location (`run.sh` at the repo root) stable, and keep
  its CLI (`<file.md>`, `--out <path>`).
- **No machine-specific literals.** This repo may be checked out at a different
  absolute path on every machine, so never hardcode a home path or a per-machine
  location. Resolve paths relative to the script.

## Hard rules

1. **Do not commit, push, merge, or create PRs unless explicitly told to** in
   plain words in the current conversation. Leave the tree dirty for review.
2. **This repo may be public.** Never commit secrets, tokens, or
   machine-specific paths.
3. **Do not track `__pycache__/` or `*.pyc`** (they are gitignored) — they are
   regenerated per machine.
4. **Keep runtime deps in `requirements.txt`.** Today: `reportlab`.
5. **Bump the version on every commit pushed to `main`.** `__version__` in
   `main.py` is the single source of truth (surfaced via `--version` / `-v`).
   Before you commit and push to `main`, raise it following semver: **patch**
   (`0.1.0` → `0.1.1`) for fixes and internal changes, **minor**
   (`0.1.0` → `0.2.0`) for a new user-facing feature, **major**
   (`0.1.0` → `1.0.0`) for a breaking CLI change. One bump per pushed commit;
   include it in that same commit. This applies only when you are authorized to
   push (rule 1 still governs whether you push at all).

## Development

- **Red/green TDD.** For any change to `main.py`'s parsing/rendering logic, write
  or extend a failing test in `test_inline_markup.py` first (RED), confirm it
  fails, then make it pass (GREEN), then refactor. Keep pure string helpers
  (like `inline_markup`) separately testable — do not fold them into IO paths.
- **Run the tests before finishing:** `python3 test_inline_markup.py` (uses the
  stdlib `unittest`).
- Target Python 3, standard library plus `reportlab` only.
