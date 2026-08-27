# Architecture

`markdown-to-pdf` renders a Markdown file to a styled PDF using ReportLab's
`platypus` flowable model. It is a single-module tool (`main.py`) with a thin
shell entry point (`markdown-to-pdf.sh`).

## Flow

```
run.sh <file.md> [--out <path>]
  └─ exec python3 main.py <file.md> [--out <path>]
       ├─ read + normalize the Markdown text
       ├─ parse_markdown() → a list of ReportLab Flowables (the "story")
       └─ convert_markdown_to_pdf() → SimpleDocTemplate.build(story) → PDF
```

## Entry point (`run.sh`)

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
- **Mermaid** (`find_mermaid_renderer`, `render_mermaid`, `mermaid_block`): a
  ```mermaid fence shells out to `mermaid-cli`, which needs a headless browser,
  and embeds the resulting PNG. Rendering happens at `MERMAID_SCALE` and is
  scaled back down so print stays sharp. The whole path is optional by design:
  with no renderer the fence degrades to a plain code block carrying the
  diagram source, and the tool warns once on stderr.
- **Tables** (`_split_table_cells`, `_parse_table_row`, `measure_column_widths`,
  `fit_column_widths`, `render_table`). Two pieces are worth knowing. Rows are
  split on *unescaped* pipes, so `\|` is a literal pipe inside a cell rather
  than a cell boundary that shifts every later cell right. Columns are then
  sized to their content: each column is measured for its longest word and its
  widest cell, and `fit_column_widths` — pure arithmetic, unit-tested — shares
  the text block out between them, so an index or checkbox column stays narrow
  and prose columns get the room. The table always spans the full text block.
- **Parser** (`parse_markdown`): the line-oriented state machine that walks the
  Markdown and dispatches to the block builders, flushing buffers at boundaries.
- **Output** (`resolve_output_path`, `versioned_path`, `_prompt_overwrite`,
  `convert_markdown_to_pdf`, `main`): resolve a file or directory output path
  (non-interactive mode writes a `-vN` variant
  rather than overwriting), build the document, and handle CLI arguments.

## Testing

`test_inline_markup.py` (stdlib `unittest`) pins the inline-markup behavior —
the emphasis rules, underscore-in-identifiers literals, and code-span
extraction — plus table row splitting, column fitting, soft and hard line
breaks, list continuation, syntax highlighting, and mermaid rendering. Two of
those suites assert a dependency directly (`pygments` is importable, a mermaid
renderer resolves), because both features degrade silently when the dependency
is absent and no behavioral test would notice. New parsing behavior
should be added test-first here (red/green). The rendering/IO layers are
exercised by running the tool on real Markdown.
