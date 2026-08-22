# markdown-to-pdf

An opinionated utility script to convert a Markdown file to a styled PDF.

This is a small Python tool (built on [ReportLab](https://pypi.org/project/reportlab/)) with a thin shell entry point.

## Install

```sh
git clone https://github.com/jpsyx/markdown-to-pdf.git
cd markdown-to-pdf
./install.sh          # → ~/.local/bin/markdown-to-pdf
```

`install.sh` creates a private virtualenv inside the clone, installs the
dependencies into it, and writes an executable launcher into `~/.local/bin` —
so `markdown-to-pdf` is a real command available to any shell, script, or tool:

```sh
markdown-to-pdf <file.md>                 # write <file>.pdf next to the input
markdown-to-pdf <file.md> --out out.pdf   # explicit output path
markdown-to-pdf <file.md> --black-text    # pure-black printable text
markdown-to-pdf --help                    # all options
```

Body text is set in a print serif (Charter where available), headings in a
humanist sans, and code in Menlo, each chosen from a per-platform candidate list
and falling back to the built-in PDF fonts when none is installed.

Fenced code blocks are syntax highlighted when the fence carries a language
tag (```typescript, ```python, ```sql, ...); an untagged fence renders plain.
A fence may also call out lines, using the meta-string convention Docusaurus and
Shiki share:

````
```typescript {3,5-7}
````

Those lines get a shaded background so prose can point at them. MDX proper (JSX
inside Markdown) is not supported; only the highlight spec is read.
A ```mermaid fence is rendered as a diagram, which needs Node.js: `install.sh`
provisions the renderer, and without it the fence prints its own source so
nothing is lost.

Markdown links remain clickable in the PDF and are rendered without underlines
for print readability. Use `--black-text` when the entire document, including
headings and links, should be pure black (`#000000`).

Set `BIN_DIR` to install somewhere else (`BIN_DIR=/usr/local/bin ./install.sh`).
If the chosen directory isn't on your `$PATH`, the installer says so and prints
the line to add.

**Keep the clone.** The converter and its virtualenv live there; the launcher
points at them. If you move the clone, re-run `./install.sh` from its new
location.

### Updating

```sh
git pull && ./install.sh
```

`install.sh` is idempotent: it refreshes the virtualenv and overwrites the same
launcher, never leaving a second copy. It also repairs a virtualenv whose Python
has since been upgraded or removed.

### Uninstalling

```sh
rm ~/.local/bin/markdown-to-pdf   # or $BIN_DIR/markdown-to-pdf
rm -rf .venv                      # optional; everything else is in the clone
```

## Usage from a clone

Without installing, run it in place:

```sh
./run.sh <file.md>
```

## Requirements

- Python 3, with the standard `venv` module (Debian/Ubuntu ship it separately as
  `python3-venv`)
- `reportlab` — `./install.sh` installs it into the virtualenv; by hand,
  `pip install -r requirements.txt`
- Network access the first time you install (to download `reportlab`)

## Layout

- `install.sh` — installs the launcher onto `$PATH` (and updates it in place).
- `run.sh` — entry point; resolves its own dir and execs `main.py`.
- `main.py` — the converter (argument parsing, Markdown → PDF rendering).
- `test_inline_markup.py` — unit tests for inline-markup parsing.
- `docs/architecture.md` — how the converter is structured.

## Development

Run the tests (`unittest`):

```sh
python3 test_inline_markup.py
```

## License

[MIT](LICENSE)
