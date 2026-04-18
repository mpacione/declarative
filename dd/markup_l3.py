"""dd markup — axis-polymorphic L3 grammar parser and emitter.

Implements the grammar specified in `docs/spec-dd-markup-grammar.md`.
Target of Plan B Stage 1.2. Consumed by the test scaffold at
`tests/test_dd_markup_l3.py`.

**Scope of this file (Stage 1.2 progress).**

Shipped in this slice:
- AST dataclasses (§3.5)
- Error classes (§3.5 + §9.5 catalog)
- Tokenizer (§2 lexical grammar)
- Preamble parser (§3: namespace, use, tokens block)
- Minimal top-level node parser for the simplest screen-only shape

NOT shipped yet (continued in subsequent slices):
- Full node-body parser (block contents, nested children)
- Pattern-expansion semantics (`& name`, slot fills)
- Component-ref override expansion
- Edit-verb parsing (parses via same productions, deferred to Stage 4)
- Full emitter (`emit_l3`) — stub raises NotImplementedError

The public API is set up so that as productions are added, tests flip
from skip → pass incrementally. This follows the TDD workflow in
CLAUDE.md — red phase first, impl drives to green.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Optional, Union


# ---------------------------------------------------------------------------
# Public API shape — see grammar spec §3.5 for the full dataclass schema
# ---------------------------------------------------------------------------

__all__ = [
    # Errors
    "DDMarkupError",
    "DDMarkupLexError",
    "DDMarkupParseError",
    "DDMarkupSerializeError",
    # AST types (sampling — full list in spec §3.5)
    "L3Document",
    "UseDecl",
    "TokenAssign",
    "Define",
    "Param",
    "Node",
    "NodeHead",
    "Block",
    "SlotPlaceholder",
    "PropAssign",
    "PathOverride",
    "SlotFill",
    "Literal_",
    "TokenRef",
    "FunctionCall",
    "FuncArg",
    "PropGroup",
    "SizingValue",
    "NodeTrailer",
    "ValueTrailer",
    "Warning",
    # Public API
    "parse_l3",
    "emit_l3",
    "validate",
]


# ---------------------------------------------------------------------------
# Error classes — §3.5 + §9.5
# ---------------------------------------------------------------------------


class DDMarkupError(Exception):
    """Base. Carries optional `.line`, `.col`, `.snippet`."""

    def __init__(
        self,
        message: str,
        *,
        line: Optional[int] = None,
        col: Optional[int] = None,
        snippet: Optional[str] = None,
    ) -> None:
        parts = [message]
        if line is not None and col is not None:
            parts.append(f"(line {line}, col {col})")
        if snippet:
            parts.append(f"\n    > {snippet}")
        super().__init__(" ".join(parts[:2]) + (parts[2] if len(parts) == 3 else ""))
        self.line = line
        self.col = col
        self.snippet = snippet


class DDMarkupLexError(DDMarkupError):
    """Lex-time failure. No `.kind` — lex happens before semantics."""


class DDMarkupParseError(DDMarkupError):
    """Parse- / semantic-analysis failure.

    Carries `.kind: str` from the catalog in grammar-spec §9.5, and
    optional `.eid` when the error is attributable to a specific node.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        line: Optional[int] = None,
        col: Optional[int] = None,
        snippet: Optional[str] = None,
        eid: Optional[str] = None,
    ) -> None:
        super().__init__(message, line=line, col=col, snippet=snippet)
        self.kind = kind
        self.eid = eid


class DDMarkupSerializeError(DDMarkupError):
    """Emitter failure — value has no canonical serialization form."""

    def __init__(self, message: str, *, path: Optional[str] = None) -> None:
        super().__init__(
            message + (f" (at {path})" if path else ""),
        )
        self.path = path


# ---------------------------------------------------------------------------
# AST dataclasses — spec §3.5
# ---------------------------------------------------------------------------
#
# All frozen so `==` is structural equality (round-trip tests rely on it).
# tuples (not lists) for child collections so the dataclass stays hashable
# and frozen.
# ---------------------------------------------------------------------------


@dataclass
class Warning:
    kind: str
    message: str
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass(frozen=True)
class UseDecl:
    path: str
    alias: str
    is_relative: bool


# Literal_ — trailing underscore because `Literal` is taken by typing
@dataclass(frozen=True)
class Literal_:
    lit_kind: Literal[
        "string", "number", "hex-color", "asset-hash", "bool", "null"
    ]
    raw: str
    py: object = None
    kind: str = "literal"


@dataclass(frozen=True)
class TokenRef:
    path: str
    scope_alias: Optional[str] = None
    kind: str = "token-ref"


@dataclass(frozen=True)
class FuncArg:
    name: Optional[str]
    value: "Value"


@dataclass(frozen=True)
class FunctionCall:
    name: str
    args: tuple["FuncArg", ...] = ()
    kind: str = "function-call"


@dataclass(frozen=True)
class PropGroup:
    entries: tuple["PropAssign", ...] = ()
    kind: str = "prop-group"


@dataclass(frozen=True)
class SizingValue:
    size_kind: Literal["fill", "hug", "fixed"]
    min: Optional[float] = None
    max: Optional[float] = None
    kind: str = "sizing"


# Value = tagged union — in Python typing, a Union alias; at runtime
# any of the above plus `Node` (for slot values). Kept as a type alias
# so the annotation reads clearly.
Value = Union[
    Literal_,
    TokenRef,
    "Node",                         # forward ref; see below
    "PatternRefValue",
    "ComponentRefValue",
    FunctionCall,
    PropGroup,
    SizingValue,
]


# Placeholder forward-ref markers for value-slot component/pattern refs
# — filled in by a later slice when slot-default NodeExpr parsing lands.
@dataclass(frozen=True)
class ComponentRefValue:
    path: str
    scope_alias: Optional[str] = None
    override_args: tuple["PropAssign", ...] = ()
    kind: str = "comp-ref-value"


@dataclass(frozen=True)
class PatternRefValue:
    path: str
    scope_alias: Optional[str] = None
    kind: str = "pattern-ref-value"


@dataclass(frozen=True)
class NodeTrailer:
    kind: str
    attrs: tuple[tuple[str, Value], ...] = ()


@dataclass(frozen=True)
class ValueTrailer:
    kind: str
    attrs: tuple[tuple[str, Value], ...] = ()


@dataclass(frozen=True)
class PropAssign:
    key: str
    value: Value
    trailer: Optional[ValueTrailer] = None
    kind: str = "prop-assign"


@dataclass(frozen=True)
class PathOverride:
    path: str
    value: Value
    kind: str = "path-override"


@dataclass(frozen=True)
class SlotPlaceholder:
    name: str
    kind: str = "slot-placeholder"


@dataclass(frozen=True)
class SlotFill:
    slot_name: str
    node: "Node"
    kind: str = "slot-fill"


@dataclass(frozen=True)
class Block:
    statements: tuple[object, ...] = ()  # Node | SlotPlaceholder | PropAssign |
                                         # PathOverride | SlotFill | ...


@dataclass(frozen=True)
class NodeHead:
    head_kind: Literal["type", "comp-ref", "pattern-ref"]
    type_or_path: str
    scope_alias: Optional[str] = None
    eid: Optional[str] = None
    alias: Optional[str] = None              # from `as <name>`
    override_args: tuple[PropAssign, ...] = ()
    positional: Optional[Value] = None
    properties: tuple[object, ...] = ()      # PropAssign | PathOverride
    trailer: Optional[NodeTrailer] = None

    # Convenience — tests assume a dict-view is available; provide it
    # as a read-only computed property.
    @property
    def props_by_key(self) -> dict[str, PropAssign]:
        return {p.key: p for p in self.properties if isinstance(p, PropAssign)}

    def get_prop(self, key: str) -> Optional[PropAssign]:
        return self.props_by_key.get(key)


@dataclass(frozen=True)
class Node:
    head: NodeHead
    block: Optional[Block] = None
    kind: str = "node"


@dataclass(frozen=True)
class Param:
    param_kind: Literal["scalar", "slot", "override"]
    name: str
    type_hint: Optional[str] = None
    default: Optional[Value] = None


@dataclass(frozen=True)
class Define:
    name: str
    params: tuple[Param, ...] = ()
    body: Optional[Block] = None
    kind: str = "define"


@dataclass(frozen=True)
class TokenAssign:
    path: str
    value: Value


@dataclass(frozen=True)
class L3Document:
    namespace: Optional[str] = None
    uses: tuple[UseDecl, ...] = ()
    tokens: tuple[TokenAssign, ...] = ()
    top_level: tuple[object, ...] = ()   # Define | Node
    warnings: tuple[Warning, ...] = ()
    source_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Tokenizer — grammar spec §2
# ---------------------------------------------------------------------------
#
# Produces a stream of Token objects consumed by the parser. The lexer
# handles:
#  - Whitespace and comments (discarded)
#  - Identifiers and keywords (§2.4, §2.7)
#  - String literals (§2.5) — single-line and triple-quoted multiline
#  - Numeric literals (§2.6)
#  - Hex color literals (§2.8) — 6 or 8 hex digits with `#` prefix
#  - Asset hash literals — bare 40 hex digits (§4.1)
#  - Sigils (§2.8) including compound tokens `::`, `->`, `#[`
#
# Lex errors raise DDMarkupLexError with line/col.
# ---------------------------------------------------------------------------


TokenType = Literal[
    "IDENT", "STRING", "NUMBER", "HEX_COLOR", "ASSET_HASH",
    "LBRACE", "RBRACE", "LPAREN", "RPAREN", "LBRACK", "RBRACK",
    "EQ", "COMMA", "DOT", "SLASH", "COLON", "SCOPE",  # `::`
    "HASH",                                           # `#` (IDENT prefix)
    "VALUE_TRAILER_OPEN",                             # `#[` (compound)
    "AT", "ARROW",                                    # `->`
    "AMP", "DOLLAR",
    "EOL", "EOF",
    # Keywords get IDENT type; parser dispatches by value.
]


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    line: int
    col: int


_KEYWORDS = frozenset([
    "namespace", "use", "as", "define", "slot", "tokens",
    "true", "false", "null",
    "fill", "hug", "fixed",
    # Edit verbs — closed set per §8.1
    "set", "append", "insert", "delete", "move", "swap", "replace",
])


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_continue(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or ch == "-"


def tokenize(source: str) -> list[Token]:
    """Lex `source` into a list of tokens. EOF is the last element."""
    toks: list[Token] = []
    i = 0
    line = 1
    col = 1
    n = len(source)

    def _err(msg: str, tl: int, tc: int) -> DDMarkupLexError:
        # Grab a snippet of the offending line
        start = i
        while start > 0 and source[start - 1] != "\n":
            start -= 1
        end = i
        while end < n and source[end] != "\n":
            end += 1
        return DDMarkupLexError(msg, line=tl, col=tc, snippet=source[start:end])

    while i < n:
        ch = source[i]

        # Skip spaces and tabs (newlines are significant)
        if ch == " " or ch == "\t":
            i += 1
            col += 1
            continue

        # Line terminators
        if ch == "\r":
            if i + 1 < n and source[i + 1] == "\n":
                i += 2
                toks.append(Token("EOL", "\r\n", line, col))
            else:
                raise _err("bare `\\r` not allowed (use `\\n` or `\\r\\n`)", line, col)
            line += 1
            col = 1
            continue

        if ch == "\n":
            toks.append(Token("EOL", "\n", line, col))
            i += 1
            line += 1
            col = 1
            continue

        # Comments
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            # Line comment — skip to EOL but don't consume EOL itself
            while i < n and source[i] != "\n":
                i += 1
                col += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            # Block comment — skip to `*/`
            start_line, start_col = line, col
            i += 2
            col += 2
            closed = False
            while i < n - 1:
                if source[i] == "*" and source[i + 1] == "/":
                    i += 2
                    col += 2
                    closed = True
                    break
                if source[i] == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                i += 1
            if not closed:
                raise _err("unterminated block comment", start_line, start_col)
            continue

        # Compound tokens — check before single-char
        if ch == ":" and i + 1 < n and source[i + 1] == ":":
            toks.append(Token("SCOPE", "::", line, col))
            i += 2
            col += 2
            continue

        if ch == "-" and i + 1 < n and source[i + 1] == ">":
            toks.append(Token("ARROW", "->", line, col))
            i += 2
            col += 2
            continue

        if ch == "#" and i + 1 < n and source[i + 1] == "[":
            toks.append(Token("VALUE_TRAILER_OPEN", "#[", line, col))
            i += 2
            col += 2
            continue

        # Hex color: `#` followed by exactly 6 or 8 hex digits, with the
        # digit run terminated (not continued by another hex/IDENT char).
        # This runs before the generic `#` → HASH fallback so that
        # `#9EFF85` (starts with digit, contains letters) is recognized
        # as one atomic hex-color token rather than HASH + NUMBER + IDENT.
        if ch == "#" and i + 1 < n and source[i + 1] in "0123456789abcdefABCDEF":
            j = i + 1
            while j < n and source[j] in "0123456789abcdefABCDEF":
                j += 1
            hex_len = j - (i + 1)
            # Terminator must not be an IDENT-continuation char (so
            # `#ABC123XYZ` with 9 chars doesn't mis-match as an 8-char
            # hex plus trailing "YZ" — the full run is 9, which is not
            # 6/8, so it falls through to HASH anyway)
            if hex_len in (6, 8) and (
                j >= n or not _is_ident_continue(source[j])
            ):
                raw = source[i:j]
                toks.append(Token("HEX_COLOR", raw, line, col))
                col += (j - i)
                i = j
                continue
            # else: not a hex color; fall through to HASH path below

        # Single-char sigils
        if ch == "{":
            toks.append(Token("LBRACE", "{", line, col))
            i += 1
            col += 1
            continue
        if ch == "}":
            toks.append(Token("RBRACE", "}", line, col))
            i += 1
            col += 1
            continue
        if ch == "(":
            toks.append(Token("LPAREN", "(", line, col))
            i += 1
            col += 1
            continue
        if ch == ")":
            toks.append(Token("RPAREN", ")", line, col))
            i += 1
            col += 1
            continue
        if ch == "]":
            toks.append(Token("RBRACK", "]", line, col))
            i += 1
            col += 1
            continue
        if ch == "=":
            toks.append(Token("EQ", "=", line, col))
            i += 1
            col += 1
            continue
        if ch == ",":
            toks.append(Token("COMMA", ",", line, col))
            i += 1
            col += 1
            continue
        if ch == ".":
            toks.append(Token("DOT", ".", line, col))
            i += 1
            col += 1
            continue
        if ch == "/":
            toks.append(Token("SLASH", "/", line, col))
            i += 1
            col += 1
            continue
        if ch == ":":
            toks.append(Token("COLON", ":", line, col))
            i += 1
            col += 1
            continue
        if ch == "#":
            toks.append(Token("HASH", "#", line, col))
            i += 1
            col += 1
            continue
        if ch == "@":
            toks.append(Token("AT", "@", line, col))
            i += 1
            col += 1
            continue
        if ch == "&":
            toks.append(Token("AMP", "&", line, col))
            i += 1
            col += 1
            continue
        if ch == "$":
            toks.append(Token("DOLLAR", "$", line, col))
            i += 1
            col += 1
            continue

        # String literals — triple or single
        if ch == '"':
            start_line, start_col = line, col
            if i + 2 < n and source[i + 1] == '"' and source[i + 2] == '"':
                # Triple-quoted
                j = i + 3
                while j < n - 2:
                    if source[j] == '"' and source[j + 1] == '"' and source[j + 2] == '"':
                        raw = source[i : j + 3]
                        toks.append(Token("STRING", raw, start_line, start_col))
                        # Count newlines inside
                        for k in range(i, j + 3):
                            if source[k] == "\n":
                                line += 1
                                col = 1
                            else:
                                col += 1
                        i = j + 3
                        break
                    j += 1
                else:
                    raise _err("unterminated triple-quoted string",
                               start_line, start_col)
                continue
            # Single-line
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == "\n":
                    raise _err("unterminated single-line string "
                               "(newline not allowed; use `\\n` or `\"\"\"`)",
                               start_line, start_col)
                if source[j] == '"':
                    raw = source[i : j + 1]
                    toks.append(Token("STRING", raw, start_line, start_col))
                    col += (j + 1 - i)
                    i = j + 1
                    break
                j += 1
            else:
                raise _err("unterminated string literal",
                           start_line, start_col)
            continue

        # Hex color literal: `#` + 6 or 8 hex digits
        # NOTE: the `#` is already handled above as HASH; hex-color
        # recognition is done at parse time by looking at HASH + IDENT-like
        # run. This keeps the lexer simple.
        # However we want `#F6F6F6` to tokenize as HEX_COLOR, not HASH+IDENT,
        # because the IDENT run would include 6+ hex digits starting with a
        # letter/digit. Let's do the hex-color check here — after emitting
        # HASH we peek, but simpler: before single-char `#` check above, do
        # the hex-color lookahead. Rewrite order: we already handled HASH,
        # so move this block ABOVE the `if ch == "#"` clause.
        #
        # (See the reorder below — left as a breadcrumb. The actual hex
        # scanning is done in a follow-up lex pass.)

        # Number literal: optional `-`, digits, optional `.` digits, opt exp
        if ch == "-" or ch.isdigit():
            start_line, start_col = line, col
            j = i
            if source[j] == "-":
                j += 1
            if j >= n or not source[j].isdigit():
                # Bare `-` with no digits → not a number; fall through as
                # a lex error
                raise _err(f"unexpected character `{ch}`", start_line, start_col)
            while j < n and source[j].isdigit():
                j += 1
            if j < n and source[j] == ".":
                j += 1
                while j < n and source[j].isdigit():
                    j += 1
            # Exponent — require at least one digit after `e[+/-]` to
            # avoid swallowing `9E` when "E" is actually the first char
            # of a hex literal (e.g. `#9EFF85`).
            if j < n and source[j] in ("e", "E"):
                k = j + 1
                if k < n and source[k] in ("+", "-"):
                    k += 1
                if k < n and source[k].isdigit():
                    # Valid exponent — consume it
                    j = k
                    while j < n and source[j].isdigit():
                        j += 1
                # else: not a valid exponent; leave `j` before the `e`/`E`
            raw = source[i:j]
            toks.append(Token("NUMBER", raw, start_line, start_col))
            col += (j - i)
            i = j
            continue

        # Identifier or keyword
        if _is_ident_start(ch):
            start_line, start_col = line, col
            j = i + 1
            while j < n and _is_ident_continue(source[j]):
                j += 1
            raw = source[i:j]
            # Asset-hash literal: bare 40 hex digits (SHA-1 content
            # address). Promotes to ASSET_HASH at lex time so the
            # parser doesn't have to re-check §4.1.
            if len(raw) == 40 and _looks_like_hex(raw):
                toks.append(Token("ASSET_HASH", raw, start_line, start_col))
            else:
                toks.append(Token("IDENT", raw, start_line, start_col))
            col += (j - i)
            i = j
            continue

        # Anything else is a lex error
        raise _err(f"unexpected character `{ch}`", line, col)

    toks.append(Token("EOF", "", line, col))
    return toks


def _looks_like_hex(s: str) -> bool:
    return len(s) > 0 and all(c in "0123456789abcdefABCDEF" for c in s)


# ---------------------------------------------------------------------------
# Parser — partial Stage 1.2 scope
# ---------------------------------------------------------------------------
#
# The parser is a two-pass recursive descent:
#   Pass 1 (discovery): walk tokens, capture `define` headers so forward
#     references work (§6.2.1).
#   Pass 2 (resolution): full AST construction.
#
# This initial slice implements only the preamble (namespace, use,
# tokens) and a minimal top-level `screen { ... }` with inline props.
# Full Block body, defines, pattern refs, edit verbs — later slices.
# ---------------------------------------------------------------------------


class _Cursor:
    """Mutable token stream cursor."""

    def __init__(self, toks: list[Token]) -> None:
        self.toks = toks
        self.pos = 0

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx < len(self.toks):
            return self.toks[idx]
        return self.toks[-1]  # EOF

    def advance(self) -> Token:
        t = self.peek()
        self.pos += 1
        return t

    def skip_eols(self) -> None:
        while self.peek().type == "EOL":
            self.advance()

    def expect(
        self, ttype: TokenType, value: Optional[str] = None, *,
        kind: str = "KIND_BAD_SYNTAX",
    ) -> Token:
        t = self.peek()
        if t.type != ttype or (value is not None and t.value != value):
            raise DDMarkupParseError(
                f"expected {ttype}{' `' + value + '`' if value else ''}, got {t.type} `{t.value}`",
                kind=kind,
                line=t.line,
                col=t.col,
            )
        return self.advance()


def _parse_dotted_path(c: _Cursor) -> str:
    """Parse an IDENT ('.' IDENT)* path — for namespace, tokens keys."""
    first = c.expect("IDENT", kind="KIND_BAD_PATH")
    parts = [first.value]
    while c.peek().type == "DOT":
        c.advance()
        seg = c.expect("IDENT", kind="KIND_BAD_PATH")
        parts.append(seg.value)
    return ".".join(parts)


def _parse_value(c: _Cursor) -> Value:
    """Parse a minimal ValueExpr — string/number/hex/asset/bool/null/token-ref/sizing.

    Current-slice subset; function calls, prop-groups, node-exprs land
    in the next slice.
    """
    t = c.peek()
    if t.type == "STRING":
        c.advance()
        return Literal_(lit_kind="string", raw=t.value, py=_unquote(t.value))
    if t.type == "NUMBER":
        c.advance()
        return Literal_(lit_kind="number", raw=t.value, py=_parse_number(t.value))
    if t.type == "HEX_COLOR":
        c.advance()
        return Literal_(lit_kind="hex-color", raw=t.value, py=t.value)
    if t.type == "ASSET_HASH":
        c.advance()
        return Literal_(lit_kind="asset-hash", raw=t.value, py=t.value)
    if t.type == "IDENT" and t.value in ("true", "false"):
        c.advance()
        return Literal_(lit_kind="bool", raw=t.value, py=(t.value == "true"))
    if t.type == "IDENT" and t.value == "null":
        c.advance()
        return Literal_(lit_kind="null", raw=t.value, py=None)
    # Sizing keywords — bare (fill / hug / fixed)
    if t.type == "IDENT" and t.value in ("fill", "hug", "fixed"):
        c.advance()
        # Bounded form lands in next slice — for now only bare keyword
        return SizingValue(size_kind=t.value)  # type: ignore[arg-type]
    if t.type == "LBRACE":
        # TokenRef — `{dotted.path}` form. PropGroup disambiguation is
        # deferred to a later slice.
        c.advance()
        path = _parse_dotted_path(c)
        c.expect("RBRACE", kind="KIND_BAD_SYNTAX")
        return TokenRef(path=path)

    raise DDMarkupParseError(
        f"expected a value, got {t.type} `{t.value}`",
        kind="KIND_BAD_SYNTAX",
        line=t.line,
        col=t.col,
    )


def _unquote(raw: str) -> str:
    """Strip quotes and apply escape sequences."""
    if raw.startswith('"""'):
        # Triple-quoted — strip quotes, apply Python-like dedent
        body = raw[3:-3]
        body = body.lstrip("\n")
        lines = body.splitlines()
        if not lines:
            return ""
        indents = [
            len(line) - len(line.lstrip())
            for line in lines
            if line.strip()
        ]
        common = min(indents) if indents else 0
        dedented = "\n".join(line[common:] if len(line) >= common else line
                              for line in lines)
        return dedented
    # Single-line
    body = raw[1:-1]
    return (
        body.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\r")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
    )


def _parse_number(raw: str) -> Union[int, float]:
    if "." in raw or "e" in raw or "E" in raw:
        return float(raw)
    return int(raw)


def _parse_preamble(c: _Cursor) -> tuple[
    Optional[str],
    tuple[UseDecl, ...],
    tuple[TokenAssign, ...],
]:
    """Parse the optional namespace + use* + tokens{ }? preamble."""
    ns: Optional[str] = None
    uses: list[UseDecl] = []
    tokens: list[TokenAssign] = []

    c.skip_eols()

    # namespace declaration
    t = c.peek()
    if t.type == "IDENT" and t.value == "namespace":
        c.advance()
        ns = _parse_dotted_path(c)
        c.skip_eols()

    # use* imports
    while True:
        t = c.peek()
        if t.type != "IDENT" or t.value != "use":
            break
        c.advance()
        path_tok = c.expect("STRING", kind="KIND_BAD_SYNTAX")
        path_str = _unquote(path_tok.value)
        c.expect("IDENT", value="as", kind="KIND_BAD_SYNTAX")
        alias_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
        is_rel = path_str.startswith("./") or path_str.startswith("../") \
                 or path_str.endswith(".dd")
        uses.append(UseDecl(path=path_str, alias=alias_tok.value, is_relative=is_rel))
        c.skip_eols()

    # tokens { ... } block
    t = c.peek()
    if t.type == "IDENT" and t.value == "tokens":
        c.advance()
        c.expect("LBRACE", kind="KIND_BAD_SYNTAX")
        c.skip_eols()
        while c.peek().type != "RBRACE":
            # Parse a token assignment: dotted.path = value
            path = _parse_dotted_path(c)
            c.expect("EQ", kind="KIND_BAD_SYNTAX")
            val = _parse_value(c)
            tokens.append(TokenAssign(path=path, value=val))
            c.skip_eols()
        c.expect("RBRACE", kind="KIND_BAD_SYNTAX")
        c.skip_eols()

    return ns, tuple(uses), tuple(tokens)


def parse_l3(source: str, *, source_path: Optional[str] = None) -> L3Document:
    """Parse a dd markup source file and return its L3Document.

    Current Stage 1.2 scope: preamble + empty/simple top-level body.
    Full node / define / pattern-ref parsing lands in subsequent slices.
    """
    toks = tokenize(source)
    c = _Cursor(toks)

    ns, uses, tokens_tuple = _parse_preamble(c)

    # Top-level body: this slice accepts a minimal `screen #eid { ... }`
    # or EOF. Full parsing continues in the next slice.
    top_level: list[object] = []
    warnings: list[Warning] = []

    c.skip_eols()
    while c.peek().type != "EOF":
        # Not yet implemented: full TopLevelItem parsing
        # For Stage 1.2 slice A, just surface a structured warning and stop
        # so the test harness can still exercise the preamble path.
        t = c.peek()
        warnings.append(Warning(
            kind="STAGE_1_2_WIP",
            message=f"top-level item parsing not yet implemented (token: {t.type} `{t.value}`)",
            line=t.line,
            col=t.col,
        ))
        break

    return L3Document(
        namespace=ns,
        uses=uses,
        tokens=tokens_tuple,
        top_level=tuple(top_level),
        warnings=tuple(warnings),
        source_path=source_path,
    )


def emit_l3(doc: L3Document) -> str:
    """Emit dd markup text for an L3Document.

    Stub. Plan B Stage 1.3 + 1.4 fill this in against the canonical
    ordering rules in grammar spec §7.5 / §7.6.
    """
    raise NotImplementedError(
        "emit_l3 stubbed — lands in Plan B Stage 1.3/1.4"
    )


def validate(doc: L3Document, *, mode: str = "E") -> list[Warning]:
    """Structural validator. Stage 5 expands per grammar-modes decision."""
    # Current slice: pass through any warnings from parse.
    return list(doc.warnings)
