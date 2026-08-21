#!/usr/bin/env python3
"""Tests for inline_markup() — emphasis handling (bold/italic, * and _).

Run:  python3 test_inline_markup.py
"""
import contextlib
import io
import re
import subprocess
import sys
import unittest

import main


class Version(unittest.TestCase):
    def test_version_is_semver(self):
        # __version__ is the single source of truth for the tool's version.
        self.assertTrue(hasattr(main, "__version__"))
        self.assertRegex(main.__version__, r"^\d+\.\d+\.\d+$")

    def test_cli_version_flag(self):
        # --version prints "markdown-to-pdf <version>" and exits 0.
        out = subprocess.run(
            [sys.executable, main.__file__, "--version"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(out.returncode, 0)
        self.assertIn(main.__version__, out.stdout)
        self.assertIn("markdown-to-pdf", out.stdout)

    def test_cli_version_short_alias(self):
        # -v is an alias for --version.
        out = subprocess.run(
            [sys.executable, main.__file__, "-v"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(out.returncode, 0)
        self.assertIn(main.__version__, out.stdout)


class UnderscoreEmphasis(unittest.TestCase):
    def test_underscore_italic(self):
        self.assertEqual(main.inline_markup("_italic_"), "<i>italic</i>")

    def test_underscore_bold(self):
        self.assertEqual(main.inline_markup("__bold__"), "<b>bold</b>")

    def test_underscore_italic_midsentence(self):
        self.assertEqual(
            main.inline_markup("a _mix_ here"), "a <i>mix</i> here"
        )

    def test_underscore_emphasis_with_punctuation_boundary(self):
        # parens are non-word chars, so emphasis still fires
        self.assertEqual(main.inline_markup("(_note_)"), "(<i>note</i>)")

    def test_bold_before_italic(self):
        self.assertEqual(
            main.inline_markup("__b__ and _i_"), "<b>b</b> and <i>i</i>"
        )


class UnderscoreLeftLiteral(unittest.TestCase):
    """Intraword underscores must NOT become emphasis."""

    def test_snake_case(self):
        self.assertEqual(main.inline_markup("snake_case"), "snake_case")

    def test_snake_case_multi(self):
        self.assertEqual(
            main.inline_markup("snake_case_word"), "snake_case_word"
        )

    def test_filename(self):
        self.assertEqual(main.inline_markup("file_name.py"), "file_name.py")

    def test_leading_space_not_emphasis(self):
        # CommonMark: "_ x _" (space after opener) is not emphasis
        self.assertEqual(main.inline_markup("_ x _"), "_ x _")


class AsteriskStillWorks(unittest.TestCase):
    def test_asterisk_italic(self):
        self.assertEqual(main.inline_markup("*italic*"), "<i>italic</i>")

    def test_asterisk_bold(self):
        self.assertEqual(main.inline_markup("**bold**"), "<b>bold</b>")

    def test_mixed_underscore_and_asterisk(self):
        self.assertEqual(
            main.inline_markup("a _u_ and *s*"), "a <i>u</i> and <i>s</i>"
        )


class CodeSpansProtectUnderscores(unittest.TestCase):
    def test_underscores_in_code_are_literal(self):
        out = main.inline_markup("`a_b_c`")
        # underscores inside code must NOT be italicized
        self.assertNotIn("<i>", out)
        self.assertIn("a_b_c", out)

    def test_code_span_next_to_emphasis(self):
        out = main.inline_markup("`snake_case` and _yes_")
        self.assertIn("snake_case", out)
        self.assertIn("<i>yes</i>", out)
        # the code-span underscores stayed literal
        self.assertNotIn("<i>snake", out)


class Links(unittest.TestCase):
    def test_external_link_becomes_anchor(self):
        out = main.inline_markup("[Devex](https://www.devex.com)")
        self.assertIn('href="https://www.devex.com"', out)
        self.assertIn("<a ", out)
        self.assertIn('underline="0">Devex</a>', out)

    def test_mailto_kept(self):
        out = main.inline_markup("[mail me](mailto:a@b.com)")
        self.assertIn('href="mailto:a@b.com"', out)

    def test_anchor_kept(self):
        out = main.inline_markup("[jump](#section)")
        self.assertIn('href="#section"', out)

    def test_local_file_resolved_to_absolute_file_uri(self):
        import pathlib

        base = "/tmp/songs"
        expected = (pathlib.Path(base) / "song-list.md").resolve().as_uri()
        out = main.inline_markup("[notes](song-list.md)", base_dir=base)
        self.assertIn(f'href="{expected}"', out)
        self.assertTrue(expected.startswith("file://"))

    def test_resolve_href_percent_encodes_spaces(self):
        # _resolve_href is the pure helper; a nonexistent base won't hit symlinks
        got = main._resolve_href("my file.pdf", "/nonexistent-base-xyz")
        self.assertEqual(got, "file:///nonexistent-base-xyz/my%20file.pdf")

    def test_resolve_href_passes_external_through(self):
        self.assertEqual(
            main._resolve_href("https://x.com/a?b=1&c=2", "/base"),
            "https://x.com/a?b=1&c=2",
        )

    def test_no_basedir_leaves_relative_href(self):
        # global base dir is None in unit tests → relative path preserved
        main._LINK_BASE_DIR = None
        out = main.inline_markup("[notes](song-list.md)")
        self.assertIn('href="song-list.md"', out)

    def test_plain_brackets_are_not_a_link(self):
        self.assertEqual(main.inline_markup("[just brackets]"), "[just brackets]")

    def test_link_text_emphasis_still_processed(self):
        out = main.inline_markup("[**bold**](https://x.com)")
        self.assertIn("<b>bold</b>", out)

    def test_underscore_in_href_not_italicized(self):
        out = main.inline_markup("[a](song_list.md)", base_dir="/d")
        self.assertNotIn("<i>", out)
        self.assertIn("song_list.md", out)

    def test_black_text_mode_makes_links_black(self):
        main._BLACK_TEXT = True
        try:
            out = main.inline_markup("[article](https://example.com/article)")
        finally:
            main._BLACK_TEXT = False
        self.assertIn('color="0x000000"', out)

    def test_links_are_clickable_without_underlines(self):
        out = main.inline_markup("[article](https://example.com/article)")
        self.assertIn('href="https://example.com/article"', out)
        self.assertIn('underline="0"', out)
        self.assertNotIn("<u>", out)


class TableRowParsing(unittest.TestCase):
    def test_plain_row_splits_on_pipes(self):
        self.assertEqual(
            main._parse_table_row("| 1 | Article | Publication |"),
            ["1", "Article", "Publication"],
        )

    def test_escaped_pipe_stays_inside_its_cell(self):
        # A title like "Opinion | Three minutes on Sudan" is escaped `\|` in
        # GFM. It must NOT split the cell into two (which would shift every
        # later cell right and invent a phantom column).
        self.assertEqual(
            main._parse_table_row(r"| 4 | Opinion \| Three minutes on Sudan | TNH |"),
            ["4", "Opinion | Three minutes on Sudan", "TNH"],
        )

    def test_escaped_pipe_inside_a_link_label(self):
        row = main._parse_table_row(
            r"| 4 | [Opinion \| Three minutes](https://x.org/a) | TNH |"
        )
        self.assertEqual(
            row, ["4", "[Opinion | Three minutes](https://x.org/a)", "TNH"]
        )

    def test_escaped_backslash_before_a_real_separator(self):
        # `\\` is a literal backslash; the pipe after it still separates.
        self.assertEqual(main._parse_table_row(r"| a\\ | b |"), ["a\\", "b"])

    def test_separator_row_with_escaped_pipe_is_not_a_separator(self):
        self.assertFalse(main._is_table_separator(r"| --- \| --- |"))

    def test_alignments_unaffected_by_escaping(self):
        self.assertEqual(
            main._parse_table_alignments("| ---: | --- | :---: |"),
            ["RIGHT", "LEFT", "CENTER"],
        )


class ColumnWidths(unittest.TestCase):
    def test_narrow_column_stays_narrow(self):
        # A `#` column of single digits must not eat a third of the table.
        widths = main.fit_column_widths([10, 40, 30], [20, 300, 120], 500)
        self.assertLess(widths[0], 40)
        self.assertGreater(widths[1], widths[2])

    def test_widths_always_fill_the_available_space(self):
        for mins, maxs in (
            ([10, 40, 30], [20, 300, 120]),
            ([10, 40, 30], [20, 900, 400]),
            ([200, 300, 250], [400, 600, 500]),
            ([5], [9]),
        ):
            widths = main.fit_column_widths(mins, maxs, 500)
            self.assertAlmostEqual(sum(widths), 500, places=6)

    def test_content_that_fits_keeps_its_proportions(self):
        widths = main.fit_column_widths([10, 40], [100, 300], 400)
        self.assertAlmostEqual(widths[0], 100, places=6)
        self.assertAlmostEqual(widths[1], 300, places=6)

    def test_overflow_shrinks_toward_the_minimum_width(self):
        widths = main.fit_column_widths([20, 100], [40, 800], 300)
        # Every column keeps at least its longest-word width when there is room.
        self.assertGreaterEqual(widths[0], 20)
        self.assertGreaterEqual(widths[1], 100)
        # The greedy column absorbs almost all of the shortfall.
        self.assertLess(widths[0], 40)
        self.assertGreater(widths[1], 200)

    def test_impossible_minimums_split_proportionally(self):
        widths = main.fit_column_widths([100, 300], [150, 400], 200)
        self.assertAlmostEqual(sum(widths), 200, places=6)
        self.assertGreater(widths[1], widths[0])

    def test_no_columns_yields_no_widths(self):
        self.assertEqual(main.fit_column_widths([], [], 500), [])

    def test_zero_content_falls_back_to_equal_columns(self):
        self.assertEqual(main.fit_column_widths([0, 0], [0, 0], 400), [200, 200])

    def test_narrow_column_never_shrinks_below_the_floor(self):
        # A `#` column beside four columns whose longest unbreakable token is a
        # long file path. The minimums cannot all fit, so widths are shared out
        # in proportion; without a floor the `#` column gets ~7pt, which is less
        # than the 16pt of cell padding, and ReportLab is handed a negative
        # available width and raises.
        mins = [22.0] + [416.0] * 4
        maxs = [24.0] + [4016.0] * 4
        widths = main.fit_column_widths(mins, maxs, 522.0, floor=22.0)
        for width in widths:
            self.assertGreaterEqual(width, 22.0)

    def test_flooring_still_fills_the_available_space(self):
        widths = main.fit_column_widths(
            [22.0] + [416.0] * 4, [24.0] + [4016.0] * 4, 522.0, floor=22.0
        )
        self.assertAlmostEqual(sum(widths), 522.0, places=6)

    def test_floor_is_opt_in_and_defaults_to_off(self):
        # Without a floor the three original branches are untouched.
        self.assertEqual(main.fit_column_widths([0, 0], [0, 0], 400), [200, 200])
        widths = main.fit_column_widths([10, 40], [100, 300], 400)
        self.assertAlmostEqual(widths[0], 100, places=6)

    def test_floor_wider_than_the_page_still_returns_usable_widths(self):
        # More columns than the text block can seat. There is no width that both
        # fits the page and clears the padding, so every column gets the floor
        # and the table overflows visibly rather than crashing.
        widths = main.fit_column_widths([50.0] * 40, [80.0] * 40, 522.0, floor=22.0)
        self.assertEqual(len(widths), 40)
        for width in widths:
            self.assertGreaterEqual(width, 22.0)


class TableRendering(unittest.TestCase):
    def _widths(self, header, rows, alignments):
        styles = main.make_styles()
        table = main.render_table(header, rows, alignments, styles)
        return table._argW

    def test_index_column_is_sized_to_its_digits(self):
        header = ["#", "Article", "Publication"]
        rows = [
            ["1", "Exclusive: WFP to extend Palantir contract despite concerns", "FRANCE 24"],
            ["2", "Deep dive: the organizations still hiring in global development", "Devex Newswire"],
        ]
        widths = self._widths(header, rows, ["RIGHT", "LEFT", "LEFT"])
        available = main.PAGE_WIDTH - main.LEFT_MARGIN - main.RIGHT_MARGIN
        self.assertAlmostEqual(sum(widths), available, places=4)
        # The `#` column holds one digit; it should be by far the narrowest.
        self.assertLess(widths[0], available / 8)
        self.assertGreater(widths[1], widths[2])

    def test_ragged_rows_are_padded_not_widened(self):
        widths = self._widths(["A", "B"], [["only one cell"]], ["LEFT", "LEFT"])
        self.assertEqual(len(widths), 2)

    def test_long_unbreakable_tokens_never_starve_a_narrow_column(self):
        # The regression: a one-character `#` column beside four columns whose
        # longest words are long file paths. Every column must leave room for
        # its own 16pt of padding, or ReportLab raises "negative availWidth".
        header = ["#", "Assumption", "Falsifier", "If falsified", "Owner"]
        path = "shared/models/queries/StructuredQuery/sqlToStructuredQuery.ts:118"
        rows = [
            [
                str(n),
                f"An assumption naming {path} and {path}",
                f"Falsified when {path} reports dialectArtefactSuspected",
                f"Cancel the phase described in {path}",
                f"{path}",
            ]
            for n in range(1, 9)
        ]
        widths = self._widths(header, rows, ["LEFT"] * 5)
        available = main.PAGE_WIDTH - main.LEFT_MARGIN - main.RIGHT_MARGIN
        self.assertAlmostEqual(sum(widths), available, places=4)
        for width in widths:
            self.assertGreater(width, 16.0)

    def test_a_table_of_long_paths_actually_renders(self):
        # End to end through ReportLab: the table that used to raise must wrap.
        header = ["#", "Assumption", "Falsifier", "If falsified", "Owner"]
        path = "shared/models/queries/StructuredQuery/sqlToStructuredQuery.ts:118"
        rows = [[str(n), path, path, path, path] for n in range(1, 9)]
        styles = main.make_styles()
        table = main.render_table(header, rows, ["LEFT"] * 5, styles)
        available = main.PAGE_WIDTH - main.LEFT_MARGIN - main.RIGHT_MARGIN
        table.wrap(available, main.PAGE_HEIGHT)


class Styles(unittest.TestCase):
    def test_black_text_mode_makes_every_style_black(self):
        styles = main.make_styles(black_text=True)
        for style in styles.values():
            self.assertEqual(style.textColor, main.BLACK)


class BulletGlyphIsExtractable(unittest.TestCase):
    """A list bullet must survive copy/paste and text extraction.

    ReportLab's WinAnsi table follows Adobe in mapping every unused code above
    40 to `bullet`, and picks the lowest such code (127) when encoding U+2022.
    Extractors implement the strict table instead, where 127 is undefined, so
    the bullet comes back as `(cid:127)` or vanishes. Encoding it at 149 — the
    one code the strict table also calls `bullet` — makes every reader agree.
    """

    def _font(self):
        from reportlab.pdfbase import pdfmetrics

        return pdfmetrics.getFont(main.BULLET_FONT)

    def test_bullet_encodes_to_the_unambiguous_winansi_code(self):
        self.assertEqual("•".encode(self._font().encName), b"\x95")

    def test_the_ambiguous_bullet_aliases_are_left_undefined(self):
        vector = self._font().encoding.vector
        self.assertEqual(vector[149], "bullet")
        for code in (127, 129, 141, 143, 144, 157):
            self.assertIsNone(vector[code])

    def test_ordinary_characters_still_encode_as_winansi(self):
        encoding = self._font().encName
        self.assertEqual("Grill the plan".encode(encoding), b"Grill the plan")
        self.assertEqual("café — naïve".encode(encoding), "café — naïve".encode("WinAnsiEncoding"))

    def test_unordered_lists_render_with_the_bullet_safe_font(self):
        story = []
        buffer = [("unordered", "alpha", None, None), ("unordered", "beta", None, None)]
        main.flush_bullets(buffer, story, main.make_styles())
        self.assertEqual(story[0]._bulletFontName, main.BULLET_FONT)

    def test_ordered_lists_are_unaffected(self):
        story = []
        buffer = [("ordered", "alpha", None, None)]
        main.flush_bullets(buffer, story, main.make_styles())
        self.assertEqual(story[0]._bulletType, "1")


def _item_texts(list_flowable):
    """The rendered text of each ListItem in a ReportLab ListFlowable."""
    texts = []
    for item in list_flowable._content:
        content = item._content[0] if hasattr(item, "_content") else item
        texts.append(content.text)
    return texts


class SoftLineBreaksInLists(unittest.TestCase):
    """A wrapped list item is one item, not an item plus a paragraph.

    In Markdown a single newline inside a list item is a soft break: it exists
    so the source can be wrapped at a sane column, and it folds into a space.
    Splitting on it turns every wrapped bullet into its own one-item list with
    an orphaned paragraph after it.
    """

    def test_wrapped_bullet_stays_one_item(self):
        story = main.parse_markdown(
            "- **Choice one.** Rejected:\n"
            "  the alternative, because reasons.\n"
            "- **Choice two.** Kept.\n"
        )
        lists = [f for f in story if type(f).__name__ == "ListFlowable"]
        self.assertEqual(len(lists), 1)
        self.assertEqual(
            _item_texts(lists[0]),
            [
                "<b>Choice one.</b> Rejected: the alternative, because reasons.",
                "<b>Choice two.</b> Kept.",
            ],
        )

    def test_wrapped_bullet_emits_no_stray_paragraph(self):
        story = main.parse_markdown("- one\n  continued\n")
        self.assertEqual([type(f).__name__ for f in story], ["ListFlowable"])

    def test_wrapped_ordered_item_stays_one_item(self):
        story = main.parse_markdown(
            "1. First item that wraps\n"
            "   onto a second line.\n"
            "2. Second item.\n"
        )
        lists = [f for f in story if type(f).__name__ == "ListFlowable"]
        self.assertEqual(len(lists), 1)
        self.assertEqual(
            _item_texts(lists[0]),
            ["First item that wraps onto a second line.", "Second item."],
        )

    def test_unindented_continuation_also_joins(self):
        # CommonMark lazy continuation: the continuation need not be indented.
        story = main.parse_markdown("- one\ncontinued\n")
        lists = [f for f in story if type(f).__name__ == "ListFlowable"]
        self.assertEqual(_item_texts(lists[0]), ["one continued"])

    def test_three_continuation_lines_all_join(self):
        story = main.parse_markdown("- a\n  b\n  c\n  d\n")
        lists = [f for f in story if type(f).__name__ == "ListFlowable"]
        self.assertEqual(_item_texts(lists[0]), ["a b c d"])

    def test_blank_line_ends_the_list(self):
        story = main.parse_markdown("- one\n\nA new paragraph.\n")
        self.assertEqual(
            [type(f).__name__ for f in story], ["ListFlowable", "Paragraph"]
        )

    def test_a_heading_ends_the_list(self):
        story = main.parse_markdown("- one\n## Heading\n")
        self.assertEqual(
            [type(f).__name__ for f in story], ["ListFlowable", "Paragraph"]
        )
        self.assertEqual(story[1].text, "Heading")

    def test_a_fence_ends_the_list(self):
        story = main.parse_markdown("- one\n```\ncode\n```\n")
        self.assertEqual([type(f).__name__ for f in story], ["ListFlowable", "Table"])

    def test_a_table_ends_the_list(self):
        story = main.parse_markdown("- one\n| a | b |\n| --- | --- |\n| 1 | 2 |\n")
        self.assertEqual([type(f).__name__ for f in story], ["ListFlowable", "Table"])

    def test_a_blockquote_ends_the_list(self):
        story = main.parse_markdown("- one\n> quoted\n")
        self.assertEqual([type(f).__name__ for f in story], ["ListFlowable", "Table"])


class HardLineBreaks(unittest.TestCase):
    """Two trailing spaces, or a trailing backslash, is the only real break."""

    def test_two_trailing_spaces_break_the_line(self):
        story = main.parse_markdown("alpha  \nbeta\n")
        self.assertEqual(story[0].text, "alpha<br/>beta")

    def test_more_than_two_trailing_spaces_still_break(self):
        story = main.parse_markdown("alpha    \nbeta\n")
        self.assertEqual(story[0].text, "alpha<br/>beta")

    def test_trailing_backslash_breaks_the_line(self):
        story = main.parse_markdown("alpha\\\nbeta\n")
        self.assertEqual(story[0].text, "alpha<br/>beta")

    def test_single_newline_is_a_space(self):
        story = main.parse_markdown("alpha\nbeta\n")
        self.assertEqual(story[0].text, "alpha beta")

    def test_one_trailing_space_is_not_a_break(self):
        story = main.parse_markdown("alpha \nbeta\n")
        self.assertEqual(story[0].text, "alpha beta")

    def test_last_line_of_a_paragraph_never_breaks(self):
        story = main.parse_markdown("alpha  \n")
        self.assertEqual(story[0].text, "alpha")

    def test_hard_break_inside_a_bullet(self):
        story = main.parse_markdown("- alpha  \n  beta\n")
        lists = [f for f in story if type(f).__name__ == "ListFlowable"]
        self.assertEqual(_item_texts(lists[0]), ["alpha<br/>beta"])


def _code_cell(source, language, *, black_text=False):
    """The single flowable inside the table a fenced code block renders to."""
    table = main.code_block(
        source, language, main.make_styles()["code"], black_text=black_text
    )
    return table._cellvalues[0][0]


class SyntaxHighlighting(unittest.TestCase):
    """A tagged fence is colored per token; an untagged one stays plain.

    Highlighting degrades silently when Pygments is missing, so the dependency
    itself is asserted: without it every fence renders plain and no test that
    only checked the fallback would notice.
    """

    def test_pygments_is_installed(self):
        self.assertTrue(
            main._PYGMENTS_AVAILABLE,
            "pygments must be installed for highlighting; see requirements.txt",
        )

    def test_typescript_is_highlighted(self):
        cell = _code_cell(["const x: number = 1;"], "typescript")
        self.assertEqual(type(cell).__name__, "XPreformatted")
        self.assertIn("<font color=", cell.text)

    def test_python_is_highlighted(self):
        cell = _code_cell(["def f(x):", "    return x + 1"], "python")
        self.assertEqual(type(cell).__name__, "XPreformatted")
        self.assertIn("<font color=", cell.text)

    def _visible(self, markup):
        """The text a reader sees, with markup stripped and entities restored."""
        text = re.sub(r"<[^>]+>", "", markup)
        for entity, char in (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
            text = text.replace(entity, char)
        return text

    def test_highlighting_loses_no_source(self):
        # The guard for the whole bug class: reportlab's own pygments2xpre
        # collapses every span between the first and last on a line, so
        # `const x: number = 1;` came back as `const ;`. Exact equality is the
        # only assertion that catches a silently dropped token.
        source = "const x: number = 1;"
        self.assertEqual(self._visible(main.highlight_to_xpre(source, "typescript")), source)

    def test_highlighting_loses_no_source_across_lines(self):
        source = "function f(a: string): void {\n  return;\n}"
        self.assertEqual(self._visible(main.highlight_to_xpre(source, "typescript")), source)

    def test_highlighting_adds_no_trailing_blank_line(self):
        self.assertFalse(main.highlight_to_xpre("const x = 1;", "typescript").endswith("\n"))

    def test_highlighting_escapes_markup_characters(self):
        # `<` and `&` must reach the PDF as text, not as reportlab markup.
        markup = main.highlight_to_xpre("if (a < b && c > d) {}", "typescript")
        self.assertIn("&lt;", markup)
        self.assertIn("&amp;", markup)
        self.assertEqual(self._visible(markup), "if (a < b && c > d) {}")

    def test_an_untagged_fence_is_plain(self):
        cell = _code_cell(["just text"], "")
        self.assertEqual(type(cell).__name__, "Preformatted")

    def test_an_unknown_language_falls_back_to_plain(self):
        cell = _code_cell(["whatever"], "not-a-real-language")
        self.assertEqual(type(cell).__name__, "Preformatted")

    def test_black_text_mode_is_plain(self):
        # Printable-black mode wants no color anywhere, including code.
        cell = _code_cell(["const x = 1;"], "typescript", black_text=True)
        self.assertEqual(type(cell).__name__, "Preformatted")

    def test_a_tagged_fence_survives_the_full_parse(self):
        story = main.parse_markdown("```typescript\nconst x: number = 1;\n```\n")
        self.assertEqual(len(story), 1)
        cell = story[0]._cellvalues[0][0]
        self.assertEqual(type(cell).__name__, "XPreformatted")


class MermaidDiagrams(unittest.TestCase):
    """A ```mermaid fence renders as a diagram, or degrades to its source.

    Rendering shells out to mermaid-cli, so one render is shared across the
    tests that only inspect the resulting flowable.
    """

    DIAGRAM = "flowchart TD\n    A[start] --> B[done]\n"

    @classmethod
    def setUpClass(cls):
        cls.story = main.parse_markdown(f"```mermaid\n{cls.DIAGRAM}```\n")

    def test_a_renderer_is_available(self):
        self.assertIsNotNone(
            main.find_mermaid_renderer(),
            "mermaid-cli must be installed; run ./install.sh",
        )

    def test_a_mermaid_fence_becomes_an_image(self):
        self.assertEqual([type(f).__name__ for f in self.story], ["Image"])

    def test_the_diagram_fits_the_content_width(self):
        content_width = main.PAGE_WIDTH - main.LEFT_MARGIN - main.RIGHT_MARGIN
        self.assertLessEqual(self.story[0].drawWidth, content_width)

    def test_the_diagram_fits_the_page_height(self):
        page_height = main.PAGE_HEIGHT - main.TOP_MARGIN - main.BOTTOM_MARGIN
        self.assertLessEqual(self.story[0].drawHeight, page_height)

    def test_the_diagram_keeps_its_aspect_ratio(self):
        reader = main.render_mermaid(self.DIAGRAM)
        self.assertIsNotNone(reader)
        native_width, native_height = reader.getSize()
        drawn = self.story[0]
        self.assertAlmostEqual(
            drawn.drawWidth / drawn.drawHeight,
            native_width / native_height,
            places=2,
        )

    def test_a_missing_renderer_falls_back_to_the_source(self):
        original = main.find_mermaid_renderer
        main.find_mermaid_renderer = lambda: None
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                story = main.parse_markdown(f"```mermaid\n{self.DIAGRAM}```\n")
        finally:
            main.find_mermaid_renderer = original
        self.assertEqual([type(f).__name__ for f in story], ["Table"])
        cell = story[0]._cellvalues[0][0]
        self.assertIn("flowchart TD", "\n".join(cell.lines))

    def test_a_missing_renderer_warns_on_stderr(self):
        original = main.find_mermaid_renderer
        main.find_mermaid_renderer = lambda: None
        captured = io.StringIO()
        try:
            with contextlib.redirect_stderr(captured):
                main.parse_markdown(f"```mermaid\n{self.DIAGRAM}```\n")
        finally:
            main.find_mermaid_renderer = original
        self.assertIn("mermaid", captured.getvalue().lower())

    def test_unrenderable_source_falls_back_to_the_source(self):
        with contextlib.redirect_stderr(io.StringIO()):
            story = main.parse_markdown("```mermaid\n%%not a diagram%%\n```\n")
        self.assertEqual([type(f).__name__ for f in story], ["Table"])

    def test_the_language_tag_is_matched_case_insensitively(self):
        story = main.parse_markdown(f"```Mermaid\n{self.DIAGRAM}```\n")
        self.assertEqual([type(f).__name__ for f in story], ["Image"])

    def test_a_non_mermaid_fence_is_still_a_code_block(self):
        story = main.parse_markdown("```typescript\nconst x = 1;\n```\n")
        self.assertEqual([type(f).__name__ for f in story], ["Table"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
