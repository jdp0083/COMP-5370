# tests_deserializer.py
# Library-style tests (no main/CLI).  :contentReference[oaicite:1]{index=1}
import unittest
import textwrap
from deserializer import Deserializer, NosjError



def lines(s: str):
    return textwrap.dedent(s).splitlines()


class TestScalars(unittest.TestCase):
    def test_decode_num_values(self):
        cases = [
            ("0", 0), ("1", -1), ("10", -2), ("11", -1),
            ("0110", 6), ("1010", -6), ("11110110", -10),
        ]
        for b, exp in cases:
            with self.subTest(b=b):
                self.assertEqual(Deserializer.decode_num(b), exp)

    def test_decode_num_invalid(self):
        for bad in ["", "2", "10a01", None]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    Deserializer.decode_num(bad)  # type: ignore[arg-type]
    def test_decode_simple_str_values(self):
        cases = [
            ("abcds", "abcd"),
            ("ef ghs", "ef gh"),
            ("\tabs\ts", "\tabs\t"),
            ("A0 s", "A0 "),
            ("Zs", "Z"),
            ("nos", "no"),     # was incorrectly marked invalid; it's valid
            (" s", " "),       # was incorrectly marked invalid; it's valid
        ]
        for s, exp in cases:
            with self.subTest(s=s):
                self.assertEqual(Deserializer.decode_simple_str(s), exp)

    def test_decode_simple_str_invalid(self):
        # Keep only truly invalid samples:
        # - empty
        # - contains disallowed punctuation
        # - missing trailing 's'
        # - None
        for bad in ["", "bad!", "endsmissing", None]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    Deserializer.decode_simple_str(bad)  # type: ignore[arg-type]

    # def test_decode_simple_str_values(self):
    #     cases = [
    #         ("abcds", "abcd"),
    #         ("ef ghs", "ef gh"),
    #         ("\tabs\ts", "\tabs\t"),
    #         ("A0 s", "A0 "),
    #         ("Zs", "Z"),
    #     ]
    #     for s, exp in cases:
    #         with self.subTest(s=s):
    #             self.assertEqual(Deserializer.decode_simple_str(s), exp)

    # def test_decode_simple_str_invalid(self):
    #     for bad in ["", "nos", "bad!", "endsmissing", " s", None]:
    #         with self.subTest(bad=bad):
    #             with self.assertRaises(ValueError):
    #                 Deserializer.decode_simple_str(bad)  # type: ignore[arg-type]


class TestParser(unittest.TestCase):
    def collect(self, src: str):
        return list(Deserializer.parse_lines(lines(src)))

    def test_parse_simple_scalars(self):
        src = """
            # simple scalars
            name: Johns
            age: 1010
        """
        out = self.collect(src)
        self.assertEqual(out, [
            "name -- string -- John",
            "age -- num -- -6",
        ])

    def test_parse_nested_map(self):
        src = """
            person: {
              name: Johns
              stats: {
                age: 0110
              }
            }
        """
        out = self.collect(src)
        self.assertEqual(out, [
            "person -- map -- ",
            "begin-map",
            "name -- string -- John",
            "stats -- map -- ",
            "begin-map",
            "age -- num -- 6",
            "end-map",
            "end-map",
        ])

    def test_error_bad_key(self):
        src = "bad key: 0110\n"
        with self.assertRaises(NosjError):
            self.collect(src)

    def test_error_unclosed_map(self):
        src = """
            a: {
              b: 01
        """
        with self.assertRaises(NosjError):
            self.collect(src)

    def test_error_mismatched_closing(self):
        src = "}\n"
        with self.assertRaises(NosjError):
            self.collect(src)

    def test_error_unrecognized_scalar(self):
        src = "thing: 3\n"  # not binary; not simple-string
        with self.assertRaises(NosjError):
            self.collect(src)
