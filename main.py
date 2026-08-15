#!/usr/bin/env python3
"""
Markdown-to-PDF Converter

A generic markdown-to-PDF converter that produces a clean, textbook-style PDF.
The visual system:

- US Letter pages: 612 x 792 pt
- Helvetica / Helvetica-Bold / Helvetica-Oblique
- Chapter title: #1F4E79, 22 pt, bold
- Section headings: #2E75B6, 14 pt, bold
- Body text: #000000, 10.5 pt, 15 pt leading
- Left/right margins: 62.2 pt
- Top margin: 56.3 pt
- No page numbers, headers, or footers
- Emoji glyphs render through a monochrome Noto Emoji TTF (cached under
  ~/.cache/markdown-to-pdf/), downloaded on first use; Apple Symbols is a
  partial fallback if the download fails.

Usage:
    python main.py chapter.md
    python main.py chapter.md --out chapter.pdf
    python main.py chapter.md --black-text

If the output path already exists, the script prompts to overwrite or to
append a version (-v2, -v3, ...). Non-interactive runs default to appending
a version.
"""

from __future__ import annotations

# Tool version (semver). Single source of truth. Bump on every commit that is
# pushed to main, per AGENTS.md: patch for fixes, minor for features, major for
# breaking CLI changes. Surfaced via `--version` / `-v`.
__version__ = "0.4.2"

import argparse
import html
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)

try:
    from reportlab.lib.pygments2xpre import pygments2xpre
    from pygments.util import ClassNotFound
    _PYGMENTS_AVAILABLE = True
except ImportError:
    pygments2xpre = None
    ClassNotFound = Exception
    _PYGMENTS_AVAILABLE = False


def _register_mono_font() -> str:
    """Register a Unicode-capable monospace TTF for code blocks.

    The default PDF Courier is a Type 1 font limited to WinAnsi; characters
    outside that set (box-drawing, em dashes already normalized away, etc.)
    render as tofu. Walk a small set of platform-specific candidate paths and
    register the first one that exists under the name "MDCodeMono". If none
    are available, fall back to plain Courier and accept the tofu risk.
    """
    candidates = [
        "/System/Library/Fonts/SFNSMono.ttf",                       # macOS SF Mono
        "/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",      # Debian/Ubuntu
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",               # Fedora/Arch
        "C:\\Windows\\Fonts\\consola.ttf",                          # Windows Consolas
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("MDCodeMono", path))
                return "MDCodeMono"
            except Exception:
                continue
    return "Courier"


CODE_FONT = _register_mono_font()

# WinAnsi codes that Adobe (and so ReportLab) aliases to `bullet` purely because
# they are otherwise unused. Strict decoder tables leave them undefined, so a
# bullet written at one of these comes back as `(cid:127)` or disappears. 149 is
# the single code both the loose and the strict tables call `bullet`.
_BULLET_ALIAS_CODES = (127, 129, 141, 143, 144, 157)
_BULLET_CODE = 149


def _register_bullet_font() -> str:
    """Register a Helvetica that encodes U+2022 at a code every reader knows.

    ReportLab encodes `•` at the lowest WinAnsi code named `bullet`, which is
    127 — a code the strict WinAnsi table does not define. The glyph draws
    correctly, but pdfminer, pypdf and poppler all fail to recover it, so list
    bullets are lost to copy/paste, search and screen readers. Clone WinAnsi
    with the ambiguous aliases dropped and `•` pinned to 149.

    Falls back to plain Helvetica if ReportLab's codec internals move; that
    restores the unextractable bullet rather than breaking rendering, and the
    test suite fails loudly when it happens.
    """
    try:
        from reportlab.pdfbase.rl_codecs import RL_Codecs

        # Derive the tables from the stock WinAnsi codec rather than hardcoding
        # them, so this stays correct if ReportLab revises the encoding. Codes
        # 0-31 are undefined in WinAnsi and simply drop out.
        decoded: dict[int, int] = {}
        for code in range(256):
            try:
                decoded[code] = ord(bytes([code]).decode("WinAnsiEncoding"))
            except Exception:
                continue
        decoding_map = {code: char for code, char in decoded.items() if code not in _BULLET_ALIAS_CODES}
        # Highest code first, so the lowest (canonical) code wins each character
        # — e.g. a space encodes to 32, not to the 160 that also decodes to it.
        encoding_map = {decoded[code]: code for code in sorted(decoded, reverse=True) if code not in _BULLET_ALIAS_CODES}
        encoding_map[ord("•")] = _BULLET_CODE
        # Dynamic codecs take (encoding_map, decoding_map) in that order.
        RL_Codecs.add_dynamic_codec("bulletsafewinansi", encoding_map, decoding_map)
        RL_Codecs.register()

        encoding = pdfmetrics.Encoding("BulletSafeWinAnsi", base="WinAnsiEncoding")
        for code in _BULLET_ALIAS_CODES:
            encoding[code] = None
        pdfmetrics.registerEncoding(encoding)
        pdfmetrics.registerFont(pdfmetrics.Font("Helvetica-BulletSafe", "Helvetica", "BulletSafeWinAnsi"))
        if "•".encode("BulletSafeWinAnsi") != bytes([_BULLET_CODE]):
            return "Helvetica"
        return "Helvetica-BulletSafe"
    except Exception:
        return "Helvetica"


BULLET_FONT = _register_bullet_font()


class _Color:
    """ANSI color codes for terminal output.

    Bright variants (9x) are chosen so colored text stays legible on a black
    terminal background. Dark blue (34) and dark magenta (35) are intentionally
    omitted because they wash out on dark backgrounds.
    """

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"


def _supports_color(stream=None) -> bool:
    """Return True if ANSI color codes should be emitted on `stream`.

    Honors the standard NO_COLOR convention (https://no-color.org). Defaults
    to checking stdout when no stream is given.
    """
    s = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(s.isatty())
    except (AttributeError, ValueError):
        return False


def _color(text: str, *codes: str, stream=None) -> str:
    """Wrap `text` in ANSI escape codes when the target stream supports color."""
    if not _supports_color(stream):
        return text
    return "".join(codes) + text + _Color.RESET


# Emoji-rendering support.
#
# ReportLab can only render fonts whose outlines it can extract. macOS's Apple
# Color Emoji is sbix (bitmap-based), so we can't use it — emojis come out as
# tofu in the default Helvetica run. The fix is to register a monochrome
# emoji-capable TTF, then wrap emoji codepoints in <font name="..."> spans so
# they pick up that font.
#
# Preferred font is Noto Emoji (monochrome) — full Unicode emoji coverage,
# permissive license, ~430 KB. Cached at ~/.cache/markdown-to-pdf/ and
# downloaded on first run where the source markdown actually contains emoji.
# Apple Symbols is the partial fallback (covers ⚙ ⌛ ⚠ arrows but misses 1F4xx
# pictographs).

_NOTO_EMOJI_URL = (
    # Monochrome Noto Emoji variable font, served from the google/fonts repo.
    # The googlefonts/noto-emoji repo only ships the color (CBDT/COLR) builds,
    # which ReportLab cannot rasterize — so we point at the OFL variable font
    # in google/fonts instead.
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf"
)
_EMOJI_CACHE_DIR = Path.home() / ".cache" / "markdown-to-pdf"
_EMOJI_CACHE_PATH = _EMOJI_CACHE_DIR / "NotoEmoji-Variable.ttf"

EMOJI_RE = re.compile(
    "[⌀-⏿"            # Misc Technical (⌛ ⌨ ⏰ ⏳ ...)
    "①-⓿"             # Enclosed Alphanumerics
    "■-➿"             # Misc Symbols, Dingbats (★ ☀ ☎ ✂ ✅ ✈ ✨ ...)
    "⬀-⯿"             # Misc Symbols and Arrows (⬇ ⭐ ...)
    "〰〽㊗㊙"  # Stray CJK symbols used as emoji
    "\U0001F000-\U0001FAFF"     # All SMP emoji ranges (😀 💡 📝 🎉 🚀 🔥 🌍 ...)
    "]️?"                  # Optional variation selector
)


_emoji_font_name: str | None = None
_emoji_font_tried: bool = False


def _try_register_emoji_font(path: Path, registered_name: str) -> bool:
    """Register `path` as `registered_name`. Returns True on success."""
    try:
        pdfmetrics.registerFont(TTFont(registered_name, str(path)))
        return True
    except Exception:
        return False


def _download_noto_emoji() -> bool:
    """Fetch Noto Emoji to the cache. Returns True on success.

    Prints a yellow status line to stderr so the user knows why the first run
    is slower than subsequent ones.
    """
    import urllib.request

    print(
        _color(
            f"Downloading Noto Emoji (one-time, ~2 MB) → {_EMOJI_CACHE_PATH}",
            _Color.YELLOW,
            stream=sys.stderr,
        ),
        file=sys.stderr,
    )
    try:
        _EMOJI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(_NOTO_EMOJI_URL, timeout=30) as resp:
            data = resp.read()
        # Sanity check: a real TTF starts with 0x00010000 or "OTTO"/"true"/"typ1"
        # and is at least ~50 KB. Reject anything obviously wrong (e.g. an HTML
        # error page returned by a proxy).
        if len(data) < 50_000 or data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
            print(
                _color(
                    "warning: Noto Emoji download returned unexpected data; skipping.",
                    _Color.YELLOW,
                    stream=sys.stderr,
                ),
                file=sys.stderr,
            )
            return False
        _EMOJI_CACHE_PATH.write_bytes(data)
        print(
            _color("Emoji font ready.", _Color.GREEN, stream=sys.stderr),
            file=sys.stderr,
        )
        return True
    except Exception as e:
        print(
            _color(
                f"warning: emoji font download failed ({e}); emojis may render as tofu.",
                _Color.YELLOW,
                stream=sys.stderr,
            ),
            file=sys.stderr,
        )
        return False


def _get_emoji_font() -> str | None:
    """Return the registered emoji font name, or None if no font is available.

    Lazy and memoized: the font is only registered (or downloaded) on the
    first call. Subsequent calls return the cached result.
    """
    global _emoji_font_name, _emoji_font_tried
    if _emoji_font_tried:
        return _emoji_font_name
    _emoji_font_tried = True

    if _EMOJI_CACHE_PATH.exists() and _try_register_emoji_font(_EMOJI_CACHE_PATH, "MDEmoji"):
        _emoji_font_name = "MDEmoji"
        return _emoji_font_name

    if _download_noto_emoji() and _try_register_emoji_font(_EMOJI_CACHE_PATH, "MDEmoji"):
        _emoji_font_name = "MDEmoji"
        return _emoji_font_name

    apple_symbols = Path("/System/Library/Fonts/Apple Symbols.ttf")
    if apple_symbols.exists() and _try_register_emoji_font(apple_symbols, "MDEmoji"):
        _emoji_font_name = "MDEmoji"
        return _emoji_font_name

    return None


def _wrap_emojis(text: str) -> str:
    """Wrap each emoji codepoint in a <font name="MDEmoji">...</font> span.

    Must be called after `escape()` so the inserted XML tags survive into the
    Paragraph renderer. Bails out cheaply when there are no emoji characters
    in the text, which avoids ever loading the emoji font for plain content.
    """
    if not EMOJI_RE.search(text):
        return text
    font = _get_emoji_font()
    if font is None:
        return text
    return EMOJI_RE.sub(lambda m: f'<font name="{font}">{m.group(0)}</font>', text)


CHAPTER_BLUE = colors.HexColor("#1F4E79")
SECTION_BLUE = colors.HexColor("#2E75B6")
BODY_COLOR = colors.HexColor("#000000")
BLACK = colors.HexColor("#000000")
CALLOUT_FILL = colors.HexColor("#EAF4FB")
CALLOUT_BORDER = SECTION_BLUE
CODE_FILL = colors.HexColor("#F3F4F6")
TABLE_HEADER_FILL = colors.HexColor("#F3F4F6")
TABLE_BORDER = colors.HexColor("#D1D5DB")
LINK_COLOR = colors.HexColor("#1155CC")
_BLACK_TEXT = False

# Base directory used to resolve *relative file* links to absolute file:// URIs
# so they open on click. Set by convert_markdown_to_pdf() to the input .md's
# parent. inline_markup() reads it only as a fallback when no explicit base_dir
# is passed, so the string helper stays deterministic/testable.
_LINK_BASE_DIR: str | None = None

PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT_MARGIN = 56.2  # ReportLab frame padding adds 6 pt, yielding sample x=62.2
RIGHT_MARGIN = 56.2
TOP_MARGIN = 51.8   # ReportLab frame padding plus title metrics yield sample y=56.3
BOTTOM_MARGIN = 42.0

# Room a table cell keeps for its content once its padding is paid for. Below
# roughly this, a cell cannot seat a single glyph and ReportLab raises rather
# than clipping, so it is a floor on column width and not a style choice.
MIN_CELL_CONTENT_WIDTH = 6.0


def versioned_path(path: Path) -> Path:
    if not path.exists():
        return path
    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    match = re.match(r"^(.*)-v(\d+)$", stem)
    if match:
        root = match.group(1)
        version = int(match.group(2)) + 1
    else:
        root = stem
        version = 2
    while True:
        candidate = parent / f"{root}-v{version}{suffix}"
        if not candidate.exists():
            return candidate
        version += 1


def normalize_text(text: str) -> str:
    replacements = {
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "−": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        " ": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _extract_code_spans(text: str) -> tuple[str, list[str]]:
    # CommonMark code spans: an opening run of N backticks is closed by the
    # next run of EXACTLY N backticks (so ``` ... ``` works inline, and a
    # double-tick span can contain a single tick). We extract spans up-front,
    # stash their content, and leave a placeholder behind so the bold/italic
    # passes can't see backticks/asterisks inside code.
    spans: list[str] = []
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "`":
            out.append(text[i])
            i += 1
            continue
        j = i
        while j < n and text[j] == "`":
            j += 1
        opening_len = j - i
        k = j
        close_start = -1
        while k < n:
            if text[k] != "`":
                k += 1
                continue
            m = k
            while m < n and text[m] == "`":
                m += 1
            if m - k == opening_len:
                close_start = k
                break
            k = m
        if close_start == -1:
            out.append(text[i:j])
            i = j
            continue
        content = text[j:close_start]
        if len(content) >= 2 and content.startswith(" ") and content.endswith(" ") and content.strip():
            content = content[1:-1]
        spans.append(content)
        out.append(f"\x01CODE{len(spans) - 1}\x01")
        i = close_start + opening_len
    return "".join(out), spans


def _emphasis(text: str) -> str:
    """Apply bold/italic (`**`,`*`,`__`,`_`) markdown emphasis to escaped text."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    # Underscore emphasis. Guarded by word boundaries so intraword underscores
    # (snake_case, file_name.py) stay literal, per CommonMark. Bold (__) runs
    # before italic (_) so a __run__ isn't half-consumed by the single-_ pass.
    text = re.sub(r"(?<![\w_])__(\S(?:.*?\S)?)__(?![\w_])", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w_])_(\S(?:.*?\S)?)_(?![\w_])", r"<i>\1</i>", text)
    return text


# Markdown inline link: [text](target). Not preceded by ! (that's an image).
# Target is any run without whitespace or a closing paren.
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")
_EXTERNAL_HREF_RE = re.compile(r"^(?:https?|mailto|tel|ftp|file):", re.IGNORECASE)


def _extract_links(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace `[text](target)` with sentinels, returning (text, [(text, target)])."""
    links: list[tuple[str, str]] = []

    def repl(match: re.Match) -> str:
        links.append((match.group(1), match.group(2)))
        return f"\x02LINK{len(links) - 1}\x02"

    return _LINK_RE.sub(repl, text), links


def _resolve_href(href: str, base_dir: str | None) -> str:
    """Resolve a link target for the PDF.

    External schemes (http/https/mailto/tel/ftp/file) and in-doc anchors (`#…`)
    pass through unchanged — a URL annotation opens them in the default browser.
    A *relative file path* is resolved against `base_dir` and returned as an
    absolute `file://` URI so clicking it opens the file with the OS default
    handler (macOS: same as `open`). Without a base dir the path is left as-is.
    """
    h = href.strip()
    if not h or h.startswith("#") or _EXTERNAL_HREF_RE.match(h):
        return h
    if base_dir:
        try:
            return (Path(base_dir) / h).resolve().as_uri()
        except (ValueError, OSError):
            return h
    return h


def inline_markup(text: str, base_dir: str | None = None) -> str:
    if base_dir is None:
        base_dir = _LINK_BASE_DIR
    text = normalize_text(text)
    text, code_spans = _extract_code_spans(text)
    # Pull links out before escaping so hrefs stay raw and their text/targets
    # are not mangled by emphasis passes; they are rebuilt as <a> tags last.
    text, links = _extract_links(text)
    text = escape(text)
    text = _emphasis(text)

    def _restore(match: re.Match) -> str:
        idx = int(match.group(1))
        body = escape(code_spans[idx])
        return f'<font name="Courier" backColor="{CODE_FILL.hexval()}">{body}</font>'

    text = re.sub(r"\x01CODE(\d+)\x01", _restore, text)

    if links:

        def _restore_link(match: re.Match) -> str:
            label, target = links[int(match.group(1))]
            inner = _emphasis(escape(label))
            href = _resolve_href(target, base_dir)
            href_attr = escape(href, {'"': "&quot;"})
            link_color = BLACK if _BLACK_TEXT else LINK_COLOR
            return (
                f'<a href="{href_attr}" color="{link_color.hexval()}" '
                f'underline="0">{inner}</a>'
            )

        text = re.sub(r"\x02LINK(\d+)\x02", _restore_link, text)

    text = _wrap_emojis(text)
    return text


def make_styles(font_shrink: float = 0.0, *, black_text: bool = False) -> dict[str, ParagraphStyle]:
    """Build the paragraph style sheet.

    `font_shrink` (points) is subtracted from every style's fontSize and
    leading. Used by the agenda flow as a last-resort fit to keep the
    printed PDF inside 2 pages without touching the default look for
    every other markdown-to-pdf invocation.
    """
    s = float(font_shrink)
    chapter_color = BLACK if black_text else CHAPTER_BLUE
    section_color = BLACK if black_text else SECTION_BLUE
    body_color = BLACK if black_text else BODY_COLOR
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "MDChapterTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22 - s,
            leading=26.4 - s,
            textColor=chapter_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=20,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "MDSectionHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14 - s,
            leading=17 - s,
            textColor=section_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=15,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "MDSubsectionHeading",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11.5 - s,
            leading=14.5 - s,
            textColor=section_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h4": ParagraphStyle(
            "MDMinorHeading",
            parent=base["Heading4"],
            fontName="Helvetica-Bold",
            fontSize=10.5 - s,
            leading=13 - s,
            textColor=chapter_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "MDBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5 - s,
            leading=15 - s,
            textColor=body_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=12,
        ),
        "table_cell": ParagraphStyle(
            "MDTableCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5 - s,
            leading=15 - s,
            textColor=body_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "MDTableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10.5 - s,
            leading=15 - s,
            textColor=body_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "quote_plain": ParagraphStyle(
            "MDQuotePlain",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=10.5 - s,
            leading=15 - s,
            textColor=chapter_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "callout": ParagraphStyle(
            "MDCallout",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=10.5 - s,
            leading=15 - s,
            textColor=chapter_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "bullet": ParagraphStyle(
            "MDBullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5 - s,
            leading=15 - s,
            textColor=body_color,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=4,
        ),
        # Used for "scheduled anchor" lines in an ordered checkbox list — items
        # the user can't tick off (e.g. "12:00 PM | Walk Luna"). Lives between
        # numbered list items, indented so the time column aligns with the time
        # column of the numbered rows above and below, with tight spacing so
        # the visual reads as "still in the list".
        "scheduled": ParagraphStyle(
            "MDScheduled",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5 - s,
            leading=15 - s,
            textColor=body_color,
            alignment=TA_LEFT,
            leftIndent=40,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=4,
        ),
        "code": ParagraphStyle(
            "MDCode",
            parent=base["Code"],
            fontName=CODE_FONT,
            fontSize=max(7.0, 9 - s),
            leading=max(9.5, 12 - s),
            textColor=BODY_COLOR,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=0,
        ),
    }


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(inline_markup(text), style)


def callout_box(lines: Iterable[str], style: ParagraphStyle) -> Table:
    text = " ".join(line.strip() for line in lines if line.strip())
    cell = Paragraph(inline_markup(text), style)
    table = Table([[cell]], colWidths=[PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CALLOUT_FILL),
                ("BOX", (0, 0), (-1, -1), 1.0, CALLOUT_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    table.hAlign = "LEFT"
    table.spaceBefore = 0
    table.spaceAfter = 12
    return table


def code_block(
    lines: list[str], language: str, style: ParagraphStyle, *, black_text: bool = False
) -> Table:
    # Preserve whitespace and line breaks exactly. With no language tag, use a
    # plain Preformatted (mono font, no colors). With a language tag, run the
    # source through Pygments to produce XPreformatted markup with per-token
    # <font color="..."> spans. Unknown languages fall back to plain rendering.
    text = "\n".join(lines)
    cell: Flowable
    used_highlight = False
    if language and _PYGMENTS_AVAILABLE and not black_text:
        try:
            highlighted = pygments2xpre(text, language=language)
            cell = XPreformatted(highlighted, style)
            used_highlight = True
        except (ClassNotFound, Exception):
            cell = Preformatted(text, style)
    else:
        cell = Preformatted(text, style)
    _ = used_highlight  # currently unused, reserved for future per-language styling
    table = Table([[cell]], colWidths=[PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CODE_FILL),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    table.hAlign = "LEFT"
    table.spaceBefore = 6
    table.spaceAfter = 12
    return table


def blockquote(text: str, style: ParagraphStyle) -> Table:
    cell = Paragraph(inline_markup(text), style)
    table = Table([[cell]], colWidths=[PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN])
    table.setStyle(
        TableStyle(
            [
                ("LINEBEFORE", (0, 0), (0, -1), 3.0, SECTION_BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    table.hAlign = "LEFT"
    table.spaceBefore = 4
    table.spaceAfter = 12
    return table


_TABLE_SEPARATOR_CELL_RE = re.compile(r":?-+:?")


def _is_table_separator(line: str) -> bool:
    """True if `line` is a GFM table separator row like `|---|:--:|---:|`.

    Requires a leading pipe to keep the rule unambiguous; a bare `---` is
    still rendered as a horizontal rule by the existing parser.
    """
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    cells = _parse_table_row(stripped)
    if not cells:
        return False
    for cell in cells:
        if not cell or not _TABLE_SEPARATOR_CELL_RE.fullmatch(cell):
            return False
    return True


def _split_table_cells(line: str) -> list[str]:
    """Split a GFM table row on *unescaped* pipes, keeping the escapes.

    A backslash escapes the next character, so `\\|` is a literal pipe inside a
    cell and `\\\\` is a literal backslash whose trailing pipe still separates.
    Splitting naively on `|` is what lets a title like `Opinion \\| Three
    minutes on Sudan` shift every later cell one column to the right and invent
    a phantom column at the end of the table.
    """
    cells: list[str] = []
    current: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "\\" and i + 1 < n:
            current.append(ch)
            current.append(line[i + 1])
            i += 2
            continue
        if ch == "|":
            cells.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    cells.append("".join(current))
    return cells


def _unescape_table_cell(cell: str) -> str:
    """Resolve the two escapes table splitting depends on: `\\|` and `\\\\`.

    Every other backslash escape is left for the inline-markup pass, which
    treats them literally — this only undoes what row splitting had to read.
    """
    return re.sub(r"\\([\\|])", r"\1", cell)


def _parse_table_row(line: str) -> list[str]:
    """Split a GFM table row into cell strings. Outer pipes are stripped."""
    cells = _split_table_cells(line.strip())
    # Drop the empty cells produced by the optional leading/trailing pipes.
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [_unescape_table_cell(cell.strip()) for cell in cells]


def _parse_table_alignments(separator_line: str) -> list[str]:
    """Return a list of `LEFT` / `RIGHT` / `CENTER` per column."""
    cells = _parse_table_row(separator_line)
    alignments = []
    for cell in cells:
        left = cell.startswith(":")
        right = cell.endswith(":")
        if left and right:
            alignments.append("CENTER")
        elif right:
            alignments.append("RIGHT")
        else:
            alignments.append("LEFT")
    return alignments


def _apply_width_floor(
    widths: Sequence[float],
    available: float,
    floor: float,
) -> list[float]:
    """Raise every column to `floor`, paying for it from columns that have room.

    A column narrower than its own cell padding leaves negative room for the
    cell's content, and ReportLab raises rather than clipping ("flowable given
    negative availWidth"). The floor is therefore a hard layout requirement, not
    a preference.

    Water-filling: share `available` out in proportion to the incoming widths,
    pin any column that lands under `floor`, and redistribute what is left among
    the rest. Each pass pins at least one more column, so it settles in at most
    one pass per column, and the result always sums to `available`.

    When even `floor` per column does not fit, every column gets `floor` and the
    table overflows the text block. That is visible and recoverable; a crash is
    neither.
    """
    n_cols = len(widths)
    if n_cols == 0 or floor <= 0:
        return [float(w) for w in widths]
    if n_cols * floor >= available:
        return [floor] * n_cols

    base = [max(0.0, float(w)) for w in widths]
    pinned = [False] * n_cols
    for _ in range(n_cols):
        free = [i for i in range(n_cols) if not pinned[i]]
        if not free:
            return [floor] * n_cols
        budget = available - floor * (n_cols - len(free))
        total_free = sum(base[i] for i in free)
        if total_free <= 0:
            share = budget / len(free)
            out = [floor if pinned[i] else share for i in range(n_cols)]
        else:
            out = [
                floor if pinned[i] else budget * (base[i] / total_free)
                for i in range(n_cols)
            ]
        starved = [i for i in free if out[i] < floor]
        if not starved:
            return out
        for i in starved:
            pinned[i] = True
    return [floor] * n_cols


def fit_column_widths(
    min_widths: Sequence[float],
    max_widths: Sequence[float],
    available: float,
    *,
    floor: float = 0.0,
) -> list[float]:
    """Distribute `available` points across columns from their content widths.

    `max_widths[i]` is the width column *i* needs to render its widest cell on
    one line; `min_widths[i]` is the width of its longest unbreakable word (the
    narrowest it can get without clipping). Pure arithmetic, no ReportLab —
    measuring lives in `measure_column_widths`.

    Three cases:

    - **Everything fits** — each column gets its natural width and the leftover
      slack is shared out in proportion to those widths, so the table still
      spans the text block instead of ending raggedly mid-page.
    - **Too wide** — the shortfall is charged to each column in proportion to
      how much slack it has (`max - min`), so a one-digit `#` column keeps its
      width and a prose column absorbs the wrapping.
    - **Even the minimums don't fit** — split in proportion to the minimums and
      let the cells wrap; there is no width that avoids it.

    `floor` is the narrowest a column may end up. Pass the cell's padding plus a
    little room for content: proportional splitting can otherwise hand a
    one-character column less width than its own padding, which makes ReportLab
    raise. It defaults to 0, leaving the three cases above untouched.

    The returned widths always sum to `available`.
    """
    n_cols = len(max_widths)
    if n_cols == 0:
        return []
    even = [available / n_cols] * n_cols
    mins = [max(0.0, min(float(lo), float(hi))) for lo, hi in zip(min_widths, max_widths)]
    maxs = [max(0.0, float(hi)) for hi in max_widths]

    total_max = sum(maxs)
    if total_max <= 0:
        return _apply_width_floor(even, available, floor)

    if total_max <= available:
        slack = available - total_max
        widths = [w + slack * (w / total_max) for w in maxs]
        return _apply_width_floor(widths, available, floor)

    total_min = sum(mins)
    if total_min >= available:
        widths = even if total_min <= 0 else [available * (w / total_min) for w in mins]
        return _apply_width_floor(widths, available, floor)

    flex = total_max - total_min
    shortfall = total_max - available
    widths = [hi - shortfall * ((hi - lo) / flex) for lo, hi in zip(mins, maxs)]
    return _apply_width_floor(widths, available, floor)


def _text_width(text: str, style: ParagraphStyle) -> float:
    """Width of `text` in `style`'s font, or a rough estimate if unmeasurable."""
    if not text:
        return 0.0
    try:
        return pdfmetrics.stringWidth(text, style.fontName, style.fontSize)
    except (KeyError, ValueError, UnicodeEncodeError):
        # A glyph the base-14 font can't encode (an emoji, say). Estimate
        # rather than fail: column sizing is a layout hint, not a contract.
        return len(text) * style.fontSize * 0.55


_TAG_RE = re.compile(r"<[^>]+>")


def _visible_cell_text(cell: str) -> str:
    """The text a cell actually shows: markdown resolved, markup tags removed.

    Runs the same `inline_markup` the cell will be rendered with, so a link
    measures as its label (not its URL) and emphasis markers don't count.
    """
    return html.unescape(_TAG_RE.sub("", inline_markup(cell)))


def measure_column_widths(
    columns: Sequence[Sequence[tuple[str, ParagraphStyle]]],
    padding: float,
) -> tuple[list[float], list[float]]:
    """Measure each column's (longest-word, widest-cell) width, incl. padding."""
    min_widths: list[float] = []
    max_widths: list[float] = []
    for column in columns:
        col_min = 0.0
        col_max = 0.0
        for cell, style in column:
            text = _visible_cell_text(cell)
            col_max = max(col_max, _text_width(text, style))
            for word in text.split():
                col_min = max(col_min, _text_width(word, style))
        min_widths.append(col_min + padding)
        max_widths.append(max(col_min, col_max) + padding)
    return min_widths, max_widths


def render_table(
    header: list[str],
    rows: list[list[str]],
    alignments: list[str],
    styles: dict[str, ParagraphStyle],
    *,
    borders: bool = True,
    compact: bool = False,
    agenda_tables: bool = False,
) -> Table:
    """Render a GFM table as a ReportLab Table with content-fitted columns.

    Column widths come from what the cells actually contain (see
    `fit_column_widths`), so a `#` column of single digits stays narrow and the
    space it used to waste goes to the prose columns. The table still spans the
    full text block.

    If every header cell is empty (a common pattern when the user wants a
    pure-grid layout — GFM requires a header row but the user has nothing
    to put in it), the header row is omitted entirely so the table reads
    as a clean grid of body cells.

    With `borders=False`, the cell grid is suppressed for a frameless
    layout. Padding and header-fill (if any) still apply.

    With `compact=True`, the per-cell top/bottom padding is tightened so
    multi-row reference tables (e.g. the agenda's "Today's habits" grid)
    take less vertical space. The trade-off is a more constrained look,
    which is acceptable for reference grids but not for body tables; the
    flag is opt-in per render.

    With `agenda_tables=True`, the table's left padding goes to zero so
    cells in the dense Today's habits / Completed today grids align with
    the page-left margin. Agenda-only by construction (wired exclusively
    from `--agenda`); other callers' tables are untouched.
    """
    n_cols = max(len(header), max((len(r) for r in rows), default=0), 1)
    header = header + [""] * (n_cols - len(header))
    rows = [r + [""] * (n_cols - len(r)) for r in rows]
    alignments = alignments + ["LEFT"] * (n_cols - len(alignments))

    header_is_empty = all(not cell.strip() for cell in header)
    available = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

    data: list[list[Flowable]] = []
    if not header_is_empty:
        data.append([
            Paragraph(inline_markup(cell), styles["table_header"]) for cell in header
        ])
    for row in rows:
        data.append([
            Paragraph(inline_markup(cell), styles["table_cell"]) for cell in row
        ])

    top_pad, bot_pad = (1, 1) if compact else (6, 6)
    left_pad = 0 if agenda_tables else 8
    right_pad = 8
    columns = [
        [(row[col], styles["table_cell"]) for row in rows]
        + ([] if header_is_empty else [(header[col], styles["table_header"])])
        for col in range(n_cols)
    ]
    col_widths = fit_column_widths(
        *measure_column_widths(columns, left_pad + right_pad),
        available,
        # A column has to seat its own padding plus a glyph or two, or ReportLab
        # is handed a negative content width and raises instead of wrapping.
        floor=left_pad + right_pad + MIN_CELL_CONTENT_WIDTH,
    )
    table_style: list = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), left_pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), right_pad),
        ("TOPPADDING", (0, 0), (-1, -1), top_pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), bot_pad),
    ]
    if borders:
        table_style.append(("GRID", (0, 0), (-1, -1), 0.5, TABLE_BORDER))
    if not header_is_empty and borders:
        table_style.append(("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_FILL))
    align_map = {"LEFT": "LEFT", "RIGHT": "RIGHT", "CENTER": "CENTER"}
    for col_idx, align in enumerate(alignments):
        table_style.append(("ALIGN", (col_idx, 0), (col_idx, -1), align_map[align]))

    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle(table_style))
    table.hAlign = "LEFT"
    table.spaceBefore = 2 if compact else 6
    table.spaceAfter = 4 if compact else 12
    return table


def flush_paragraph(buffer: list[str], story: list[Flowable], styles: dict[str, ParagraphStyle]) -> None:
    if buffer:
        story.append(paragraph(" ".join(buffer).strip(), styles["body"]))
        buffer.clear()


# Task-list (GFM checkbox) glyphs. Picked to be a matching same-size pair that
# both exist in the monochrome Noto Emoji TTF we ship — the obvious choice
# (U+2610 BALLOT BOX) is missing from that font and renders as a blank glyph,
# so the pair below was chosen instead after inspecting the font's cmap.
# Both codepoints sit in the EMOJI_RE range, so whichever path renders them
# (inline-text via _wrap_emojis, or per-item bullet override via bulletFontName)
# ends up in the emoji font and prints as a real square checkbox.
CHECKBOX_UNCHECKED = "◻"  # U+25FB WHITE MEDIUM SQUARE
CHECKBOX_CHECKED = "☑"    # U+2611 BALLOT BOX WITH CHECK

# Scheduled-anchor line: clock-time prefix followed by " | " and a name. Used
# inside an agenda's Suggested order for items the user can't tick (Zoom,
# walks, lunch, power-down). Matches "7:15 AM | foo", "~12:00 PM | foo",
# "9:00 PM | foo" — leading "~" is optional, AM/PM is required.
SCHEDULED_LINE_RE = re.compile(
    r"^~?\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)\s*\|\s+\S",
)


def flush_bullets(
    buffer: list[tuple[str, str, str | None, int | None]],
    story: list[Flowable],
    styles: dict[str, ParagraphStyle],
) -> None:
    if not buffer:
        return
    ordered = all(kind == "ordered" for kind, _, _, _ in buffer)
    has_checkbox = any(state is not None for _, _, state, _ in buffer)
    all_checkbox = has_checkbox and all(state is not None for _, _, state, _ in buffer)
    # Force-register the emoji font when we have any checkbox items rendered
    # as bullets — the bullet text bypasses _wrap_emojis (which only runs on
    # paragraph body text), so we need to set bulletFontName explicitly.
    checkbox_bullet_font = (_get_emoji_font() or "Helvetica") if has_checkbox else "Helvetica"

    # Honor the explicit number on the first ordered-list item when present.
    # Lets agendas split an ordered list around plain-text "scheduled" lines
    # while keeping numbering continuous (e.g. items 5, 6, 7 → blank line →
    # plain anchor → 8, 9, 10 instead of restarting at 1).
    start_number = 1
    if ordered and buffer and buffer[0][3] is not None:
        start_number = buffer[0][3]

    # Numbered checkbox lists put the checkbox FIRST and the number INSIDE the
    # text ("☑ 1. foo"), not the auto-numbered bullet ("1. ☑ foo"). The user
    # wants the box on the left so it lines up with the unordered MIT callout
    # above; the number is informational, not the primary handle. We achieve
    # this by switching to bulletType="bullet" and rendering the number as part
    # of the text. Trade-off: ReportLab no longer right-aligns the periods (so
    # "9." and "10." don't form a perfect column), but the visual hierarchy of
    # "checkbox first" matters more than period alignment for a printable plan.
    if ordered and all_checkbox:
        items: list[ListItem] = []
        for idx, (_, text, state, _) in enumerate(buffer, start=start_number):
            glyph = CHECKBOX_CHECKED if state == "checked" else CHECKBOX_UNCHECKED
            items.append(
                ListItem(
                    paragraph(f"{idx}. {text}", styles["bullet"]),
                    leftIndent=22,
                    bulletFontName=checkbox_bullet_font,
                    bulletFontSize=10.5,
                    bulletColor=BODY_COLOR,
                    value=glyph,
                )
            )
        story.append(
            ListFlowable(
                items,
                bulletType="bullet",  # per-item `value=` provides the actual bullet
                leftIndent=22,
                bulletFontName="Helvetica",
                bulletFontSize=10.5,
                bulletColor=BODY_COLOR,
                spaceBefore=0,
                spaceAfter=4,
            )
        )
        buffer.clear()
        return

    items = []
    for kind, text, state, _ in buffer:
        glyph: str | None
        if state == "checked":
            glyph = CHECKBOX_CHECKED
        elif state == "unchecked":
            glyph = CHECKBOX_UNCHECKED
        else:
            glyph = None

        item_kwargs: dict = {
            "leftIndent": 18,
            "bulletFontName": "Helvetica" if ordered else BULLET_FONT,
            "bulletFontSize": 10.5,
            "bulletColor": BODY_COLOR,
        }
        display_text = text
        if glyph is not None and ordered:
            # Ordered list with a mix of checkbox and non-checkbox items: keep
            # the auto-number, prepend the checkbox glyph to the text. (The
            # uniform-checkbox case is handled above.) `_wrap_emojis` will
            # wrap the glyph in the emoji font.
            display_text = f"{glyph} {text}"
        elif glyph is not None and not ordered:
            # Unordered + checkbox: replace the bullet point with the checkbox
            # glyph entirely. `value=` on ListItem overrides the bullet text for
            # that single item; bulletFontName must point at the emoji font or
            # Helvetica will render tofu for the ballot-box codepoint.
            item_kwargs["value"] = glyph
            item_kwargs["bulletFontName"] = checkbox_bullet_font

        items.append(ListItem(paragraph(display_text, styles["bullet"]), **item_kwargs))

    list_kwargs = {
        "bulletType": "1" if ordered else "bullet",
        "leftIndent": 18,
        # Unordered lists draw `•` from this font, so it must be the one that
        # encodes the bullet at a code every extractor can decode.
        "bulletFontName": "Helvetica" if ordered else BULLET_FONT,
        "bulletFontSize": 10.5,
        "bulletColor": BODY_COLOR,
        "spaceBefore": 0,
        "spaceAfter": 12,
    }
    if ordered:
        # `start` controls the first number for ordered lists. When passed to an
        # unordered list, ReportLab uses it as the bullet glyph itself, which
        # renders every bullet as the literal "1".
        list_kwargs["start"] = str(start_number)
    story.append(ListFlowable(items, **list_kwargs))
    buffer.clear()


def flush_quotes(buffer: list[str], story: list[Flowable], styles: dict[str, ParagraphStyle]) -> None:
    if buffer:
        # Single-line block quotes render with a left blue bar and italic blue text;
        # multi-line block quotes render as a filled callout box.
        if len(buffer) == 1:
            story.append(blockquote(buffer[0].strip(), styles["quote_plain"]))
        else:
            story.append(callout_box(buffer, styles["callout"]))
        buffer.clear()


def parse_markdown(
    markdown: str,
    *,
    table_borders: bool = True,
    compact_tables: bool = False,
    font_shrink: float = 0.0,
    agenda_tables: bool = False,
    black_text: bool = False,
) -> list[Flowable]:
    global _BLACK_TEXT
    _BLACK_TEXT = black_text
    styles = make_styles(font_shrink=font_shrink, black_text=black_text)
    story: list[Flowable] = []
    paragraph_buffer: list[str] = []
    bullet_buffer: list[tuple[str, str, str | None, int | None]] = []
    quote_buffer: list[str] = []
    code_buffer: list[str] = []
    code_language: str = ""
    in_code_block = False

    def flush_all() -> None:
        flush_paragraph(paragraph_buffer, story, styles)
        flush_bullets(bullet_buffer, story, styles)
        flush_quotes(quote_buffer, story, styles)

    raw_lines = markdown.splitlines()
    i = 0
    while i < len(raw_lines):
        raw_line = raw_lines[i]

        # Fenced code blocks: ``` opens, ``` closes. Optional language tag on
        # the opening fence (```rust, ```gdscript, ```json, ...) enables
        # Pygments syntax highlighting. Content lines are emitted verbatim (no
        # stripping, no inline markup) so that indentation is preserved and
        # backticks/asterisks in code do not become formatting.
        if raw_line.lstrip().startswith("```"):
            if in_code_block:
                story.append(
                    code_block(
                        code_buffer,
                        code_language,
                        styles["code"],
                        black_text=black_text,
                    )
                )
                code_buffer = []
                code_language = ""
                in_code_block = False
            else:
                flush_all()
                code_language = raw_line.lstrip()[3:].strip()
                in_code_block = True
            i += 1
            continue
        if in_code_block:
            code_buffer.append(raw_line.rstrip())
            i += 1
            continue

        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_all()
            i += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph(paragraph_buffer, story, styles)
            flush_bullets(bullet_buffer, story, styles)
            quote_buffer.append(stripped.lstrip("> ").strip())
            i += 1
            continue

        flush_quotes(quote_buffer, story, styles)

        # GFM tables: a row of pipe-separated cells followed by a separator
        # row of `|---|---|`. The separator is the load-bearing signal — a
        # bare line that happens to start with `|` is treated as a paragraph
        # unless the next line confirms it's a table.
        if (
            stripped.startswith("|")
            and i + 1 < len(raw_lines)
            and _is_table_separator(raw_lines[i + 1])
        ):
            flush_paragraph(paragraph_buffer, story, styles)
            flush_bullets(bullet_buffer, story, styles)
            alignments = _parse_table_alignments(raw_lines[i + 1])
            header = _parse_table_row(stripped)
            body_rows: list[list[str]] = []
            j = i + 2
            while j < len(raw_lines):
                row_line = raw_lines[j].strip()
                if not row_line.startswith("|"):
                    break
                body_rows.append(_parse_table_row(row_line))
                j += 1
            story.append(render_table(header, body_rows, alignments, styles, borders=table_borders, compact=compact_tables, agenda_tables=agenda_tables))
            i = j
            continue

        # GFM task-list syntax: `- [ ] foo`, `- [x] foo`, `1. [ ] foo`, `1. [X] foo`.
        # The optional `\[([ xX])\]\s+` group captures the marker after the
        # bullet/number; nothing else inside `[...]` matches (so `- [link](url)`
        # passes through as plain text without being misread as a checkbox).
        unordered = re.match(r"^[-*+]\s+(?:\[([ xX])\]\s+)?(.+)$", stripped)
        ordered = re.match(r"^(\d+)[.)]\s+(?:\[([ xX])\]\s+)?(.+)$", stripped)
        if unordered or ordered:
            flush_paragraph(paragraph_buffer, story, styles)
            kind = "ordered" if ordered else "unordered"
            if ordered:
                explicit_number: int | None = int(ordered.group(1))
                marker = ordered.group(2)
                text = ordered.group(3).strip()
            else:
                explicit_number = None
                marker = unordered.group(1)
                text = unordered.group(2).strip()
            if marker is None:
                state: str | None = None
            elif marker.lower() == "x":
                state = "checked"
            else:
                state = "unchecked"
            bullet_buffer.append((kind, text, state, explicit_number))
            i += 1
            continue

        # Scheduled-anchor line in an agenda's Suggested order: a clock-time
        # prefix followed by " | " and a name, e.g. "7:15 AM | Zoom" or
        # "~12:00 PM | Walk Luna (15m)". Rendered with tight spacing and an
        # indent that aligns the time column with the surrounding numbered
        # items, so it reads as "list item, just without the checkbox/number".
        if SCHEDULED_LINE_RE.match(stripped):
            flush_paragraph(paragraph_buffer, story, styles)
            flush_bullets(bullet_buffer, story, styles)
            story.append(paragraph(stripped, styles["scheduled"]))
            i += 1
            continue

        flush_bullets(bullet_buffer, story, styles)

        if stripped == "---":
            flush_paragraph(paragraph_buffer, story, styles)
            story.append(Spacer(1, 8))
        elif stripped.startswith("#### "):
            flush_paragraph(paragraph_buffer, story, styles)
            story.append(paragraph(stripped[5:].strip(), styles["h4"]))
        elif stripped.startswith("### "):
            flush_paragraph(paragraph_buffer, story, styles)
            story.append(paragraph(stripped[4:].strip(), styles["h3"]))
        elif stripped.startswith("## "):
            flush_paragraph(paragraph_buffer, story, styles)
            story.append(paragraph(stripped[3:].strip(), styles["h2"]))
        elif stripped.startswith("# "):
            flush_paragraph(paragraph_buffer, story, styles)
            story.append(paragraph(stripped[2:].strip(), styles["title"]))
        else:
            paragraph_buffer.append(stripped)

        i += 1

    flush_all()
    return story


def _prompt_overwrite(path: Path) -> bool:
    """Ask whether to overwrite `path`. Returns True for overwrite, False for version.

    Non-interactive runs (stdin not a TTY) default to False so piped/scripted
    invocations never silently destroy an existing PDF. EOF (Ctrl-D) and any
    answer other than y/yes also default to False.
    """
    if not sys.stdin.isatty():
        return False
    versioned = versioned_path(path)
    prompt = (
        f"{_color(str(path), _Color.YELLOW, _Color.BOLD)} already exists.\n"
        f"Overwrite? [{_color('y', _Color.GREEN, _Color.BOLD)}/"
        f"{_color('N', _Color.WHITE, _Color.BOLD)}] "
        f"{_color(f'(no = write to {versioned.name})', _Color.DIM)}: "
    )
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        print()
        return False
    return answer in ("y", "yes")


def convert_markdown_to_pdf(
    markdown_path: Path,
    output_path: Path | None = None,
    *,
    table_borders: bool = True,
    compact_tables: bool = False,
    font_shrink: float = 0.0,
    agenda_tables: bool = False,
    black_text: bool = False,
) -> Path:
    if markdown_path.suffix.lower() != ".md":
        raise ValueError(
            f"Input file must have a .md extension, got: {markdown_path.name}"
        )
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")
    # Relative file links in the markdown resolve against the .md's own folder,
    # so they become absolute file:// URIs that open on click.
    global _LINK_BASE_DIR
    _LINK_BASE_DIR = str(markdown_path.resolve().parent)
    if output_path is None:
        output_path = markdown_path.with_suffix(".pdf")
    if output_path.exists() and not _prompt_overwrite(output_path):
        output_path = versioned_path(output_path)

    markdown = normalize_text(markdown_path.read_text(encoding="utf-8"))
    story = parse_markdown(
        markdown,
        table_borders=table_borders,
        compact_tables=compact_tables,
        font_shrink=font_shrink,
        agenda_tables=agenda_tables,
        black_text=black_text,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=output_path.stem,
        author="markdown-to-pdf",
    )
    doc.build(story)
    return output_path


def main() -> None:
    # `prog` is pinned to the command name so `--help` and the missing-argument
    # usage error name the installed executable, not this file, however it was
    # invoked (installed launcher, run.sh, or `python3 main.py`).
    parser = argparse.ArgumentParser(
        prog="markdown-to-pdf",
        description="Convert a markdown file to a styled PDF.",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"markdown-to-pdf {__version__}",
        help="Print the tool version and exit.",
    )
    parser.add_argument("markdown", type=Path, help="Markdown file path, e.g. chapter.md")
    parser.add_argument("--out", type=Path, default=None, help="Optional PDF output path, e.g. chapter.pdf")
    parser.add_argument(
        "--no-table-borders",
        dest="table_borders",
        action="store_false",
        help="Render tables without cell borders or header fill (clean grid layout).",
    )
    parser.add_argument(
        "--compact-tables",
        dest="compact_tables",
        action="store_true",
        help="Tighten cell top/bottom padding for all tables in this document — useful for reference grids (e.g. the /todo agenda's habits snapshot).",
    )
    parser.add_argument(
        "--font-shrink",
        dest="font_shrink",
        type=float,
        default=0.0,
        help="Subtract N points from every text style's fontSize and leading. Use sparingly (e.g. 1.0) as a last-resort fit; defaults preserve the standard look.",
    )
    parser.add_argument(
        "--black-text",
        dest="black_text",
        action="store_true",
        help="Render all PDF text, including headings and links, as pure black (#000000).",
    )
    parser.add_argument(
        "--agenda",
        dest="agenda",
        action="store_true",
        help="Agenda mode. Bundles --no-table-borders + --compact-tables and zeroes LEFTPADDING on table cells — the styling the /todo agenda PDF requires. Use this for any agenda regeneration so the styling can't be forgotten by individual callers.",
    )
    args = parser.parse_args()
    # --agenda forces all four agenda-flavor table tweaks on regardless of
    # what the caller passed. Single, hard-to-forget switch for the agenda
    # flow; never fires for non-agenda documents.
    table_borders = args.table_borders and not args.agenda
    compact_tables = args.compact_tables or args.agenda
    agenda_tables = args.agenda
    try:
        output = convert_markdown_to_pdf(
            args.markdown,
            args.out,
            table_borders=table_borders,
            compact_tables=compact_tables,
            font_shrink=args.font_shrink,
            agenda_tables=agenda_tables,
            black_text=args.black_text,
        )
    except (ValueError, FileNotFoundError) as err:
        print(_color(f"error: {err}", _Color.RED, _Color.BOLD, stream=sys.stderr), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        print(_color("aborted", _Color.YELLOW, stream=sys.stderr), file=sys.stderr)
        sys.exit(130)
    print(_color("Wrote", _Color.GREEN) + " " + _color(str(output), _Color.GREEN, _Color.BOLD))


if __name__ == "__main__":
    main()
