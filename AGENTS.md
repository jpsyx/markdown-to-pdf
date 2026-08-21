# AGENTS.md — rules for working on markdown-to-pdf

Rules for any human or agent modifying this repo. This file is canonical;
`CLAUDE.md` and `.cursorrules` symlink to it, and Codex/opencode read `AGENTS.md`
directly.

## What this repo is

A small, self-contained tool that converts a Markdown file to a styled PDF,
built on [ReportLab](https://pypi.org/project/reportlab/). See
[`docs/architecture.md`](docs/architecture.md).

## Entry points

There are two, both at the repo root, and both must keep working when called
directly from any location: each resolves its own directory (via `BASH_SOURCE`)
rather than assuming a working directory or a fixed install path.

- **`install.sh` installs the tool onto `$PATH`.** It creates the private
  virtualenv (`.venv/`, gitignored), installs `requirements.txt` into it, and
  writes an executable launcher at `$BIN_DIR/markdown-to-pdf` (`BIN_DIR`
  defaults to `~/.local/bin`). It must stay **idempotent and double as the
  updater**: rebuild in place, overwrite the launcher at a fixed filename, never
  leave a second copy. It must also be **self-healing** — a virtualenv whose
  interpreter no longer runs (Python upgraded, switched, or removed) is
  recreated rather than reported as an error. This is what makes
  `markdown-to-pdf` a real command reachable by any shell, script, or tool.
- **`install.sh` must work for anyone who clones this repo**, on a machine that
  knows nothing about it: no assumed `$PATH` entry, no assumed environment, no
  private convention. `BIN_DIR` is an ordinary override with a sane default, not
  a required input. When a prerequisite is missing or the result won't be
  usable, **say so and print the fix** — an absent `python3 -m venv`, a
  `BIN_DIR` that isn't on `$PATH`, a clone that was moved out from under an
  installed launcher. Never let a stranger's install fail silently or leave a
  command they can't invoke.
- **`run.sh` runs the tool from a clone.** It picks `.venv/bin/python` when
  present and the system `python3` otherwise, then execs `main.py`. Keep its
  name and location (`run.sh` at the repo root) stable, and keep its CLI
  (`<file.md>`, `--out <path>`). The installed launcher execs it, so the CLI is
  defined in exactly one place and a `git pull` is live without a reinstall.
- **`main.py` owns the CLI surface.** Argument parsing, `--help`, and the
  missing-argument usage error all live there (argparse). Never duplicate a
  usage string in a shell wrapper — it goes stale.
- **No machine-specific literals in tracked files.** This repo may be checked
  out at a different absolute path on every machine, so never hardcode a home
  path or a per-machine location. Resolve paths relative to the script.
  (`install.sh` writing the resolved clone path into the launcher it *generates*
  is fine; that file is not tracked.)

## Hard rules

1. **Do not commit, push, merge, or create PRs unless explicitly told to** in
   plain words in the current conversation. Leave the tree dirty for review.
2. **This repo may be public.** Never commit secrets, tokens, or
   machine-specific paths.
3. **Do not track `__pycache__/`, `*.pyc`, or `.venv/`** (all gitignored) — they
   are regenerated per machine.
4. **Keep Python runtime deps in `requirements.txt`.** Today: `reportlab` and
   `pygments`. That file is what `install.sh` installs into the virtualenv, so a
   new Python dep is added there and nowhere else.
5. **The mermaid renderer is a separate, optional toolchain.** Diagrams need a
   headless browser, so `mermaid-cli` is a Node dependency declared in
   `package.json` and provisioned into the clone by `install.sh`. It must stay
   **optional**: a document without a ```mermaid fence converts with no Node at
   all, and one with a fence prints the diagram source rather than failing.
   Never make the Python path import or require it.
6. **Bump the version on every commit pushed to `main`.** `__version__` in
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
