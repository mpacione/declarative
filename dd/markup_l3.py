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
        "string", "number", "hex-color", "asset-hash", "bool", "null", "enum"
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

        # Asset hash literal: 40 hex digits (lower/mixed case). Must be
        # checked BEFORE the number path because asset hashes can start
        # with a digit (SHA-1 output is hex-encoded, uniform distribution).
        # Terminator must not be IDENT-continuation to avoid matching a
        # prefix of some longer identifier.
        if ch in "0123456789abcdefABCDEF":
            j = i
            while j < n and source[j] in "0123456789abcdefABCDEF":
                j += 1
            hex_run_len = j - i
            if hex_run_len == 40 and (
                j >= n or not _is_ident_continue(source[j])
            ):
                raw = source[i:j]
                toks.append(Token("ASSET_HASH", raw, line, col))
                col += (j - i)
                i = j
                continue
            # else: not an asset hash; fall through to NUMBER/IDENT paths

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


_SIZING_KW = frozenset(("fill", "hug", "fixed"))
_BOOL_NULL_KW = frozenset(("true", "false", "null"))


def _parse_value(c: _Cursor) -> Value:
    """Parse a ValueExpr per grammar §4.1.

    Dispatches on the first token of the RHS. Handles all value forms:
    literal, token-ref, prop-group, sizing (bare + bounded),
    function-call, comp-ref-value (at slot-default), pattern-ref-value.
    """
    t = c.peek()

    # Literals
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
    if t.type == "IDENT" and t.value in _BOOL_NULL_KW:
        c.advance()
        if t.value == "null":
            return Literal_(lit_kind="null", raw=t.value, py=None)
        return Literal_(lit_kind="bool", raw=t.value, py=(t.value == "true"))

    # Sizing keywords. Bare (`fill`) or bounded (`fill(min=N, max=N)`).
    if t.type == "IDENT" and t.value in _SIZING_KW:
        return _parse_sizing(c)

    # LBRACE: TokenRef or PropGroup. Disambiguate via look-ahead.
    if t.type == "LBRACE":
        return _parse_brace_value(c)

    # Component-ref value (at slot-default site): `-> path/to/comp(args)`
    if t.type == "ARROW":
        return _parse_comp_ref_as_value(c)

    # Pattern-ref value: `& name.with.dots`
    if t.type == "AMP":
        return _parse_pattern_ref_as_value(c)

    # FunctionCall: IDENT followed by LPAREN
    if t.type == "IDENT" and c.peek(1).type == "LPAREN":
        return _parse_function_call(c)

    # EnumLit — bare IDENT used as a value (e.g., `layout=vertical`,
    # `align=center`, `mainAxis=space-between`). Catch-all for enum-like
    # keywords that aren't otherwise reserved. The schema validator
    # (capability-gated per ADR-001) checks legality at semantic time.
    if t.type == "IDENT":
        c.advance()
        return Literal_(lit_kind="enum", raw=t.value, py=t.value)

    raise DDMarkupParseError(
        f"expected a value, got {t.type} `{t.value}`",
        kind="KIND_BAD_SYNTAX",
        line=t.line,
        col=t.col,
    )


def _parse_sizing(c: _Cursor) -> SizingValue:
    """SizingKeyword | SizingBounded (grammar §3 + §4.4)."""
    kw = c.advance()
    assert kw.value in _SIZING_KW
    if c.peek().type != "LPAREN":
        return SizingValue(size_kind=kw.value)  # type: ignore[arg-type]
    # Bounded: fill(min=N, max=N)
    c.advance()  # (
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    while c.peek().type != "RPAREN":
        key = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
        if key.value not in ("min", "max"):
            raise DDMarkupParseError(
                f"sizing bound arg must be `min` or `max`, got `{key.value}`",
                kind="KIND_BAD_SYNTAX", line=key.line, col=key.col,
            )
        c.expect("EQ", kind="KIND_BAD_SYNTAX")
        num = c.expect("NUMBER", kind="KIND_BAD_SYNTAX")
        parsed = _parse_number(num.value)
        if key.value == "min":
            min_val = float(parsed)
        else:
            max_val = float(parsed)
        if c.peek().type == "COMMA":
            c.advance()
    c.expect("RPAREN", kind="KIND_BAD_SYNTAX")
    return SizingValue(size_kind=kw.value, min=min_val, max=max_val)  # type: ignore[arg-type]


def _parse_brace_value(c: _Cursor) -> Value:
    """After `{` in value position: TokenRef or PropGroup.

    Disambiguation:
      - `{ IDENT . IDENT ... }` or `{ IDENT }` → TokenRef
      - `{ IDENT = ... }` (or multi-entry) → PropGroup
    """
    c.advance()  # {
    # Empty `{}` is a lex error here; defer to the parser check:
    if c.peek().type == "RBRACE":
        raise DDMarkupParseError(
            "empty `{}` not allowed in value position",
            kind="KIND_BAD_SYNTAX",
            line=c.peek().line, col=c.peek().col,
        )
    # Look ahead: first IDENT followed by `.` or `}` means TokenRef,
    # followed by `=` means PropGroup.
    first = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
    if c.peek().type == "DOT" or c.peek().type == "RBRACE":
        # TokenRef
        parts = [first.value]
        while c.peek().type == "DOT":
            c.advance()
            seg = c.expect("IDENT", kind="KIND_BAD_PATH")
            parts.append(seg.value)
        c.expect("RBRACE", kind="KIND_BAD_SYNTAX")
        return TokenRef(path=".".join(parts))
    if c.peek().type == "EQ":
        # PropGroup
        entries: list[PropAssign] = []
        # First entry
        c.advance()  # =
        val = _parse_value(c)
        entries.append(PropAssign(key=first.value, value=val))
        _skip_propgroup_sep(c)
        while c.peek().type != "RBRACE":
            key_path = _parse_dotted_or_single(c)
            c.expect("EQ", kind="KIND_BAD_SYNTAX")
            v = _parse_value(c)
            entries.append(PropAssign(key=key_path, value=v))
            _skip_propgroup_sep(c)
        c.expect("RBRACE", kind="KIND_BAD_SYNTAX")
        return PropGroup(entries=tuple(entries))
    raise DDMarkupParseError(
        f"expected `.`, `}}`, or `=` inside brace value; got {c.peek().type} `{c.peek().value}`",
        kind="KIND_BAD_SYNTAX",
        line=c.peek().line, col=c.peek().col,
    )


def _skip_propgroup_sep(c: _Cursor) -> None:
    """PropGroup entries are separated by `,`, EOL, or whitespace (§2/§7.6).

    At this point the tokenizer has emitted EOL for newlines but has
    discarded spaces, so the only tokens we need to consume between
    entries are COMMA and EOL.
    """
    while c.peek().type in ("COMMA", "EOL"):
        c.advance()


def _parse_dotted_or_single(c: _Cursor) -> str:
    """Parse IDENT (. IDENT)* — single or dotted path."""
    first = c.expect("IDENT", kind="KIND_BAD_PATH")
    parts = [first.value]
    while c.peek().type == "DOT":
        c.advance()
        seg = c.expect("IDENT", kind="KIND_BAD_PATH")
        parts.append(seg.value)
    return ".".join(parts)


def _parse_function_call(c: _Cursor) -> FunctionCall:
    """IDENT `(` FuncArgs? `)` per grammar §3/§4.3."""
    name_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
    c.expect("LPAREN", kind="KIND_BAD_SYNTAX")
    args: list[FuncArg] = []
    # skip initial EOLs after `(` — allow multi-line function calls
    while c.peek().type == "EOL":
        c.advance()
    while c.peek().type != "RPAREN":
        arg = _parse_func_arg(c)
        args.append(arg)
        # comma, EOL, or close
        while c.peek().type in ("COMMA", "EOL"):
            c.advance()
    c.expect("RPAREN", kind="KIND_BAD_SYNTAX")
    return FunctionCall(name=name_tok.value, args=tuple(args))


def _parse_func_arg(c: _Cursor) -> FuncArg:
    """FuncArg — either positional ValueExpr or `name=ValueExpr`."""
    # Look-ahead: if IDENT followed by `=`, it's a keyword arg.
    if c.peek().type == "IDENT" and c.peek(1).type == "EQ":
        name = c.advance().value
        c.advance()  # =
        return FuncArg(name=name, value=_parse_value(c))
    return FuncArg(name=None, value=_parse_value(c))


def _parse_comp_ref_as_value(c: _Cursor) -> ComponentRefValue:
    """`-> path/to/comp(optional-args)` used as a value expression.

    Only appears as a slot-default or inside a PropAssign's RHS that
    maps to a structural param (exercised in fixture 01's
    `slot cta = -> button/small/solid(label={cta_label})`).
    """
    c.expect("ARROW", kind="KIND_BAD_SYNTAX")
    scope, path = _parse_comp_path(c)
    override_args: tuple[PropAssign, ...] = ()
    if c.peek().type == "LPAREN":
        override_args = _parse_override_args(c)
    return ComponentRefValue(path=path, scope_alias=scope, override_args=override_args)


def _parse_pattern_ref_as_value(c: _Cursor) -> PatternRefValue:
    c.expect("AMP", kind="KIND_BAD_SYNTAX")
    scope, path = _parse_pattern_path(c)
    return PatternRefValue(path=path, scope_alias=scope)


def _parse_comp_path(c: _Cursor) -> tuple[Optional[str], str]:
    """Parse a CompPath — `IDENT '::'? IDENT '/' IDENT ...`.

    `.` appearing in a CompPath is `KIND_BAD_PATH`.
    Returns (scope_alias, slash-path).
    """
    first = c.expect("IDENT", kind="KIND_BAD_PATH")
    scope: Optional[str] = None
    if c.peek().type == "SCOPE":
        c.advance()
        scope = first.value
        first = c.expect("IDENT", kind="KIND_BAD_PATH")
    # Must be followed by `/` for a multi-segment slash-path, OR just
    # a bare single-segment name (rare but legal, e.g. `-> icon/back`
    # is two segments; `-> safari-bottom` might be one).
    parts = [first.value]
    while c.peek().type == "SLASH":
        c.advance()
        seg = c.expect("IDENT", kind="KIND_BAD_PATH")
        parts.append(seg.value)
    # If a DOT appears here, that's a violation — CompPath uses `/`.
    if c.peek().type == "DOT":
        t = c.peek()
        raise DDMarkupParseError(
            f"`.` not allowed in component-ref path (use `/`)",
            kind="KIND_BAD_PATH",
            line=t.line, col=t.col,
        )
    return scope, "/".join(parts)


def _parse_pattern_path(c: _Cursor) -> tuple[Optional[str], str]:
    """Parse a PatternPath — `IDENT '::'? IDENT ('.' IDENT)*`.

    `/` appearing in a PatternPath is `KIND_BAD_PATH`.
    Returns (scope_alias, dotted-path).
    """
    first = c.expect("IDENT", kind="KIND_BAD_PATH")
    scope: Optional[str] = None
    if c.peek().type == "SCOPE":
        c.advance()
        scope = first.value
        first = c.expect("IDENT", kind="KIND_BAD_PATH")
    parts = [first.value]
    while c.peek().type == "DOT":
        c.advance()
        seg = c.expect("IDENT", kind="KIND_BAD_PATH")
        parts.append(seg.value)
    # A SLASH here is a violation.
    if c.peek().type == "SLASH":
        t = c.peek()
        raise DDMarkupParseError(
            f"`/` not allowed in pattern-ref path (use `.`)",
            kind="KIND_BAD_PATH",
            line=t.line, col=t.col,
        )
    return scope, ".".join(parts)


def _parse_override_args(c: _Cursor) -> tuple[PropAssign, ...]:
    """`(key=val, key=val, ...)` — per grammar §3 OverrideArgs."""
    c.expect("LPAREN", kind="KIND_BAD_SYNTAX")
    args: list[PropAssign] = []
    while c.peek().type != "RPAREN":
        while c.peek().type == "EOL":
            c.advance()
        key = _parse_dotted_or_single(c)
        c.expect("EQ", kind="KIND_BAD_SYNTAX")
        val = _parse_value(c)
        args.append(PropAssign(key=key, value=val))
        while c.peek().type in ("COMMA", "EOL"):
            c.advance()
    c.expect("RPAREN", kind="KIND_BAD_SYNTAX")
    return tuple(args)


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


# ---------------------------------------------------------------------------
# Top-level + Node + Block + Define parsing
# ---------------------------------------------------------------------------
#
# Grammar productions implemented in this section:
#   TopLevelItem := DefineDecl | Node
#   Node         := NodeHead Block?
#   NodeHead     := (TypeKeyword | CompRef | PatternRef)
#                   EID? ('as' IDENT)?
#                   PositionalContent?
#                   NodeProperty*
#                   NodeTrailer?
#   Block        := '{' (Node | SlotPlaceholder | PropAssign
#                       | PathOverride | SlotFill | ValueTrailer)* '}'
#   DefineDecl   := 'define' IDENT ParamList Block
#   ParamList    := '(' (Param (',' Param)* ','?)? ')'
#   Param        := ScalarParam | SlotParam
#
# Disambiguation rules live in grammar §3.1/§3.2 (applied below).
# ---------------------------------------------------------------------------


# Type keywords per grammar §2.7. This set is closed at parse time; new
# canonical types extend it by editing the grammar spec AND this set
# together. `fill`/`hug`/`fixed` are value keywords, not TypeKeyword.
_TYPE_KEYWORDS = frozenset((
    "screen", "frame", "text", "rectangle", "vector", "group", "ellipse",
    "button", "card", "header", "container", "icon", "image", "slider",
    "heading", "tabs", "overlay", "list", "input", "toggle", "checkbox",
    "radio", "avatar", "badge", "dialog", "drawer", "menu", "popover",
    "tooltip", "chart", "divider", "boolean-operation", "line", "star",
    "polygon", "nav",
))

_TEXT_BEARING_TYPES = frozenset((
    "text", "heading", "button", "badge", "tooltip", "input",
))


def _is_statement_starter(tt: TokenType, value: str) -> bool:
    """Per grammar §2.2 — what tokens can start a new statement?"""
    if tt == "IDENT":
        return value in _TYPE_KEYWORDS or value in (
            "define", "namespace", "use", "tokens",
            "set", "append", "insert", "delete", "move", "swap", "replace",
        )
    return tt in ("ARROW", "AMP", "AT", "DOLLAR")


def _parse_node_trailer(c: _Cursor) -> Optional[NodeTrailer]:
    """Parse `(kind key=val key=val)` — node-level provenance trailer."""
    if c.peek().type != "LPAREN":
        return None
    # Look-ahead: inside `(`, must start with IDENT to be a trailer.
    # Otherwise it could be a function-call arg-list (shouldn't reach
    # here — function-calls are in value position).
    if c.peek(1).type != "IDENT":
        return None
    c.advance()  # (
    kind_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
    attrs: list[tuple[str, Value]] = []
    while c.peek().type != "RPAREN":
        while c.peek().type in ("COMMA", "EOL"):
            c.advance()
        if c.peek().type == "RPAREN":
            break
        key = _parse_dotted_or_single(c)
        c.expect("EQ", kind="KIND_BAD_SYNTAX")
        val = _parse_value(c)
        attrs.append((key, val))
    c.expect("RPAREN", kind="KIND_BAD_SYNTAX")
    return NodeTrailer(kind=kind_tok.value, attrs=tuple(attrs))


def _parse_value_trailer(c: _Cursor) -> Optional[ValueTrailer]:
    """Parse `#[kind key=val ...]` — value-level provenance trailer."""
    if c.peek().type != "VALUE_TRAILER_OPEN":
        return None
    c.advance()  # #[
    kind_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
    attrs: list[tuple[str, Value]] = []
    while c.peek().type != "RBRACK":
        while c.peek().type in ("COMMA", "EOL"):
            c.advance()
        if c.peek().type == "RBRACK":
            break
        key = _parse_dotted_or_single(c)
        c.expect("EQ", kind="KIND_BAD_SYNTAX")
        val = _parse_value(c)
        attrs.append((key, val))
    c.expect("RBRACK", kind="KIND_BAD_SYNTAX")
    return ValueTrailer(kind=kind_tok.value, attrs=tuple(attrs))


def _parse_node(c: _Cursor) -> Node:
    """Parse a full Node per grammar §3."""
    t = c.peek()

    head_kind: Literal["type", "comp-ref", "pattern-ref"]
    scope_alias: Optional[str] = None
    type_or_path: str
    override_args: tuple[PropAssign, ...] = ()

    if t.type == "ARROW":
        c.advance()
        scope_alias, type_or_path = _parse_comp_path(c)
        head_kind = "comp-ref"
        if c.peek().type == "LPAREN":
            # OverrideArgs inline on the node head
            override_args = _parse_override_args(c)
    elif t.type == "AMP":
        c.advance()
        scope_alias, type_or_path = _parse_pattern_path(c)
        head_kind = "pattern-ref"
    elif t.type == "IDENT" and t.value in _TYPE_KEYWORDS:
        c.advance()
        type_or_path = t.value
        head_kind = "type"
    else:
        raise DDMarkupParseError(
            f"expected a node head (TypeKeyword, `->`, or `&`), got {t.type} `{t.value}`",
            kind="KIND_BAD_SYNTAX",
            line=t.line, col=t.col,
        )

    # Optional EID
    eid: Optional[str] = None
    if c.peek().type == "HASH":
        c.advance()
        eid_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
        eid = eid_tok.value

    # Optional `as <name>` alias (sugar for #eid at pattern-ref call sites)
    alias: Optional[str] = None
    if c.peek().type == "IDENT" and c.peek().value == "as":
        c.advance()
        alias_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
        alias = alias_tok.value

    # Optional positional content on text-bearing types.
    # PositionalContent := StringLit | TokenRef
    # Positional may appear on a continuation line after the head start,
    # so skip EOLs with rollback if the next token isn't positional.
    positional: Optional[Value] = None
    if head_kind == "type" and type_or_path in _TEXT_BEARING_TYPES:
        saved_for_pos = c.pos
        while c.peek().type == "EOL":
            c.advance()
        pk = c.peek()
        if pk.type == "STRING":
            c.advance()
            positional = Literal_(lit_kind="string", raw=pk.value, py=_unquote(pk.value))
        elif pk.type == "LBRACE":
            # Could be TokenRef (positional) or PropGroup (unlikely here).
            # Look ahead: IDENT followed by `.` or `}` → TokenRef.
            if c.peek(1).type == "IDENT" and c.peek(2).type in ("DOT", "RBRACE"):
                positional = _parse_brace_value(c)
            else:
                c.pos = saved_for_pos    # not positional, rewind
        else:
            c.pos = saved_for_pos        # not positional, rewind

    # NodeProperty* — PropAssign | PathOverride, plus inline ValueTrailer
    # attached to the preceding value.
    properties: list[object] = []
    trailer: Optional[NodeTrailer] = None

    while True:
        # Skip intra-head EOLs (multi-line head continuation, grammar §2.2)
        # But only skip EOLs if the next non-EOL token is a continuation
        # of the head (a property, trailer, or block open).
        saved_pos = c.pos
        while c.peek().type == "EOL":
            c.advance()
        nxt = c.peek()
        # Termination conditions per §2.2
        if nxt.type in ("LBRACE", "RBRACE", "EOF"):
            break
        # An IDENT that's a TypeKeyword looks like a statement-starter,
        # BUT if it's followed by `=` or `.`, it's a property path
        # (e.g., `container.gap=8` where `container` is both a type
        # keyword AND a legal internal-eid). Continue the head in that
        # case.
        is_type_continuation_prop = (
            nxt.type == "IDENT"
            and nxt.value in _TYPE_KEYWORDS
            and c.peek(1).type in ("EQ", "DOT")
        )
        if (
            _is_statement_starter(nxt.type, nxt.value)
            and not is_type_continuation_prop
            and c.pos != saved_pos
        ):
            # A new statement on a new line ends the head
            c.pos = saved_pos
            # Consume the trailing EOLs so the block/parent sees them
            while c.peek().type == "EOL":
                c.advance()
            break

        # NodeTrailer on the head line — `(kind ...)` before block/end
        if nxt.type == "LPAREN" and c.peek(1).type == "IDENT":
            trailer = _parse_node_trailer(c)
            continue

        # PropAssign / PathOverride (both are `IDENT (.IDENT)* = value`)
        if nxt.type == "IDENT":
            # Must not be a RESERVED_KEYWORD (like 'as' — handled above)
            if nxt.value == "as":
                break
            key = _parse_dotted_or_single(c)
            c.expect("EQ", kind="KIND_BAD_SYNTAX")
            val = _parse_value(c)
            # Value-level trailer may be inline or on a continuation line.
            saved = c.pos
            while c.peek().type == "EOL":
                c.advance()
            vtrailer = _parse_value_trailer(c)
            if vtrailer is None:
                c.pos = saved
            if "." in key:
                properties.append(PathOverride(path=key, value=val))
            else:
                properties.append(PropAssign(key=key, value=val, trailer=vtrailer))
            continue

        if nxt.type == "DOLLAR":
            # $ext.* property keys
            c.advance()
            key_rest_first = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
            key_parts = ["$" + key_rest_first.value]
            while c.peek().type == "DOT":
                c.advance()
                seg = c.expect("IDENT", kind="KIND_BAD_PATH")
                key_parts.append(seg.value)
            full_key = ".".join(key_parts)
            c.expect("EQ", kind="KIND_BAD_SYNTAX")
            val = _parse_value(c)
            properties.append(PropAssign(key=full_key, value=val))
            continue

        # Something else — end of head
        break

    # Optional Block body. Disambiguate: `{` immediately followed by
    # `IDENT }` is a SIBLING SlotPlaceholder (the next statement at the
    # outer block's level), not a child-block open for this node.
    block: Optional[Block] = None
    while c.peek().type == "EOL":
        c.advance()
    if (
        c.peek().type == "LBRACE"
        and not (
            c.peek(1).type == "IDENT"
            and c.peek(2).type == "RBRACE"
        )
    ):
        block = _parse_block(c)

    head = NodeHead(
        head_kind=head_kind,
        type_or_path=type_or_path,
        scope_alias=scope_alias,
        eid=eid,
        alias=alias,
        override_args=override_args,
        positional=positional,
        properties=tuple(properties),
        trailer=trailer,
    )
    return Node(head=head, block=block)


def _parse_block(c: _Cursor) -> Block:
    """Parse a `{ ... }` block body per grammar §3."""
    lbrace = c.expect("LBRACE", kind="KIND_BAD_SYNTAX")
    c.skip_eols()
    stmts: list[object] = []

    # Empty `{}` is forbidden per Q6 — KIND_EMPTY_BLOCK
    if c.peek().type == "RBRACE":
        c.advance()
        raise DDMarkupParseError(
            "empty `{}` block is forbidden; use absence instead",
            kind="KIND_EMPTY_BLOCK",
            line=lbrace.line, col=lbrace.col,
        )

    while c.peek().type != "RBRACE":
        stmt = _parse_block_statement(c)
        stmts.append(stmt)
        c.skip_eols()
    c.expect("RBRACE", kind="KIND_BAD_SYNTAX")
    return Block(statements=tuple(stmts))


def _parse_block_statement(c: _Cursor) -> object:
    """Dispatch: Node | SlotPlaceholder | SlotFill | PropAssign | PathOverride.

    Dispatch order matters. `text="Done"` inside a CompRef block is a
    PropAssign where `text` is the property KEY (Figma instance-override
    text), NOT a text node. So the `IDENT = value` / `IDENT . path = value`
    branch runs BEFORE the TypeKeyword → Node branch.
    """
    t = c.peek()

    # SlotPlaceholder `{name}` as a standalone block statement
    if t.type == "LBRACE" and c.peek(1).type == "IDENT" and c.peek(2).type == "RBRACE":
        c.advance()  # {
        name_tok = c.advance()  # IDENT
        c.advance()  # }
        return SlotPlaceholder(name=name_tok.value)

    # IDENT followed by `=` / `.` → PropAssign / PathOverride / SlotFill.
    # This runs BEFORE the TypeKeyword-is-node check because type keywords
    # may legitimately be used as property keys (e.g., `text="Done"` as a
    # Figma instance override on a CompRef).
    if t.type == "IDENT":
        tt = c.peek(1).type
        if tt == "EQ":
            rhs = c.peek(2)
            is_node_rhs = (
                (rhs.type == "IDENT" and rhs.value in _TYPE_KEYWORDS)
                or rhs.type == "ARROW"
                or rhs.type == "AMP"
            )
            if is_node_rhs:
                slot_name = c.advance().value
                c.advance()  # =
                node = _parse_node(c)
                return SlotFill(slot_name=slot_name, node=node)
            # PropAssign
            key = c.advance().value
            c.advance()  # =
            val = _parse_value(c)
            vtrailer = _parse_value_trailer(c)
            return PropAssign(key=key, value=val, trailer=vtrailer)
        if tt == "DOT":
            path = _parse_dotted_or_single(c)
            c.expect("EQ", kind="KIND_BAD_SYNTAX")
            val = _parse_value(c)
            return PathOverride(path=path, value=val)

    # Node-start tokens: TypeKeyword / `->` / `&`. Falls through here
    # when the IDENT is a TypeKeyword NOT followed by `=` or `.`.
    if (
        (t.type == "IDENT" and t.value in _TYPE_KEYWORDS)
        or t.type == "ARROW"
        or t.type == "AMP"
    ):
        return _parse_node(c)

    # `@eid` reference — edit-context node (parses through same productions)
    if t.type == "AT":
        return _parse_edit_node(c)

    # $ext
    if t.type == "DOLLAR":
        c.advance()
        first = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
        key_parts = ["$" + first.value]
        while c.peek().type == "DOT":
            c.advance()
            seg = c.expect("IDENT", kind="KIND_BAD_PATH")
            key_parts.append(seg.value)
        c.expect("EQ", kind="KIND_BAD_SYNTAX")
        val = _parse_value(c)
        return PropAssign(key=".".join(key_parts), value=val)

    raise DDMarkupParseError(
        f"unexpected token in block body: {t.type} `{t.value}`",
        kind="KIND_BAD_SYNTAX",
        line=t.line, col=t.col,
    )


def _parse_edit_node(c: _Cursor) -> Node:
    """`@eid [props]` — edit-context reference. Parses through Node.

    Wildcard `*`/`**` in an `@eid` path during a NON-edit-verb context
    is `KIND_WILDCARD_IN_CONSTRUCT`. We're inside a block body here,
    not an edit verb — so any wildcard fires the error.
    """
    at_tok = c.expect("AT", kind="KIND_BAD_SYNTAX")
    # Parse @-path; disallow `*` / `**` segments at construction.
    first = c.expect("IDENT", kind="KIND_BAD_PATH")
    parts = [first.value]
    while c.peek().type in ("DOT", "SLASH"):
        sep_tok = c.advance()
        nxt = c.peek()
        if nxt.type == "IDENT":
            parts.append(nxt.value)
            c.advance()
        else:
            # Wildcard or other — only IDENT allowed at construction.
            raise DDMarkupParseError(
                "wildcards are not allowed in construction `@eid` paths "
                "(edit-verb context only)",
                kind="KIND_WILDCARD_IN_CONSTRUCT",
                line=at_tok.line, col=at_tok.col,
            )
    # Synthesize a Node with head_kind=type and the path as the type_or_path.
    # The edit-context semantic is preserved by the leading `@` — the
    # parser produces a Node whose head represents an addressed eid.
    # We encode this by putting the path into `type_or_path` with a
    # special scope_alias="@" marker. A future semantic analyzer
    # dispatches on this.
    # Now parse any trailing properties.
    properties: list[object] = []
    c.skip_eols()
    while True:
        nxt = c.peek()
        if nxt.type in ("RBRACE", "EOF", "LBRACE"):
            break
        if _is_statement_starter(nxt.type, nxt.value):
            break
        if nxt.type == "IDENT":
            key = _parse_dotted_or_single(c)
            c.expect("EQ", kind="KIND_BAD_SYNTAX")
            val = _parse_value(c)
            if "." in key:
                properties.append(PathOverride(path=key, value=val))
            else:
                properties.append(PropAssign(key=key, value=val))
            while c.peek().type == "EOL":
                c.advance()
            continue
        break
    head = NodeHead(
        head_kind="type",
        type_or_path="@" + ".".join(parts),
        scope_alias="@",
        properties=tuple(properties),
    )
    return Node(head=head, block=None)


# ---------------------------------------------------------------------------
# Define parser
# ---------------------------------------------------------------------------


_VALID_TYPE_HINTS = frozenset((
    "text", "number", "bool", "color", "dimension", "node", "slot",
))


def _parse_define(c: _Cursor) -> Define:
    """`define NAME(params) { body }` per grammar §6.1."""
    c.expect("IDENT", value="define", kind="KIND_BAD_SYNTAX")
    name_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
    params = _parse_param_list(c)
    c.skip_eols()
    body = _parse_block(c)
    return Define(name=name_tok.value, params=tuple(params), body=body)


def _parse_param_list(c: _Cursor) -> list[Param]:
    """`(param, param, ...)`  — optional, comma-separated, trailing-comma OK."""
    c.expect("LPAREN", kind="KIND_BAD_SYNTAX")
    params: list[Param] = []
    while c.peek().type == "EOL":
        c.advance()
    while c.peek().type != "RPAREN":
        params.append(_parse_param(c))
        while c.peek().type in ("COMMA", "EOL"):
            c.advance()
    c.expect("RPAREN", kind="KIND_BAD_SYNTAX")
    return params


def _parse_param(c: _Cursor) -> Param:
    """ScalarParam | SlotParam per grammar §3.

    SlotParam defaults are NodeExpr (full node), not generic Value —
    per grammar §6.1 a slot fills a structural subtree position.
    """
    t = c.peek()
    if t.type == "IDENT" and t.value == "slot":
        c.advance()
        name = c.expect("IDENT", kind="KIND_BAD_SYNTAX").value
        default: Optional[Value] = None
        if c.peek().type == "EQ":
            c.advance()
            # Slot default is a NodeExpr — parse via _parse_node if the
            # RHS starts with a node-head token, else fall back to a
            # generic value (rare — NodeExpr is the spec'd form).
            rhs = c.peek()
            if (
                (rhs.type == "IDENT" and rhs.value in _TYPE_KEYWORDS)
                or rhs.type == "ARROW"
                or rhs.type == "AMP"
            ):
                default = _parse_node(c)     # type: ignore[assignment]
            else:
                default = _parse_value(c)
        return Param(param_kind="slot", name=name, type_hint=None, default=default)
    # ScalarParam — `name: type [= default]`
    name = c.expect("IDENT", kind="KIND_BAD_SYNTAX").value
    c.expect("COLON", kind="KIND_BAD_SYNTAX")
    type_hint_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
    type_hint = type_hint_tok.value
    default2: Optional[Value] = None
    if c.peek().type == "EQ":
        c.advance()
        default2 = _parse_value(c)
    return Param(
        param_kind="scalar",
        name=name,
        type_hint=type_hint,
        default=default2,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_l3(source: str, *, source_path: Optional[str] = None) -> L3Document:
    """Parse a dd markup source file and return its L3Document.

    Stage 1.2 scope (slices A–I):
    - Full preamble (namespace + use + tokens)
    - Top-level nodes and defines with nested blocks
    - All value forms (literal, token-ref, prop-group, sizing, function-call,
      comp-ref-value, pattern-ref-value)
    - Node + value trailers
    - Pattern refs, slot fills, slot placeholders, path overrides
    - `$ext.*` extension metadata
    - Edit-context `@eid` in construction (parses; wildcard detection
      fires `KIND_WILDCARD_IN_CONSTRUCT`)
    """
    toks = tokenize(source)
    c = _Cursor(toks)

    ns, uses, tokens_tuple = _parse_preamble(c)

    top_level: list[object] = []
    warnings: list[Warning] = []

    c.skip_eols()
    while c.peek().type != "EOF":
        t = c.peek()
        if t.type == "IDENT" and t.value == "define":
            top_level.append(_parse_define(c))
        else:
            top_level.append(_parse_node(c))
        c.skip_eols()

    # Semantic pass: collect `KIND_UNUSED_IMPORT` warnings.
    used_aliases: set[str] = set()
    _collect_scope_aliases(top_level, used_aliases)
    for ta in tokens_tuple:
        _collect_scope_aliases((ta.value,), used_aliases)
    for u in uses:
        if u.alias not in used_aliases:
            warnings.append(Warning(
                kind="KIND_UNUSED_IMPORT",
                message=f"`use` alias `{u.alias}` is never referenced",
                line=None, col=None,
            ))

    return L3Document(
        namespace=ns,
        uses=uses,
        tokens=tokens_tuple,
        top_level=tuple(top_level),
        warnings=tuple(warnings),
        source_path=source_path,
    )


def _collect_scope_aliases(items: object, out: set[str]) -> None:
    """Walk AST and collect every scope_alias use site."""
    if items is None:
        return
    if isinstance(items, (list, tuple)):
        for it in items:
            _collect_scope_aliases(it, out)
        return
    if isinstance(items, L3Document):
        _collect_scope_aliases(items.top_level, out)
        for ta in items.tokens:
            _collect_scope_aliases(ta.value, out)
        return
    sa = getattr(items, "scope_alias", None)
    if isinstance(sa, str):
        out.add(sa)
    # Recurse into children
    for attr in (
        "top_level", "statements", "properties", "override_args",
        "entries", "args", "params", "value", "default", "body",
        "block", "head", "positional", "trailer", "node",
    ):
        child = getattr(items, attr, None)
        if child is not None and child is not items:
            _collect_scope_aliases(child, out)


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
