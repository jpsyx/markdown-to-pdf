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
markdown-to-pdf <file.md> out.pdf         # shorthand for --out out.pdf
markdown-to-pdf <file.md> exports/        # shorthand for --out exports/
markdown-to-pdf <file.md> --out exports/  # write exports/<file>.pdf
markdown-to-pdf <file.md> --black-text    # pure-black printable text
markdown-to-pdf --help                    # all options
```

Body text is set in a print serif (Charter where available), headings in a
humanist sans, and code in Menlo, each chosen from a per-platform candidate list
and falling back to the built-in PDF fonts when none is installed.

Tables fit their columns using the actual wrapped text, including bold text
and inline code. The target is at least two words per line in each multiword
body cell; single-word labels and values are exempt. The renderer searches for
widths that meet that target before reducing table type in 0.5-point steps,
down to 8 points. At that floor it balances density and row height as well as
the page allows. Body text outside the table keeps its original size.
Words are never split at arbitrary characters: body cells may wrap at existing
hyphens or slashes, and header words stay intact. Headers repeat on subsequent
pages; ordinary rows stay together, while a row taller than a page can continue
onto the next page.

Three pieces of raw HTML are understood. An inline `<sup>G4</sup>` renders as a
small raised superscript wherever text renders, including table cells and
headings, which suits glossary markers placed right after a term; inside a code
span or fence it stays literal. A `<small>` line and a `</small>` line, each on
its own and with or without blank lines around the content, set everything
between them in smaller type: a table starts its fitting 1.5 points lower
(still never below 8 points) and prose drops a point. GitHub keeps `<sup>` but
strips `<small>`, so a wrapped table simply renders at normal size there.
Markdown has no page break, so the CSS idiom serves as one: a line holding only
`<div style="page-break-before: always"></div>` (or `page-break-after`,
`break-before: page`, `break-after: page`) starts a new page, and does nothing
at the top of a page, so it never leaves a blank one. HTML-based converters
honor the same line, and GitHub shows nothing.

Fenced code blocks are syntax highlighted when the fence carries a language
tag (```typescript, ```python, ```sql, ...); an untagged fence renders plain.
A fence may also call out lines, using the meta-string convention Docusaurus and
Shiki share:

````
```typescript {3,5-7}
````

Those lines get a shaded background so prose can point at them. MDX proper (JSX
inside Markdown) is not supported; only the highlight spec is read.

A source line too wide for the page is wrapped rather than run off the right
margin, breaking at a space where there is one and hard-cutting a long
identifier where there is not. Continuations carry a `\u21b3` marker so a wrap is
never mistaken for the source's own formatting, and a called-out line keeps its
shading across every physical row it occupies.

A ```mermaid fence is rendered as a diagram, which needs Node.js: `install.sh`
provisions the renderer, and without it the fence prints its own source so
nothing is lost. A diagram is scaled to fill the text block, so it may take a
whole page: a figure's printed size follows from its aspect ratio rather than
from the pixel size mermaid happened to emit, which is what lets a diagram
carry descriptive labels and stay legible.

A diagram and its explanation are one figure and are never split across a page
break. The italic paragraph after a fence is read as its caption, and a `Where:`
glossary between the two joins the same figure, so the drawing is sized to the
page minus whatever its explanation needs.

A blockquote straight after a diagram or an image is that figure's caption box.
Its blocks keep their own structure, so it can hold the caption, a bold label,
and a table defining the drawing's labels. They print a size smaller, as in a
`<small>` region, inside a shaded box that stays on the figure's page. Inside
the box, a paragraph that is wholly bold prints as a small capitals label, and
a table is laid out without lines or fills, its first column flush with the
caption; leave its header cells empty to omit the header row. When the
box is too tall for the page, its type shrinks before the drawing does, and the
drawing never drops below a third of the page. GitHub shows the same blockquote
as an ordinary quote, so nothing is lost there.

```markdown
> *What to notice in the diagram.*
>
> **Diagram key**
>
> | | |
> | --- | --- |
> | **staged** | Objects uploaded but not yet visible to viewers. |
```

Standalone local images are embedded in the PDF. Relative paths resolve from
the Markdown file's directory, so `![Picker](assets/picker.png)` works from any
current working directory. Images retain their aspect ratio and shrink to fit
the page without being enlarged. Remote image URLs are rejected and never
fetched.

Pages are numbered, centred in the bottom margin. The footer sits below the
text block, so numbering never pushes content around, and a document that fits
on one page is left unnumbered.

Markdown links remain clickable in the PDF and are rendered without underlines
for print readability. Use `--black-text` when the entire document, including
headings and links, should be pure black (`#000000`).

Set `BIN_DIR` to install somewhere else (`BIN_DIR=/usr/local/bin ./install.sh`).
If the chosen directory isn't on your `$PATH`, the installer says so and prints
the line to add. Use `./install.sh --name md-pdf-dev` to choose another command
filename. Repeating the same name replaces that launcher in place. Installer
help exits before tool checks or writes; unknown arguments, missing names, and
names containing paths are rejected before installation.

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
