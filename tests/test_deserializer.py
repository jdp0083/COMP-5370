# tests/test_deserializer.py
import io
import os
import sys
import tempfile
import importlib
import contextlib

import pytest

# Make sure we import from the project root
sys.path.insert(0, os.getcwd())
des = importlib.import_module("deserializer")

parse_marshalled_map = des.parse_marshalled_map
NosjError = des.NosjError
main = des.main


# Helpers
class _BytesStd:
    """stdout/stderr stub that provides .buffer (BytesIO) and a text .write()."""
    def __init__(self):
        self._buf = io.BytesIO()
    @property
    def buffer(self):
        return self._buf
    def write(self, s: str):
        # Only used if something writes text; mirror to bytes buffer
        if isinstance(s, str):
            b = s.encode("utf-8")
        else:
            b = s
        self._buf.write(b)
        return len(s) if isinstance(s, str) else len(b)
    def flush(self):  # pragma: no cover
        pass

def run_main_on_text(s: str):
    """Write s to a temp file and run main(['prog', path]); capture raw bytes."""
    with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
        f.write(s)
        f.flush()
        path = f.name
    out_stub = _BytesStd()
    err_stub = _BytesStd()
    orig_out, orig_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = out_stub, err_stub
        code = main(["prog", path])
        return code, out_stub.buffer.getvalue(), err_stub.buffer.getvalue()
    finally:
        sys.stdout, sys.stderr = orig_out, orig_err
        try:
            os.remove(path)
        except OSError:
            pass

# Valid cases
def test_num_twos_complement_negative_example():
    # 1010 (4 bits) => -6
    s = "(<a:1010>)"
    out = parse_marshalled_map(s)
    assert out == ["begin-map", "a -- num -- -6", "end-map"]

def test_simple_string_no_space():
    s = "(<x:abcds>)"
    out = parse_marshalled_map(s)
    assert out == ["begin-map", "x -- string -- abcd", "end-map"]

def test_simple_string_with_space():
    s = "(<a:ef ghs>)"
    out = parse_marshalled_map(s)
    assert out == ["begin-map", "a -- string -- ef gh", "end-map"]

def test_complex_string_percent_decoding():
    s = "(<x:ab%2Ccd>)"  # %2C = comma
    out = parse_marshalled_map(s)
    assert out == ["begin-map", "x -- string -- ab,cd", "end-map"]

def test_nested_map_with_num():
    s = "(<x:(<y:1000>)>)"  # '1000' (4 bits) => -8
    out = parse_marshalled_map(s)
    assert out == [
        "begin-map",
        "x -- map -- ",
        "begin-map",
        "y -- num -- -8",
        "end-map",
        "end-map",
    ]

def test_leading_trailing_whitespace_allowed_around_entire_map():
    s = "  \t ( <a:0> ) \n"
    s = s.strip()  # your parser also strips internally; this mimics allowed outer whitespace
    # But we want to ensure outer whitespace is allowed by the parser itself:
    out = parse_marshalled_map("   \t(<a:0>)  \n")
    assert out == ["begin-map", "a -- num -- 0", "end-map"]

def test_nested_map_mixed_signs():
    s = "(<m:(<p:001,n:1>)>)"  # 001 -> +1, 1 -> -1
    out = parse_marshalled_map(s)
    assert out == [
        "begin-map",
        "m -- map -- ",
        "begin-map",
        "p -- num -- 1",
        "n -- num -- -1",
        "end-map",
        "end-map",
    ]



# Invalid cases (structure & rules)
@pytest.mark.parametrize("s", [
    "(<a:abc%2G>)",   # invalid hex in percent escape
    "(<a:ab%>)",      # truncated percent escape
    "(<a:%>)",        # lone percent, not a valid complex string escape
])
def test_invalid_complex_string_bad_percent(s):
    with pytest.raises(NosjError):
        parse_marshalled_map(s)

def test_duplicate_keys_rejected():
    with pytest.raises(NosjError):
        parse_marshalled_map("(<a:0,a:1>)")

def test_missing_colon_after_key():
    with pytest.raises(NosjError):
        parse_marshalled_map("(<a0>)")

def test_missing_comma_between_pairs():
    with pytest.raises(NosjError):
        parse_marshalled_map("(<a:0b:1>)")

def test_unclosed_map_missing_closing_paren():
    with pytest.raises(NosjError):
        parse_marshalled_map("(<a:0>)x")

def test_trailing_garbage_after_top_level():
    with pytest.raises(NosjError):
        parse_marshalled_map("(<a:0>)junk")

def test_whitespace_inside_map_outside_simple_string_is_invalid():
    # space before key
    with pytest.raises(NosjError):
        parse_marshalled_map("(< a:bs>)")
    # space before colon
    with pytest.raises(NosjError):
        parse_marshalled_map("(<a :bs>)")
    # space after value (not part of a simple-string token)
    with pytest.raises(NosjError):
        parse_marshalled_map("(<a:bs >)")

def test_keys_must_be_lowercase_letters_only():
    for bad in ["A", "a1", "_a", "a_b", "a-"]:
        with pytest.raises(NosjError):
            parse_marshalled_map(f"(<{bad}:0>)")


# -----------------------------
# CLI behavior
# -----------------------------
def test_cli_success_no_stderr_exit0():
    code, out, err = run_main_on_text("(<a:1010>)")
    assert code == 0
    assert out == b"begin-map\na -- num -- -6\nend-map\n"
    assert err == b""

def test_cli_invalid_exit66_and_error_line():
    code, out, err = run_main_on_text("(<a0>)")  # missing colon
    assert code == 66
    assert out == b""
    assert err.startswith(b"ERROR -- ")

def test_cli_missing_file_exit66(capsys):
    # Call main with a non-existent file path
    code = main(["prog", "this_file_does_not_exist.nosj"])
    captured = capsys.readouterr()
    assert code == 66
    assert captured.out == ""
    assert captured.err.startswith("ERROR -- ")
