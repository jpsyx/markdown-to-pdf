# markdown-to-pdf

Convert a Markdown file to a styled PDF. A small Python tool (built on
[ReportLab](https://pypi.org/project/reportlab/)) with a thin shell entry point.

## Usage

```sh
./run.sh <file.md>                 # write <file>.pdf next to the input
./run.sh <file.md> --out out.pdf   # explicit output path
```

## Requirements

- Python 3
- `reportlab` (`pip install -r requirements.txt`)

## Layout

- `run.sh` — entry point; resolves its own dir and execs `python3 main.py`.
- `main.py` — the converter (argument parsing, Markdown → PDF rendering).
- `test_inline_markup.py` — unit tests for inline-markup parsing.
- `docs/architecture.md` — how the converter is structured.

## Development

Run the tests (`unittest`):

```sh
python3 test_inline_markup.py
```
