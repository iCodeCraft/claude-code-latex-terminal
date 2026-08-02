import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "lib"))

from math_spans import DisplayState, transform_delta


class MathSpanTests(unittest.TestCase):
    def test_protects_inline_punctuation_commands(self):
        result = transform_delta(r"Inline $a\,b\;c\!d\frac{1}{2}$.")

        self.assertEqual(result.content, r"Inline $a\\,b\\;c\\!d\frac{1}{2}$.")
        self.assertTrue(result.changed)

    def test_leaves_display_math_unchanged_across_batches(self):
        first = transform_delta(
            "$$\n\\begin{aligned}\na\\,x &= b " + "\\" * 2 + "\n"
        )
        second = transform_delta(
            "c\\;x &= d\n\\end{aligned}\n$$\n", first.state, final=True
        )

        self.assertEqual(
            first.content,
            "$$\n\\begin{aligned}\na\\,x &= b " + "\\" * 2 + "\n",
        )
        self.assertEqual(second.content, "c\\;x &= d\n\\end{aligned}\n$$\n")
        self.assertFalse(first.changed)
        self.assertFalse(second.changed)
        self.assertIsNone(second.state.math_delimiter)

    def test_ignores_code_and_currency(self):
        text = "Cost is $5.\n```tex\n$a\\,b$\n```\n`$x\\;y$`\nReal $z\\,w$."
        result = transform_delta(text)

        self.assertEqual(
            result.content,
            "Cost is $5.\n```tex\n$a\\,b$\n```\n`$x\\;y$`\nReal $z\\\\,w$.",
        )

    def test_resumes_inline_detection_after_display_math(self):
        first = transform_delta("$$\na\\,x\n")
        second = transform_delta("$$\nInline $a\\,b$", first.state, final=True)

        self.assertEqual(first.content, "$$\na\\,x\n")
        self.assertEqual(second.content, "$$\nInline $a\\\\,b$")

    def test_protects_display_math_when_inline_requires_replacement(self):
        text = (
            "Inline: $a\\,b$ and $x\\;y$.\n\n$$\n\\begin{aligned}\n"
            "a\\,x &= b "
            + "\\" * 2
            + "\nc\\;x &= d\n\\end{aligned}\n$$\n"
        )

        result = transform_delta(text, final=True)

        self.assertEqual(
            result.content,
            (
                "Inline: $a\\\\,b$ and $x\\\\;y$.\n\n$$\n\\begin{aligned}\n"
                "a\\\\,x &= b "
                + "\\" * 4
                + "\nc\\\\;x &= d\n\\end{aligned}\n$$\n"
            ),
        )
        self.assertTrue(result.changed)

    def test_keeps_protecting_a_display_block_in_later_batches(self):
        first = transform_delta("Inline $a\\,b$\n$$\na\\,x\n")
        second = transform_delta("c\\;x\n$$\n", first.state, final=True)

        self.assertEqual(first.content, "Inline $a\\\\,b$\n$$\na\\\\,x\n")
        self.assertTrue(first.state.protect_display_math)
        self.assertTrue(first.state.message_has_replacement)
        self.assertEqual(second.content, "c\\\\;x\n$$\n")
        self.assertTrue(second.changed)
        self.assertFalse(second.state.protect_display_math)

    def test_protects_a_display_block_started_after_an_inline_batch(self):
        first = transform_delta("Inline $a\\,b$\n\nDisplay:\n")
        second = transform_delta(
            "$$\n\\begin{aligned}\na\\,x &= b " + "\\" * 2
            + "\nc\\;x &= d\n\\end{aligned}\n$$\n",
            first.state,
            final=True,
        )

        self.assertEqual(first.content, "Inline $a\\\\,b$\n\nDisplay:\n")
        self.assertTrue(first.state.message_has_replacement)
        self.assertEqual(
            second.content,
            "$$\n\\begin{aligned}\na\\\\,x &= b " + "\\" * 4
            + "\nc\\\\;x &= d\n\\end{aligned}\n$$\n",
        )
        self.assertTrue(second.changed)

    def test_preserves_indented_code_fences_when_math_changes(self):
        text = "  ```tex\n$a\\,b$\n  ```\nReal $x\\;y$."

        result = transform_delta(text, final=True)

        self.assertEqual(
            result.content,
            "  ```tex\n$a\\,b$\n  ```\nReal $x\\\\;y$.",
        )
        self.assertTrue(result.changed)

    def test_preserves_a_backslash_split_across_batches(self):
        state = DisplayState(math_delimiter="inline")
        first = transform_delta("a\\", state)
        second = transform_delta(",b$\n", first.state, final=True)

        self.assertEqual(first.content, "a")
        self.assertTrue(first.changed)
        self.assertEqual(second.content, "\\\\,b$\n")
        self.assertTrue(second.changed)


if __name__ == "__main__":
    unittest.main()
