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


class Links(unittest.TestCase):
    def test_external_link_becomes_anchor(self):
        out = main.inline_markup("[Devex](https://www.devex.com)")
        self.assertIn('href="https://www.devex.com"', out)
        self.assertIn("<a ", out)
        self.assertIn(">Devex</u></a>", out)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
