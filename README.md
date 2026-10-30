# markdown-to-pdf

An opinionated utility script to convert a Markdown file to a styled PDF.

This is a small Python tool (built on [ReportLab](https://pypi.org/project/reportlab/)) with a thin shell entry point.

See [publishing and repository transfer](docs/publishing.md) for maintainer setup.

## Reusable page decorations

Add local artwork, a repeated footer, and a first-page rights notice without
changing the source Markdown:

```sh
markdown-to-pdf guide.md --out guide.pdf \
  --header logo.png --header-width 120 --header-opacity 0.6 \
  --watermark watermark.png --watermark-width 300 --watermark-opacity 0.15 \
  --footer '<font color="#94A4B8">Copyright 2026. All rights reserved.</font>' \
  --copyright-callout '**All rights reserved.** Shared for review only.' \
  --deterministic

markdown-to-pdf guide.md --out typeset.pdf \
  --font-regular fonts/Regular.ttf --font-bold fonts/Bold.ttf \
  --font-italic fonts/Italic.ttf --font-bold-italic fonts/BoldItalic.ttf \
  --margin-left 66 --margin-right 66 --margin-top 72 --margin-bottom 54
```

All options are optional. Without them, the existing typography, margins, and
page-number behavior stay the same. Coordinates and dimensions are PDF points
(72 points per inch), measured from the page's bottom-left corner. Images keep
their aspect ratio. `x`/`y` anchor the image's lower-left corner or the footer's
lower-left text box, not its baseline.

| Option | Purpose and default |
| --- | --- |
| `--header PATH` | Local raster image on every page. Default width 120, x at left margin, top edge 24 points below page top. |
| `--watermark PATH` | Local raster image beneath each page's content. Default width 300, centered. |
| `--footer TEXT` | Text on every page, 9-point type with 11-point leading. Default x at left margin, y 20, width equal to the margin box less 45 points. |
| `--header-x`, `--header-y`, `--header-width`, `--header-opacity` | Override header placement, size, or opacity. |
| `--watermark-x`, `--watermark-y`, `--watermark-width`, `--watermark-opacity` | Override watermark placement, size, or opacity. |
| `--footer-x`, `--footer-y`, `--footer-width`, `--footer-opacity` | Override footer placement, text-box width, or opacity. |
| `--copyright-callout TEXT` | Readable shaded box once, before the first document block. Must fit on the first page. |
| `--font-regular PATH` | Local TTF for body, headings, callout, and footer; code font is unchanged. |
| `--font-bold`, `--font-italic`, `--font-bold-italic` | Optional local TTF styles; require `--font-regular`. Omitted styles use regular, except bold-italic uses bold when supplied. |
| `--margin-left`, `--margin-right`, `--margin-top`, `--margin-bottom` | Margin points; defaults 56.2, 56.2, 51.8, and 42. Header/footer automatically reserve additional space when needed. |
| `--deterministic` | Stable PDF bytes for unchanged Markdown, assets, fonts, options, and output filename in the same rendering environment. |

Opacity defaults to 1 and accepts values from 0 to 1. Widths must be positive;
coordinates and margins must be finite and nonnegative. Artwork and footer
boxes must fit inside the Letter page. Supported local image formats are PNG,
JPEG, GIF, BMP, and TIFF. Remote image URLs are rejected. Decoration controls
require their corresponding image or footer. Invalid options are rejected
before the output file is selected, created, or replaced.

Footer and callout text accept inline Markdown (bold, italic, code, and paragraph
breaks) or this safe HTML subset: `b`, `strong`, `i`, `em`, `u`, `br`, `p`, and
`font color="#RRGGBB"`. Tags must be balanced. Other tags, attributes, comments,
links, and images are rejected; decoration text cannot execute HTML or fetch
resources. Keep Markdown emphasis within one HTML text span. Literal HTML tags
inside inline code must use escaped entities (for example, `&lt;div&gt;`), because
the safe HTML parser runs before inline Markdown. For example:

```sh
markdown-to-pdf guide.md --copyright-callout \
  '<p><strong>Reader notice</strong><br/>Shared for review only.</p>'
```

The footer repeats on single-page documents too. Existing page numbering remains
hidden for one page and appears on every page of longer documents. When a custom
footer is present, page numbers move to the right at the footer's y coordinate.
`--black-text` still controls document text; an explicitly colored footer or
callout span retains its chosen color. Custom fonts and margins apply only to
the current conversion, including when several conversions share a Python
process. Existing-output versioning still applies with `--deterministic`; use
the same clean destination to reproduce byte-identical files.

## Install with npm

The npm package is `@avandar/markdown-to-pdf`; its executable is `markdown-to-pdf`.
These registry commands become available after the package is published:

```sh
npm install --save-dev @avandar/markdown-to-pdf
npm exec -- markdown-to-pdf docs/guide.md --out guide.pdf

# Or install the command globally:
npm install --global @avandar/markdown-to-pdf
markdown-to-pdf docs/guide.md --out guide.pdf
```

For a repeatable build, add an npm script to the consuming repository:

```json
{
  "scripts": {
    "build:pdf": "markdown-to-pdf docs/guide.md --out guide.pdf"
  }
}
```

Requires Node.js 20+ and Python 3.10+ with `venv` and pip. On Debian/Ubuntu,
install `python3-venv` if necessary. Set `MARKDOWN_TO_PDF_PYTHON` to a Python
executable path to override discovery. The first invocation installs
`requirements.txt` into a private virtualenv under
`~/.cache/markdown-to-pdf/npm`. It requires network access to the configured
Python package index. Later runs reuse it; broken environments are rebuilt.
Use `MARKDOWN_TO_PDF_CACHE_DIR` to override the cache directory. The npm
installation directory and global Python environment are not modified.
Uninstalling the npm package leaves this cache; it can be deleted separately.

Setup happens on invocation, so the Python CLI works even with npm lifecycle
scripts disabled. Mermaid is an optional npm dependency; `--omit=optional`
skips it. Rendering diagrams still requires Mermaid's compatible browser and
system libraries. If its browser download was skipped, provision the browser
for your installed Puppeteer version before generating diagrams. Otherwise,
the existing converter falls back to printing diagram source.

In CI, install Node and Python, run `npm ci --include=dev`, then
`npm run build:pdf`, and upload the PDF with your CI provider's artifact or
release-upload step. Start with a clean output path: existing PDFs receive
versioned filenames in noninteractive runs. Cache the Python environment only
within the same OS, Python installation, and checkout path. The npm lockfile
does not lock Python dependencies or downloaded fonts/browser assets.

### Test packaging before publication

```sh
npm pack
# From a separate consumer repository, use the resulting tarball:
npm install --save-dev /path/to/avandar-markdown-to-pdf-VERSION.tgz
```

`npm pack` synchronizes the npm version from `main.py`; change `__version__`
there for releases. The tarball includes only the CLI runtime, shell entry
points, version script, and package documentation/license. No programmatic
JavaScript API is provided. `npm run test:npm` tests packed local/global
installations using temporary directories (requires network and Python).
The integration test currently targets POSIX systems; Windows launcher support
has not been verified.

## Install

```sh
git clone https://github.com/AvandarLabs/markdown-to-pdf.git
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
between them in smaller type, which suits a glossary or steps a reader follows
rather than studies: prose, list numbers, and tables all drop 1.5 points (a
table still never below 8 points), code blocks shrink by the same proportion
(never below 7 points), and the space between blocks halves. GitHub keeps `<sup>` but
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
