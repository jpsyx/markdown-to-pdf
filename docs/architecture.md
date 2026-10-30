# Architecture

`markdown-to-pdf` renders a Markdown file to a styled PDF using ReportLab's
`platypus` flowable model. It is a single-module tool (`main.py`) with a thin
shell entry point (`markdown-to-pdf.sh`).

## Flow

```
run.sh <file.md> [<path> | --out <path>]
  └─ exec python3 main.py <file.md> [<path> | --out <path>]
       ├─ read + normalize the Markdown text
       ├─ parse_markdown() → a list of ReportLab Flowables (the "story")
       └─ convert_markdown_to_pdf() → SimpleDocTemplate.build(story) → PDF
```

## Entry point (`run.sh`)

`install.sh` provisions or repairs the private Python environment, installs the
runtime requirements, and optionally provisions Mermaid and its browser.
It uses `npm ci` to preserve the committed dependency graph and avoid rewriting
tracked manifests during installation. Release version synchronization updates
both `package.json` and the root metadata in `package-lock.json`.
It publishes one executable launcher atomically in `BIN_DIR` (default
`$HOME/.local/bin`), named `markdown-to-pdf` unless `--name <command>` selects
another filename. Reinstalling the same name replaces it. Argument validation
and help happen before installation. The launcher forwards arguments to
`run.sh` and explains how to reinstall if that checkout has moved.

A stable, name-frozen entry point. It resolves its own directory via
`BASH_SOURCE` and execs `python3 main.py "$@"`, so it works regardless of the
absolute checkout path and can be run directly by anyone.

## `main.py` in layers

- **Fonts & color** (`register_font_family`, `_get_emoji_font`,
  `_download_noto_emoji`, `_wrap_emojis`): register three text families from
  candidate ladders, and lazily fetch/cache a Noto emoji font under
  `~/.cache/markdown-to-pdf/` so emoji render. Terminal color helpers
  (`_Color`, `_color`) are for CLI messages.

  The families are a serif for body text (Charter, then Iowan Old Style, then
  DejaVu/Liberation, then Constantia, falling back to base-14 Times), a
  humanist sans for headings (Avenir Next, DejaVu Sans, Segoe UI, falling back
  to Helvetica), and a monospace for code (Menlo, DejaVu Sans Mono, Consolas,
  falling back to Courier). Each candidate declares a file and a subfont index
  per style, so a `.ttc` collection and a one-file-per-style platform both work,
  and `registerFontFamily` is what makes `<b>` and `<i>` inside a paragraph
  resolve to real faces rather than silently rendering as regular.

  Two notes worth keeping. Helvetica is not the body default because it is a
  signage grotesque whose `I`, `l` and `1` are near-identical, which is costly
  in a document full of identifiers; it survives only as the fallback that needs
  no file. And SF Mono is deliberately not a candidate: the only weight macOS
  ships at `/System/Library/Fonts/SFNSMono.ttf` is Light, which prints anaemic.
- **Styles** (`make_styles`): builds the `ParagraphStyle` set (headings, body,
  code, callouts, tables) and the page geometry constants (margins, brand colors).
  Inline code sits 2 pt below its surrounding text (8.5 pt in the default
  10.5 pt body and tables), so the monospace face does not overpower the serif.
  Fenced code uses 8.5 pt type with 11.5 pt leading; `--font-shrink` retains
  its 7 pt type and 9.5 pt leading floors for these blocks.
- **Inline markup** (`normalize_text`, `_extract_code_spans`, `inline_markup`):
  pure string transforms that turn Markdown inline syntax (bold/italic, inline
  code) into ReportLab's mini-HTML. These are the most logic-dense, edge-case
  heavy functions, so they are covered directly by `test_inline_markup.py`.
- **Line breaks** (`split_hard_break`, `append_soft_line`, `join_soft_lines`):
  pure helpers implementing Markdown's break rules. Only two trailing spaces or
  a trailing backslash are a real break; every other newline is a *soft* break
  that folds into a space. The break travels through `inline_markup` as the
  control character `HARD_BREAK`, because `escape()` would otherwise turn a
  literal `<br/>` into visible text. Getting this wrong is what turned each
  wrapped bullet into its own one-item list with an orphaned paragraph after
  it, so `parse_markdown` also implements CommonMark lazy continuation: a line
  that neither opens a block nor starts an item folds onto the item above.
- **Block builders** (`paragraph`, `callout_box`, `code_block`, `blockquote`,
  `render_table`, and the `flush_*` helpers): turn buffered lines into Flowables.
- **Fence meta** (`parse_fence_info`): the text after ``` is a language plus an
  optional highlight spec, `{2,4-6}`, 1-based to match what a reader counts.
  Parsing is deliberately permissive: any brace group is taken as the spec, so
  a typo inside it costs the highlighting and not the language tag with its
  syntax colouring.
- **Line highlighting** (`highlight_to_xpre_lines`, `_highlighted_code_table`):
  a fence with a highlight spec becomes one table row per source line, so a
  called-out line can carry a background across the full block width. A single
  cell cannot do that, because `backColor` on a font tag stops at the end of the
  glyphs. Tokenizing still happens once over the whole source, so multi-line
  constructs are recognized, and each token's value is then split on newlines;
  splitting the *markup* instead would leave an unclosed `<font>` on one line
  and a stray closing tag on the next.
- **Syntax highlighting** (`highlight_to_xpre`): a tagged fence is tokenized by
  Pygments and emitted as one `<font color>` span per token, into an
  `XPreformatted`. This deliberately does not use `reportlab.lib.pygments2xpre`,
  which post-processes Pygments' HTML with the greedy pattern
  `<span class=".*">` and therefore collapses everything between the first and
  last span on a line, silently deleting code (`const x: number = 1;` came back
  as `const ;`). An unknown language tag falls back to plain rendering.
- **Mermaid** (`find_mermaid_renderer`, `render_mermaid`, `mermaid_fit`,
  `mermaid_block`): a ```mermaid fence shells out to `mermaid-cli`, which needs
  a headless browser, and embeds the resulting PNG. Rendering happens at
  `MERMAID_SCALE` and is scaled back down so print stays sharp, inside a
  `MERMAID_VIEWPORT_WIDTH` viewport so mermaid does not pre-shrink a wide
  diagram before this tool sees it. `mermaid_fit` then scales the result to the
  content box and is deliberately NOT capped at 1.0, so exactly one scaling
  decides the printed size. The whole path is optional by design: with no
  renderer the fence degrades to a plain code block carrying the diagram
  source, and the tool warns once on stderr.
- **Figures** (`is_diagram_caption`, `_measure`, `_shrink_caption`,
  `group_diagram_figures`): a pass over the finished story binds each diagram
  to the explanation that follows it, up to and including its italic caption,
  and wraps the group in `KeepTogether`. It runs after parsing because a
  caption's height can only be measured once it is a flowable. The drawing is
  re-fitted to the page minus that height, minus `FIGURE_SLACK`, since a group
  needing the whole content height can never be placed. Past
  `MIN_DIAGRAM_HEIGHT_FRACTION` the explanation is shrunk instead, by
  rebuilding its paragraphs against a copied style. Preceding headings join
  the group and reserve their own height, even without a caption, preventing
  heading-only pages before tall diagrams. The drawing never drops below that
  floor: an explanation too long to shrink into the remaining room runs on to
  the next page instead of crushing the drawing.
- **Caption boxes** (`figure_caption_box`, `is_figure_caption_box`): a
  blockquote straight after a diagram or an image is parsed as a document of
  its own, against `small_styles`, and set in a shaded single-cell table. It
  keeps its source in `_figure_caption_source`, so `_shrink_caption` rebuilds
  it at a smaller scale rather than editing its flowables. Inside the box a
  wholly bold paragraph becomes a small capitals label (`_caption_label_style`)
  and a table is parsed without borders, with tightened padding. Grouping
  treats the box as the diagram's whole explanation, and keeps an image with
  its box.
- **Code wrapping** (`code_columns`, `_segment_code_line`, `wrap_code_line`,
  `wrap_code_markup`): ReportLab's `Preformatted`/`XPreformatted` do not wrap,
  so a long line overflowed the frame and its tail was lost. Lines are broken
  to `code_columns` before they reach a flowable. Highlighted code is lexed
  first and its markup wrapped second, so the lexer never sees a split string;
  `wrap_code_markup` counts visible characters only and closes and reopens any
  span left open at a break.
- **Local images** (`_resolve_local_image_path`, `local_image_block`): a
  standalone Markdown image resolves relative to the input file, rejects URI
  schemes, and becomes an `Image` flowable. The image keeps its aspect ratio,
  fits within the page's content area, and is never enlarged.
- **Tables** (`_split_table_cells`, `_parse_table_row`, `_table_markup`,
  `_fit_table`, `fit_column_widths`, `_ReadableTable`, `render_table`). Rows are
  split on *unescaped* pipes, so `\|` is a literal pipe inside a cell rather
  than a cell boundary that shifts every later cell right. `_fit_table` measures
  fresh Paragraphs at candidate widths, preserving actual bold/code/emoji font
  metrics. For each font size it searches for the narrowest column that avoids
  overflow and averages at least two source words per line in every multiword
  body cell. It retries in 0.5-point steps down to an 8-point floor. If the
  density target still cannot fit, width transfers minimize overflow first,
  then density deficits and total row height. Cached measurements and bounded
  searches keep the work finite. Header words remain intact; body cells can
  break at existing hyphens and slashes, without arbitrary character splitting.
  Inline code shares the 8-point floor. Each table owns copied styles, leaving
  other tables and body text unchanged. Tables span `CONTENT_WIDTH`, accounting
  for the frame padding. `_ReadableTable` repeats headers and splits within a
  row only when that row cannot fit on a fresh page.
- **Parser** (`parse_markdown`): the line-oriented state machine that walks the
  Markdown and dispatches to the block builders, flushing buffers at boundaries.
- **Page numbers** (`page_number_text`, `draw_page_footer`, `NumberedCanvas`):
  each page is stamped with its bare number in the bottom margin, under the
  frame, so numbering costs no content height and changes no pagination. A
  one-page document is left unnumbered, and that is what needs the second pass:
  whether there is more than one page is only known once the whole story is
  laid out, which is after page one has been drawn. `NumberedCanvas` therefore
  holds each finished page as saved canvas state and replays them from
  `save()`, adding the footer once the count is known.
- **Decorations** (`decoration_markup`, `_decoration_image`,
  `_custom_font_family`, `_conversion_layout`, `_draw_decorations`): validate
  local raster artwork, finite geometry/opacity, safe text markup, and local
  TTFs before selecting or opening an output. The text parser allows only a
  small HTML subset plus inline Markdown and never accepts resource-bearing
  tags or links. Per-conversion layout scopes restore the existing global
  font/geometry values, even on failure, so the legacy block builders use the
  selected margins without leaking them into another conversion. Font names
  derive from file content; every custom family registers all four styles,
  falling back within that family rather than mixing unrelated typefaces.
  A page callback paints the watermark first, then the header and footer,
  before document flowables. Header/footer geometry reserves space in the
  text frame. A shaded callout flowable is prepended exactly once. The numbered
  canvas keeps its existing two-pass behavior and moves numbers right only
  when a custom footer is present. ReportLab invariant mode is opt-in through
  `--deterministic`; no default decoration or typography changes occur.
- **Output** (`resolve_output_path`, `versioned_path`, `_prompt_overwrite`,
  `convert_markdown_to_pdf`, `main`): resolve a file or directory output path
  (non-interactive mode writes a `-vN` variant
  rather than overwriting), build the document, and handle CLI arguments.

## Testing

`python3 -m unittest test_install -v` checks named/repeated installation without
modifying tracked package manifests,
side-effect-free help and invalid arguments, real virtualenv repair and Python
dependency installation, optional Mermaid provisioning with a failed browser
download, conversion without Node, and the moved-checkout diagnostic. These
checks use isolated output directories and preserve the existing rendering
suite below.

`test_inline_markup.py` (stdlib `unittest`) pins the inline-markup behavior —
the emphasis rules, underscore-in-identifiers literals, and code-span
extraction — plus table row splitting, column fitting, soft and hard line
breaks, list continuation, local images, syntax highlighting, and mermaid
rendering. Two of
those suites assert a dependency directly (`pygments` is importable, a mermaid
renderer resolves), because both features degrade silently when the dependency
is absent and no behavioral test would notice. New parsing behavior
should be added test-first here (red/green). The rendering/IO layers are
exercised by running the tool on real Markdown.

Decoration tests decode real PDF content streams and assert image transforms,
paint order, repeated footer content, effective text opacity, first-page-only
notices, custom fonts, margins, state restoration, deterministic bytes, and
validation before destination creation. They use ReportLab's bundled Vera TTFs
and generated local raster fixtures, without a PDF-reader dependency.
