#!/usr/bin/env python3
"""Tests for inline_markup() — emphasis handling (bold/italic, * and _).

Run:  python3 test_inline_markup.py
"""
import unittest

import main


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
