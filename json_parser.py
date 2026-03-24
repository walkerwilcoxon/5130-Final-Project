# Prompt (using Claude Sonnet 4.6): 
# Implement a JSON parser in Python in 300 lines of code. Do not use external libraries including built in Python libraries. 
# The program should include multiple functions. You do not need to handle hexadecimal numbers, Unicode escapes, or regular escapes. Include test cases.

"""
A from-scratch JSON parser in Python (~300 lines).
No external libraries. No stdlib imports.

Supports:
  - null, true, false
  - Numbers (int and float, negative, exponent)
  - Strings (basic, no unicode/hex escapes needed)
  - Arrays
  - Objects
  - Nested structures
  - Whitespace handling
"""


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class JSONParseError(Exception):
    def __init__(self, message, pos=None):
        location = f" at position {pos}" if pos is not None else ""
        super().__init__(f"JSONParseError: {message}{location}")
        self.pos = pos


# ---------------------------------------------------------------------------
# Parser state: a thin wrapper around the source string + cursor
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, source):
        self.source = source
        self.pos = 0

    def peek(self):
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def advance(self):
        ch = self.source[self.pos]
        self.pos += 1
        return ch

    def expect(self, ch):
        actual = self.peek()
        if actual != ch:
            raise JSONParseError(
                f"Expected '{ch}' but got {repr(actual)}", self.pos
            )
        self.advance()

    def eof(self):
        return self.pos >= len(self.source)

    def remaining(self):
        return self.source[self.pos:]


# ---------------------------------------------------------------------------
# Whitespace
# ---------------------------------------------------------------------------

def skip_whitespace(p):
    while not p.eof() and p.peek() in (' ', '\t', '\n', '\r'):
        p.advance()


# ---------------------------------------------------------------------------
# Literals: null, true, false
# ---------------------------------------------------------------------------

def parse_literal(p):
    """Try to match null / true / false at current position."""
    rest = p.remaining()
    if rest.startswith("null"):
        p.pos += 4
        return None
    if rest.startswith("true"):
        p.pos += 4
        return True
    if rest.startswith("false"):
        p.pos += 5
        return False
    raise JSONParseError(f"Unknown literal near {repr(rest[:10])}", p.pos)


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def _is_digit(ch):
    return ch is not None and '0' <= ch <= '9'


def parse_number(p):
    """
    Parse a JSON number (int or float).
    Grammar: [-] (0 | [1-9][0-9]*) [. [0-9]+] [(e|E) [+|-] [0-9]+]
    """
    start = p.pos
    buf = []

    # Optional leading minus
    if p.peek() == '-':
        buf.append(p.advance())

    # Integer part
    if p.peek() == '0':
        buf.append(p.advance())
    elif _is_digit(p.peek()):
        while _is_digit(p.peek()):
            buf.append(p.advance())
    else:
        raise JSONParseError("Invalid number", p.pos)

    is_float = False

    # Optional fractional part
    if p.peek() == '.':
        is_float = True
        buf.append(p.advance())
        if not _is_digit(p.peek()):
            raise JSONParseError("Digit expected after '.'", p.pos)
        while _is_digit(p.peek()):
            buf.append(p.advance())

    # Optional exponent
    if p.peek() in ('e', 'E'):
        is_float = True
        buf.append(p.advance())
        if p.peek() in ('+', '-'):
            buf.append(p.advance())
        if not _is_digit(p.peek()):
            raise JSONParseError("Digit expected in exponent", p.pos)
        while _is_digit(p.peek()):
            buf.append(p.advance())

    raw = ''.join(buf)
    if is_float:
        return _parse_float(raw)
    return _parse_int(raw)


def _parse_int(s):
    """Convert string to int without int()."""
    negative = s.startswith('-')
    digits = s[1:] if (negative or s.startswith('+')) else s
    result = 0
    for ch in digits:
        result = result * 10 + (ord(ch) - ord('0'))
    return -result if negative else result


def _parse_float(s):
    """Convert string to float without float()."""
    # Split on 'e'/'E' for exponent
    exp_val = 0
    if 'e' in s or 'E' in s:
        split_ch = 'e' if 'e' in s else 'E'
        mantissa_str, exp_str = s.split(split_ch, 1)
        exp_val = _parse_int(exp_str)
    else:
        mantissa_str = s

    negative = mantissa_str.startswith('-')
    mantissa_str = mantissa_str.lstrip('-')

    if '.' in mantissa_str:
        int_part_str, frac_part_str = mantissa_str.split('.', 1)
    else:
        int_part_str, frac_part_str = mantissa_str, ''

    int_part = _parse_int(int_part_str) if int_part_str else 0
    frac_part = 0.0
    if frac_part_str:
        frac_part = _parse_int(frac_part_str) / (10 ** len(frac_part_str))

    result = int_part + frac_part
    if exp_val > 0:
        result = result * (10 ** exp_val)
    elif exp_val < 0:
        result = result / (10 ** (-exp_val))
    return -result if negative else result


# ---------------------------------------------------------------------------
# Strings
# ---------------------------------------------------------------------------

def parse_string(p):
    """Parse a JSON string (double-quoted). Basic escapes only."""
    p.expect('"')
    buf = []
    while True:
        ch = p.peek()
        if ch is None:
            raise JSONParseError("Unterminated string", p.pos)
        if ch == '"':
            p.advance()
            break
        if ch == '\\':
            p.advance()
            esc = p.peek()
            if esc is None:
                raise JSONParseError("Unterminated escape sequence", p.pos)
            p.advance()
            ESCAPES = {
                '"':  '"',
                '\\': '\\',
                '/':  '/',
                'n':  '\n',
                'r':  '\r',
                't':  '\t',
                'b':  '\b',
                'f':  '\f',
            }
            if esc in ESCAPES:
                buf.append(ESCAPES[esc])
            else:
                raise JSONParseError(f"Unknown escape sequence \\{esc}", p.pos)
        else:
            buf.append(p.advance())
    return ''.join(buf)


# ---------------------------------------------------------------------------
# Arrays
# ---------------------------------------------------------------------------

def parse_array(p):
    """Parse a JSON array: [ value, value, ... ]"""
    p.expect('[')
    result = []
    skip_whitespace(p)
    if p.peek() == ']':
        p.advance()
        return result
    while True:
        skip_whitespace(p)
        result.append(parse_value(p))
        skip_whitespace(p)
        if p.peek() == ',':
            p.advance()
        elif p.peek() == ']':
            p.advance()
            break
        else:
            raise JSONParseError(
                f"Expected ',' or ']' in array, got {repr(p.peek())}", p.pos
            )
    return result


# ---------------------------------------------------------------------------
# Objects
# ---------------------------------------------------------------------------

def parse_object(p):
    """Parse a JSON object: { \"key\": value, ... }"""
    p.expect('{')
    result = {}
    skip_whitespace(p)
    if p.peek() == '}':
        p.advance()
        return result
    while True:
        skip_whitespace(p)
        if p.peek() != '"':
            raise JSONParseError(
                f"Expected string key, got {repr(p.peek())}", p.pos
            )
        key = parse_string(p)
        skip_whitespace(p)
        p.expect(':')
        skip_whitespace(p)
        value = parse_value(p)
        result[key] = value
        skip_whitespace(p)
        if p.peek() == ',':
            p.advance()
        elif p.peek() == '}':
            p.advance()
            break
        else:
            raise JSONParseError(
                f"Expected ',' or '}}' in object, got {repr(p.peek())}", p.pos
            )
    return result


# ---------------------------------------------------------------------------
# Value dispatcher
# ---------------------------------------------------------------------------

def parse_value(p):
    """Dispatch to the appropriate parser based on the next character."""
    skip_whitespace(p)
    ch = p.peek()
    if ch is None:
        raise JSONParseError("Unexpected end of input", p.pos)
    if ch == '"':
        return parse_string(p)
    if ch == '{':
        return parse_object(p)
    if ch == '[':
        return parse_array(p)
    if ch == '-' or _is_digit(ch):
        return parse_number(p)
    if ch in ('n', 't', 'f'):
        return parse_literal(p)
    raise JSONParseError(f"Unexpected character {repr(ch)}", p.pos)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(source):
    """Parse a JSON string and return the corresponding Python object."""
    if not isinstance(source, str):
        raise TypeError(f"Expected str, got {type(source).__name__}")
    p = Parser(source)
    skip_whitespace(p)
    value = parse_value(p)
    skip_whitespace(p)
    if not p.eof():
        raise JSONParseError(
            f"Unexpected trailing content: {repr(p.remaining()[:20])}", p.pos
        )
    return value


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  PASS  {name}")

    def fail(self, name, reason):
        self.failed += 1
        self.errors.append((name, reason))
        print(f"  FAIL  {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed.")
        if self.errors:
            print("Failed tests:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")


def _approx_eq(a, b, tol=1e-9):
    if type(a) is float or type(b) is float:
        return abs(a - b) < tol
    return a == b

def _assert_eq(r, name, got, expected):
    if _approx_eq(got, expected):
        r.ok(name)
    else:
        r.fail(name, f"got {repr(got)}, expected {repr(expected)}")


def _assert_raises(r, name, fn):
    try:
        fn()
        r.fail(name, "Expected JSONParseError but none was raised")
    except JSONParseError:
        r.ok(name)
    except Exception as e:
        r.fail(name, f"Wrong exception type: {type(e).__name__}: {e}")


def run_tests():
    r = TestResult()
    print("=" * 50)
    print("Running JSON parser tests")
    print("=" * 50)

    # --- Literals ---
    _assert_eq(r, "null",              parse("null"),  None)
    _assert_eq(r, "true",              parse("true"),  True)
    _assert_eq(r, "false",             parse("false"), False)

    # --- Numbers ---
    _assert_eq(r, "zero",              parse("0"),         0)
    _assert_eq(r, "positive int",      parse("42"),        42)
    _assert_eq(r, "negative int",      parse("-7"),        -7)
    _assert_eq(r, "float",             parse("3.14"),      3.14)
    _assert_eq(r, "negative float",    parse("-0.5"),      -0.5)
    _assert_eq(r, "exponent lower",    parse("1e3"),       1000.0)
    _assert_eq(r, "exponent upper",    parse("2E2"),       200.0)
    _assert_eq(r, "exponent plus",     parse("1.5e+2"),    150.0)
    _assert_eq(r, "exponent minus",    parse("3e-1"),      0.3)
    _assert_eq(r, "large int",         parse("1000000"),   1000000)

    # --- Strings ---
    _assert_eq(r, "empty string",      parse('""'),          "")
    _assert_eq(r, "simple string",     parse('"hello"'),     "hello")
    _assert_eq(r, "escaped newline",   parse('"a\\nb"'),     "a\nb")
    _assert_eq(r, "escaped tab",       parse('"a\\tb"'),     "a\tb")
    _assert_eq(r, "escaped quote",     parse('"say \\"hi\\""'), 'say "hi"')
    _assert_eq(r, "escaped backslash", parse('"a\\\\b"'),    "a\\b")
    _assert_eq(r, "escaped slash",     parse('"a\\/b"'),     "a/b")
    _assert_eq(r, "spaces in string",  parse('"hello world"'), "hello world")

    # --- Arrays ---
    _assert_eq(r, "empty array",       parse("[]"),          [])
    _assert_eq(r, "int array",         parse("[1,2,3]"),      [1, 2, 3])
    _assert_eq(r, "mixed array",       parse('[1,"a",true,null]'), [1, "a", True, None])
    _assert_eq(r, "nested array",      parse("[[1,2],[3,4]]"),    [[1,2],[3,4]])
    _assert_eq(r, "array whitespace",  parse("[ 1 , 2 , 3 ]"),   [1, 2, 3])

    # --- Objects ---
    _assert_eq(r, "empty object",      parse("{}"),          {})
    _assert_eq(r, "simple object",     parse('{"a":1}'),     {"a": 1})
    _assert_eq(r, "multi-key object",  parse('{"x":1,"y":2}'), {"x": 1, "y": 2})
    _assert_eq(r, "nested object",     parse('{"a":{"b":3}}'), {"a": {"b": 3}})
    _assert_eq(r, "obj with array",    parse('{"k":[1,2]}'),  {"k": [1, 2]})
    _assert_eq(r, "obj whitespace",    parse('{ "a" : 1 }'),  {"a": 1})

    # --- Complex nested ---
    complex_json = '{"name":"Alice","age":30,"scores":[95,87,100],"meta":{"active":true,"notes":null}}'
    expected = {
        "name": "Alice", "age": 30, "scores": [95, 87, 100],
        "meta": {"active": True, "notes": None}
    }
    _assert_eq(r, "complex nested",    parse(complex_json),  expected)

    # --- Whitespace tolerance ---
    _assert_eq(r, "leading whitespace",  parse("   42"),    42)
    _assert_eq(r, "trailing whitespace", parse("42   "),    42)
    _assert_eq(r, "newlines",            parse("\n42\n"),   42)

    # --- Error cases ---
    _assert_raises(r, "error: empty input",      lambda: parse(""))
    _assert_raises(r, "error: bare word",        lambda: parse("hello"))
    _assert_raises(r, "error: single quote str", lambda: parse("'hi'"))
    _assert_raises(r, "error: trailing comma",   lambda: parse("[1,2,]"))
    _assert_raises(r, "error: missing colon",    lambda: parse('{"a" 1}'))
    _assert_raises(r, "error: unterminated str",  lambda: parse('"abc'))
    _assert_raises(r, "error: bad escape",        lambda: parse('"\\q"'))
    _assert_raises(r, "error: trailing content",  lambda: parse("1 2"))
    _assert_raises(r, "error: leading dot float", lambda: parse(".5"))

    r.summary()
    return r.failed == 0


if __name__ == "__main__":
    success = run_tests()

    print("\n--- Live demo ---")
    samples = [
        '{"library":"JSON","version":1,"stable":true,"tags":["fast","pure","simple"]}',
        '[{"id":1,"val":2.5},{"id":2,"val":-1.0e2}]',
    ]
    for s in samples:
        print(f"\nInput : {s}")
        print(f"Output: {parse(s)}")