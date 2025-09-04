# deserializer.py
# Marshalled nosj map grammar (this file):
#   Overall: optional leading/trailing whitespace, then "(<" ... ">)"
#   Inside the map: "<key:value[,key:value,...]>"
#     - key: one or more lowercase letters [a-z]+ (unique within the current map)
#     - value: one of
#         * num:      [01]+   (two's complement)
#         * sstring:  [A-Za-z0-9 \t]+s   (trailing 's' is not part of value)
#         * cstring:  token containing at least one %XX (hex), decoded as bytes
#         * map:      nested "(< ... >)"
#   No whitespace inside the map text except:
#     - spaces/tabs inside a simple-string token
#     - whitespace before "(<" or after ">)" (outermost only)
# Output (pretty):
#   - begin-map / end-map
#   - "key -- map -- " then "begin-map"/"end-map" for nested maps
#   - "key -- num -- <int>" for nums
#   - "key -- string -- <decoded>" for strings
#
# Errors: print exactly one line to stderr starting with "ERROR -- " and exit 66.

import re
import sys
from typing import Iterator, List, Tuple

# Patterns for scalar recognition
BIN_RE = re.compile(r"^[01]+$")
SIMPLE_STR_RE = re.compile(r"^([A-Za-z0-9 \t]+)s$")
KEY_RE = re.compile(r"^[a-z]+$")  # keys: lowercase only per spec

class NosjError(Exception):
    pass


def _err(msg: str) -> Tuple[int, None]:
    sys.stderr.buffer.write((f"ERROR -- {msg}\n").encode("utf-8"))
    return 66, None


# -------- Percent-decoding for complex strings --------
def _decode_percent_bytes(token: str) -> Tuple[str, bool]:
    """
    Decode %XX sequences to bytes. Returns (latin1_string, had_percent).
    Raises NosjError on malformed % escapes.
    """
    out = bytearray()
    i, n = 0, len(token)
    had = False
    while i < n:
        ch = token[i]
        if ch == '%':
            if i + 2 >= n or any(c not in "0123456789abcdefABCDEF" for c in token[i+1:i+3]):
                raise NosjError("Invalid percent-encoding in complex string")
            b = int(token[i+1:i+3], 16)
            out.append(b)
            i += 3
            had = True
        else:
            # raw ASCII byte
            out.append(ord(ch))
            i += 1
    return out.decode('latin-1'), had


# -------- Core tokenization (no whitespace allowed outside s-strings) --------
class Cursor:
    def __init__(self, s: str):
        self.s = s
        self.i = 0
        self.n = len(s)

    def peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.s[j] if j < self.n else ''

    def eat(self, ch: str) -> None:
        if self.peek() != ch:
            raise NosjError(f"Expected '{ch}'")
        self.i += 1

    def eat_seq(self, seq: str) -> None:
        if self.s[self.i:self.i+len(seq)] != seq:
            raise NosjError(f"Expected '{seq}'")
        self.i += len(seq)

    def at_end(self) -> bool:
        return self.i >= self.n


def _parse_key(cur: Cursor) -> str:
    start = cur.i
    while cur.peek().islower():
        cur.i += 1
    key = cur.s[start:cur.i]
    if not key:
        raise NosjError("Missing key")
    if not KEY_RE.fullmatch(key):
        raise NosjError(f"Invalid key: {key!r}")
    return key


def _parse_value(cur: Cursor) -> Tuple[str, str]:
    """
    Returns (type, value_string) where type in {'num','string','map'}.
    For 'map', value_string is unused (empty).
    """
    ch = cur.peek()

    # Nested map
    if ch == '(' and cur.s[cur.i:cur.i+2] == '(<':
        # Parse nested map inline
        return 'map', ''

    # Otherwise scan until delimiter: ',' or '>' (end of map)
    start = cur.i
    # IMPORTANT: no whitespace allowed in tokens for nums/complex strings.
    # Simple-strings may include spaces/tabs but *must* end with trailing 's'.
    # Strategy:
    #   - If we ever see a space/tab, we will only accept it if the entire token
    #     matches SIMPLE_STR_RE. So we consume until next delimiter and validate.
    while True:
        c = cur.peek()
        if c == '' or c in {',', '>'}:
            break
        if c in {'(', ')', '<', ':'}:
            raise NosjError("Unexpected structural character inside value")
        # We'll validate whitespace rules after we know the token
        cur.i += 1
    token = cur.s[start:cur.i]

    # Classify token
    if '%' in token:
        decoded, had = _decode_percent_bytes(token)
        if not had:
            raise NosjError("Complex string must contain at least one %XX")
        return 'string', decoded

    # If token has any whitespace, it must be a simple-string by regex.
    if any(ch in ' \t' for ch in token):
        m = SIMPLE_STR_RE.fullmatch(token)
        if not m:
            raise NosjError("Whitespace outside simple-string")
        return 'string', m.group(1)

    # Pure token (no whitespace). Try num, then simple-string, else error.
    if BIN_RE.fullmatch(token):
        # num
        val = int(token, 2)
        nbits = len(token)
        if token[0] == '1':  # negative
            val -= (1 << nbits)
        return 'num', str(val)

    m = SIMPLE_STR_RE.fullmatch(token)
    if m:
        return 'string', m.group(1)

    # Otherwise treat as complex without % is NOT allowed; error.
    raise NosjError("Unrecognized value token")


def _parse_map_body(cur: Cursor, emit: List[str]) -> None:
    """
    Parse the inside of '< ... >' given cursor at first char after '<'.
    Emits pretty lines to 'emit'.
    """
    seen_keys = set()
    first = True
    while True:
        # End of map?
        if cur.peek() == '>':
            cur.eat('>')
            return

        if not first:
            # Expect comma between pairs
            if cur.peek() != ',':
                raise NosjError("Expected ',' between key-value pairs")
            cur.eat(',')
        first = False

        # Parse "key:value"
        key = _parse_key(cur)
        if key in seen_keys:
            raise NosjError("Duplicate key in map")
        seen_keys.add(key)

        if cur.peek() != ':':
            raise NosjError("Expected ':' after key")
        cur.eat(':')

        # Value
        if cur.peek() == '(' and cur.s[cur.i:cur.i+2] == '(<':
            # Nested map value
            emit.append(f"{key} -- map -- ")
            emit.append("begin-map")
            # consume "(<"
            cur.eat('('); cur.eat('<')
            _parse_map_body(cur, emit)
            # expect ")"
            if cur.peek() != ')':
                raise NosjError("Expected ')' after nested map")
            cur.eat(')')
            emit.append("end-map")
        else:
            typ, sval = _parse_value(cur)
            if typ == 'num':
                emit.append(f"{key} -- num -- {sval}")
            elif typ == 'string':
                emit.append(f"{key} -- string -- {sval}")
            else:
                # should not happen; maps handled above
                raise NosjError("Internal error parsing value")


def parse_marshalled_map(s: str) -> List[str]:
    """
    Entry: s is the entire marshalled nosj string for *one* map.
    Leading/trailing whitespace allowed; none inside except in simple-strings.
    """
    s = s.strip()
    cur = Cursor(s)

    # Outer "(< ... >)" with optional surrounding whitespace
    if cur.s[cur.i:cur.i+2] != '(<':
        raise NosjError("Map must start with '(<'")
    cur.eat('('); cur.eat('<')

    out: List[str] = []
    out.append("begin-map")
    _parse_map_body(cur, out)

    if cur.peek() != ')':
        raise NosjError("Map must end with ')'")
    cur.eat(')')
    if not cur.at_end():
        raise NosjError("Trailing characters after top-level map")
    out.append("end-map")
    return out


# ---------- CLI (LF-only output and single-line error) ----------
def _writeline_stdout(line: str) -> None:
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))

def _writeline_stderr_error(msg: str) -> None:
    sys.stderr.buffer.write((f"ERROR -- {msg}\n").encode("utf-8"))

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        _writeline_stderr_error("missing input file")
        return 66
    try:
        data = open(argv[1], "r", encoding="utf-8").read()
        for line in parse_marshalled_map(data):
            _writeline_stdout(line)
        return 0
    except FileNotFoundError:
        _writeline_stderr_error("file not found")
        return 66
    except NosjError as e:
        _writeline_stderr_error(str(e))
        return 66
    except ValueError as e:
        _writeline_stderr_error(str(e))
        return 66

if __name__ == "__main__":
    sys.exit(main(sys.argv))
