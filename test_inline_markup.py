#!/usr/bin/env python3
"""Tests for inline_markup() — emphasis handling (bold/italic, * and _).

Run:  python3 test_inline_markup.py
"""
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


class Styles(unittest.TestCase):
    def test_black_text_mode_makes_every_style_black(self):
        styles = main.make_styles(black_text=True)
        for style in styles.values():
            self.assertEqual(style.textColor, main.BLACK)


if __name__ == "__main__":
    unittest.main(verbosity=2)
