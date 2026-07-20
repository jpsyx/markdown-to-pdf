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

- **Fonts & color** (`_register_mono_font`, `_get_emoji_font`,
  `_download_noto_emoji`, `_wrap_emojis`): register a monospace font for code,
  and lazily fetch/cache a Noto emoji font under `~/.cache/markdown-to-pdf/` so
  emoji render. Terminal color helpers (`_Color`, `_color`) are for CLI messages.
- **Styles** (`make_styles`): builds the `ParagraphStyle` set (headings, body,
  code, callouts, tables) and the page geometry constants (margins, brand colors).
- **Inline markup** (`normalize_text`, `_extract_code_spans`, `inline_markup`):
  pure string transforms that turn Markdown inline syntax (bold/italic, inline
  code) into ReportLab's mini-HTML. These are the most logic-dense, edge-case
  heavy functions, so they are covered directly by `test_inline_markup.py`.
- **Block builders** (`paragraph`, `callout_box`, `code_block`, `blockquote`,
  `render_table`, and the `flush_*` helpers): turn buffered lines into Flowables.
- **Parser** (`parse_markdown`): the line-oriented state machine that walks the
  Markdown and dispatches to the block builders, flushing buffers at boundaries.
- **Output** (`versioned_path`, `_prompt_overwrite`, `convert_markdown_to_pdf`,
  `main`): resolve the output path (non-interactive mode writes a `-vN` variant
  rather than overwriting), build the document, and handle CLI arguments.

## Testing

`test_inline_markup.py` (stdlib `unittest`) pins the inline-markup behavior —
the emphasis rules, underscore-in-identifiers literals, and code-span
extraction. New parsing behavior should be added test-first here (red/green).
The rendering/IO layers are exercised by running the tool on real Markdown.
