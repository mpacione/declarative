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
    head_kind: Literal["type", "comp-ref", "pattern-ref", "edit-ref"]
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


# ---------------------------------------------------------------------------
# Edit-verb AST (M7.1) — grammar §8.6
# ---------------------------------------------------------------------------
# Seven verb statements + an ERef helper. All frozen dataclasses for
# pattern-match exhaustiveness + structural equality (no ABC needed
# per the rest of the AST style). Per-verb apply semantics live in
# `apply_edits` below; Pass 1 ships the AST + parser + emitter + stub.


@dataclass(frozen=True)
class ERef:
    """Edit-context reference (`@eid`, `@parent.child`, `@grid/*`).

    Wildcards are parsed (the `has_wildcard` flag is set) but
    `apply_edits` rejects them in M7.1; full wildcard expansion is a
    later milestone.
    """
    path: str
    scope_alias: Optional[str] = None
    has_wildcard: bool = False
    kind: str = "eref"


@dataclass(frozen=True)
class SetStatement:
    target: ERef
    properties: tuple[object, ...] = ()  # PropAssign | PathOverride
    line: Optional[int] = None
    col: Optional[int] = None
    kind: str = "set"
    implicit: bool = False  # `@eid prop=val` form vs `set @eid prop=val`


@dataclass(frozen=True)
class DeleteStatement:
    target: ERef
    line: Optional[int] = None
    col: Optional[int] = None
    kind: str = "delete"


@dataclass(frozen=True)
class AppendStatement:
    to: "ERef"
    body: "Block"
    line: Optional[int] = None
    col: Optional[int] = None
    kind: str = "append"


@dataclass(frozen=True)
class InsertStatement:
    into: "ERef"
    anchor: "ERef"
    anchor_rel: Literal["after", "before"] = "after"
    body: "Block" = None  # set by parser
    line: Optional[int] = None
    col: Optional[int] = None
    kind: str = "insert"


@dataclass(frozen=True)
class MoveStatement:
    target: "ERef"
    to: "ERef"
    position: Literal["first", "last", "after", "before"] = "last"
    position_anchor: Optional["ERef"] = None
    line: Optional[int] = None
    col: Optional[int] = None
    kind: str = "move"


@dataclass(frozen=True)
class SwapStatement:
    target: "ERef"
    with_node: "Node"
    line: Optional[int] = None
    col: Optional[int] = None
    kind: str = "swap"


@dataclass(frozen=True)
class ReplaceStatement:
    target: "ERef"
    body: "Block"
    line: Optional[int] = None
    col: Optional[int] = None
    kind: str = "replace"


# Type alias for the tagged-union of all verb statement types.
EditStatement = Union[
    SetStatement,
    DeleteStatement,
    AppendStatement,
    InsertStatement,
    MoveStatement,
    SwapStatement,
    ReplaceStatement,
]


@dataclass(frozen=True)
class L3Document:
    namespace: Optional[str] = None
    uses: tuple[UseDecl, ...] = ()
    tokens: tuple[TokenAssign, ...] = ()
    top_level: tuple[object, ...] = ()   # Define | Node
    edits: tuple[object, ...] = ()       # EditStatement (M7.1)
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
    "LBRACE", "RBRACE", "LPAREN", "RPAREN", "RBRACK",
    "EQ", "COMMA", "DOT", "SLASH", "COLON", "SCOPE",  # `::`
    "HASH",                                           # `#` (IDENT prefix)
    "VALUE_TRAILER_OPEN",                             # `#[` (compound)
    "AT", "ARROW",                                    # `->`
    "AMP", "DOLLAR",
    "STAR", "DSTAR",                                  # `*` / `**` (edit-only)
    "EOL", "EOF",
    # Keywords get IDENT type; parser dispatches by value.
    # Note: `LBRACK` is intentionally absent — bare `[` is not a token;
    # `#[` is a compound VALUE_TRAILER_OPEN (the only context `[` can appear).
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

        # Comments — only recognized at a token-separating position.
        # A `/*` inside a slash-path (e.g., `grid/*/buy-button` where
        # `*` is a wildcard) must NOT be mis-lexed as a comment-open.
        # Check: the preceding character must be whitespace / EOL /
        # start-of-file. This mirrors how most config languages handle
        # comment lookahead.
        at_token_boundary = (i == 0) or source[i - 1] in " \t\r\n"
        if (
            at_token_boundary
            and ch == "/"
            and i + 1 < n
            and source[i + 1] == "/"
        ):
            while i < n and source[i] != "\n":
                i += 1
                col += 1
            continue
        if (
            at_token_boundary
            and ch == "/"
            and i + 1 < n
            and source[i + 1] == "*"
        ):
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

        # Wildcards `*` and `**` — edit-only per §5.2; lex here so the
        # parser can detect them in construction context and raise
        # KIND_WILDCARD_IN_CONSTRUCT with a proper parse error.
        if ch == "*":
            if i + 1 < n and source[i + 1] == "*":
                toks.append(Token("DSTAR", "**", line, col))
                i += 2
                col += 2
            else:
                toks.append(Token("STAR", "*", line, col))
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

        # Asset hash literal: exactly 40 hex chars, requiring at least
        # one decimal digit to disambiguate from legitimate 40-char all-
        # hex-letter identifiers (e.g. `abcdefabcdef...abcd`). For real
        # SHA-1 outputs, the probability of zero digits in 40 random hex
        # chars is (6/16)^40 ≈ 1.5×10⁻¹⁷ — effectively never. Terminator
        # must not be IDENT-continuation so we don't slice a longer
        # identifier.
        if ch in "0123456789abcdefABCDEF":
            j = i
            while j < n and source[j] in "0123456789abcdefABCDEF":
                j += 1
            hex_run_len = j - i
            if hex_run_len == 40 and (
                j >= n or not _is_ident_continue(source[j])
            ):
                raw_hex = source[i:j]
                if any(c in "0123456789" for c in raw_hex):
                    toks.append(Token("ASSET_HASH", raw_hex, line, col))
                    col += (j - i)
                    i = j
                    continue
            # else: not an asset hash; fall through to NUMBER/IDENT paths

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

        # Identifier or keyword. Asset-hash promotion lives on the
        # digit-start path above (asset hashes are content-addressed hex,
        # randomly distributed — they start with a digit ~6/16 of the
        # time). Letter-start runs always produce IDENT, so a 40-char
        # all-hex-letter IDENT like `abcdefabcdef...` (legitimate
        # identifier) is NOT mis-promoted to ASSET_HASH.
        if _is_ident_start(ch):
            start_line, start_col = line, col
            j = i + 1
            while j < n and _is_ident_continue(source[j]):
                j += 1
            raw = source[i:j]
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
        py = _parse_number(t.value)
        # Normalize raw to the canonical `_fmt_number(py)` form so that
        # parse/emit round-trip is symmetric. Example: `1e2` parses to
        # `py=100.0`; without this normalization, `raw="1e2"` but
        # emitter writes "100", breaking the `parse(emit(doc)) == doc`
        # invariant on the Literal_ frozen-equality check.
        canonical_raw = _fmt_number(py)
        return Literal_(lit_kind="number", raw=canonical_raw, py=py)
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
    if kw.value not in _SIZING_KW:
        # Defensive: shouldn't reach here (caller gates on _SIZING_KW),
        # but raise a structured error rather than using `assert` so the
        # check survives `python -O`.
        raise DDMarkupParseError(
            f"expected sizing keyword (fill/hug/fixed), got `{kw.value}`",
            kind="KIND_BAD_SYNTAX", line=kw.line, col=kw.col,
        )
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
        # Normalize entry order per grammar §7.6 for round-trip equality.
        entries = _normalize_propgroup_entries(entries)
        return PropGroup(entries=tuple(entries))
    raise DDMarkupParseError(
        f"expected `.`, `}}`, or `=` inside brace value; got {c.peek().type} `{c.peek().value}`",
        kind="KIND_BAD_SYNTAX",
        line=c.peek().line, col=c.peek().col,
    )


# Canonical PropGroup entry ordering per grammar §7.6. Shared between
# the parse-time normalization (so `parse(emit(doc)) == doc`) and the
# emit-time serialization (so output is deterministic across two
# implementations). Single source of truth — keyed by the full
# `frozenset` of side-names belonging to the group.
_PROPGROUP_CANONICAL_ORDER: dict[frozenset[str], tuple[str, ...]] = {
    frozenset(("top", "right", "bottom", "left")):
        ("top", "right", "bottom", "left"),
    frozenset(("top-left", "top-right", "bottom-left", "bottom-right")):
        ("top-left", "top-right", "bottom-right", "bottom-left"),
    frozenset(("horizontal", "vertical")):
        ("horizontal", "vertical"),
    frozenset(("width", "height",
               "min-width", "max-width",
               "min-height", "max-height")):
        ("width", "height",
         "min-width", "max-width",
         "min-height", "max-height"),
}


def _normalize_propgroup_entries(
    entries: list[PropAssign],
) -> list[PropAssign]:
    """Sort PropGroup entries in canonical order per grammar §7.6.

    An entry set that is a SUBSET of any known group uses that group's
    canonical order (partial `padding={top=8 left=12}` still emits in
    t-r-b-l order). Entries belonging to no known group fall back to
    lex order.
    """
    keys = frozenset(e.key for e in entries)
    for key_set, order in _PROPGROUP_CANONICAL_ORDER.items():
        if keys and keys.issubset(key_set):
            pos = {k: i for i, k in enumerate(order)}
            return sorted(entries, key=lambda e: pos.get(e.key, 999))
    return sorted(entries, key=lambda e: e.key)


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
    """Strip quotes and apply escape sequences per grammar §2.5.

    Uses a single-pass decoder so that chained substitutions can't
    corrupt each other — `"\\\\n"` (backslash + `n`) must decode as
    `\\n`, not `\n`. Handles all spec'd escapes: `\\n \\t \\r \\" \\\\
    \\0` and `\\u{HHHH}` (unicode).
    """
    if raw.startswith('"""'):
        # Triple-quoted — strip quotes, apply Python-like dedent.
        # Escape sequences inside triple-quoted strings are NOT
        # processed (matches Python raw-string conventions for
        # multi-line literals).
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

    # Single-line — decode escape sequences in one pass
    body = raw[1:-1]
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            # Trailing backslash — treat as literal (lexer would have
            # caught a malformed string literal already)
            out.append("\\")
            i += 1
            continue
        nxt = body[i + 1]
        if nxt == "n":
            out.append("\n"); i += 2
        elif nxt == "t":
            out.append("\t"); i += 2
        elif nxt == "r":
            out.append("\r"); i += 2
        elif nxt == '"':
            out.append('"'); i += 2
        elif nxt == "\\":
            out.append("\\"); i += 2
        elif nxt == "0":
            out.append("\0"); i += 2
        elif nxt == "u":
            # \u{HHHH} — 1..6 hex digits inside braces
            if i + 2 < n and body[i + 2] == "{":
                end = body.find("}", i + 3)
                if end > i + 3:
                    hex_digits = body[i + 3:end]
                    if all(c in "0123456789abcdefABCDEF" for c in hex_digits):
                        try:
                            out.append(chr(int(hex_digits, 16)))
                            i = end + 1
                            continue
                        except (ValueError, OverflowError):
                            pass
            # Malformed \u — treat as literal `\u` (parser didn't flag it)
            out.append("\\u"); i += 2
        else:
            # Unknown escape — keep the backslash + char as-is (permissive)
            out.append("\\"); out.append(nxt); i += 2
    return "".join(out)


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

    # Normalize to canonical ordering per grammar §7.5 / §7.6.
    # Required for `parse(emit(doc)) == doc` round-trip (§3.5).
    uses_sorted = tuple(sorted(uses, key=lambda u: (u.alias, u.path)))
    tokens_sorted = tuple(sorted(tokens, key=lambda t: t.path))
    return ns, uses_sorted, tokens_sorted


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
    """Per grammar §2.2 — what tokens can start a new statement?

    Grammar §2.7 requires fail-open on unknown type keywords: any
    IDENT in statement position may be a not-yet-registered type
    keyword. Returning True for all IDENTs here preserves that
    fail-open behavior so a new-line IDENT correctly terminates
    the previous head instead of being parsed as a PropAssign.
    """
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

    head_kind: Literal["type", "comp-ref", "pattern-ref", "edit-ref"]
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
    elif t.type == "IDENT":
        # Grammar §2.7: "Parsers SHOULD warn on unknown type keywords
        # but MUST NOT hard-fail". Any IDENT in head position is
        # treated as a type keyword; the value may not be in the
        # compressor's `_TYPE_KEYWORDS` registry but downstream
        # passes / renderer fall back to a sensible default.
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
        # §2.7 fail-open: an IDENT on a new line that is NOT in the
        # type-keyword registry AND is NOT followed by `=` or `.`
        # (so not a property assignment) terminates the current head
        # — it's the start of a sibling node with an unknown type.
        is_unknown_type_statement = (
            nxt.type == "IDENT"
            and nxt.value not in _TYPE_KEYWORDS
            and c.peek(1).type not in ("EQ", "DOT")
            and c.pos != saved_pos
        )
        if is_unknown_type_statement:
            c.pos = saved_pos
            while c.peek().type == "EOL":
                c.advance()
            break
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

    # Normalize property order per grammar §7.5 so that
    # `parse(emit(doc)) == doc` regardless of source ordering.
    properties_sorted = sorted(
        properties,
        key=lambda p: _prop_rank(
            p.key if isinstance(p, PropAssign) else p.path
        ),
    )
    head = NodeHead(
        head_kind=head_kind,
        type_or_path=type_or_path,
        scope_alias=scope_alias,
        eid=eid,
        alias=alias,
        override_args=override_args,
        positional=positional,
        properties=tuple(properties_sorted),
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
            # SlotFill requires a NodeExpr on the RHS (type keyword / ->
            # / &). A TypeKeyword followed by LPAREN is a FunctionCall
            # (value), NOT a node head — `fill=image(asset=...)` where
            # `image` is both TypeKeyword and function name would
            # otherwise mis-dispatch as SlotFill.
            rhs_lookahead = c.peek(3)
            is_function_call_rhs = (
                rhs.type == "IDENT"
                and rhs.value in _TYPE_KEYWORDS
                and rhs_lookahead.type == "LPAREN"
            )
            is_node_rhs = (
                not is_function_call_rhs
                and (
                    (rhs.type == "IDENT" and rhs.value in _TYPE_KEYWORDS)
                    or rhs.type == "ARROW"
                    or rhs.type == "AMP"
                )
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
    #
    # Grammar §2.7: "Parsers SHOULD warn on unknown type keywords
    # but MUST NOT hard-fail". Unknown IDENTs at statement-start
    # position are therefore accepted as type keywords — the
    # resulting Node carries `type_or_path=<unknown>` and downstream
    # consumers (semantic passes / renderer / decompressor) can
    # choose to warn or dispatch-fall-through.
    if (
        t.type == "IDENT"
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
        elif nxt.type in ("STAR", "DSTAR"):
            # Wildcards are edit-only per §5.2.
            raise DDMarkupParseError(
                f"wildcard `{nxt.value}` is not allowed in a construction "
                f"`@eid` path (edit-verb context only)",
                kind="KIND_WILDCARD_IN_CONSTRUCT",
                line=at_tok.line, col=at_tok.col,
            )
        else:
            raise DDMarkupParseError(
                f"expected IDENT after `{sep_tok.value}`, got "
                f"{nxt.type} `{nxt.value}`",
                kind="KIND_BAD_PATH",
                line=nxt.line, col=nxt.col,
            )
    # Synthesize a Node with head_kind="edit-ref" (grammar §8) and the
    # path as the type_or_path. The edit-context semantic is preserved
    # by the discriminant — a future semantic analyzer / expansion pass
    # dispatches on `head_kind == "edit-ref"`. Replaces an earlier
    # `scope_alias="@"` sentinel that polluted the alias-tracking walk.
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
        head_kind="edit-ref",
        type_or_path=".".join(parts),
        scope_alias=None,
        properties=tuple(properties),
    )
    return Node(head=head, block=None)


# ---------------------------------------------------------------------------
# Edit-verb parsers (M7.1) — grammar §8.6
# ---------------------------------------------------------------------------
# Each parser consumes the verb keyword + arguments and returns the
# matching EditStatement subclass. Errors raise DDMarkupParseError
# with kind=KIND_BAD_EDIT_VERB.


_EDIT_VERBS = frozenset({
    "set", "delete", "append", "insert", "move", "swap", "replace",
})


def _parse_eref(c: _Cursor) -> ERef:
    """Parse an `@eid` / `@parent.child` / `@parent/child` reference
    into an ERef object. Wildcards (`*`, `**`) are recognised and the
    `has_wildcard` flag is set; the apply-engine rejects them in M7.1.
    """
    at_tok = c.expect("AT", kind="KIND_BAD_EDIT_VERB")
    first = c.peek()
    parts: list[str] = []
    has_wildcard = False
    if first.type == "IDENT":
        parts.append(first.value)
        c.advance()
    else:
        raise DDMarkupParseError(
            f"expected IDENT after `@`, got {first.type} `{first.value}`",
            kind="KIND_BAD_EDIT_VERB",
            line=at_tok.line, col=at_tok.col,
        )
    while c.peek().type in ("DOT", "SLASH"):
        sep_tok = c.advance()
        nxt = c.peek()
        if nxt.type == "IDENT":
            parts.append(nxt.value)
            c.advance()
        elif nxt.type in ("STAR", "DSTAR"):
            parts.append(nxt.value)
            has_wildcard = True
            c.advance()
        else:
            raise DDMarkupParseError(
                f"expected IDENT or wildcard after `{sep_tok.value}`, "
                f"got {nxt.type} `{nxt.value}`",
                kind="KIND_BAD_EDIT_VERB",
                line=nxt.line, col=nxt.col,
            )
    # Canonical join: dotted form. ERefs parsed from `@a/b` and
    # `@a.b` produce the same ERef; the emitter emits dotted form
    # consistently. Round-trip identity holds for dotted-input
    # fixtures (which is what we test in M7.1). Slash-form input
    # canonicalises on round-trip — documented in the assumption log.
    return ERef(
        path=".".join(parts),
        scope_alias=None,
        has_wildcard=has_wildcard,
    )


def _parse_property_list(c: _Cursor) -> tuple[object, ...]:
    """Parse zero-or-more `key=value` PropAssign / PathOverride
    entries until a statement-stopper token.

    Edit-context disambiguation differs from construction: in
    `set @card-1 text="New"`, the IDENT `text` is a property key,
    NOT a new TEXT node. We look ahead one token: if the next IDENT
    is followed by `=` (or `.`-then-IDENT-then-`=` for dotted
    paths), it's a property assignment; otherwise it ends the verb
    statement.
    """
    properties: list[object] = []
    c.skip_eols()
    while True:
        nxt = c.peek()
        if nxt.type in ("RBRACE", "EOF", "LBRACE"):
            break
        if nxt.type in ("ARROW", "AMP", "AT", "DOLLAR"):
            break
        if nxt.type == "IDENT":
            # Look ahead: walk a dotted path (IDENT (DOT IDENT)*) and
            # check if it ends in `=`. If yes, it's a property
            # assignment. If no, it's a new statement (or noise) and
            # we stop.
            i = 1
            while c.peek(i).type == "DOT" and c.peek(i + 1).type == "IDENT":
                i += 2
            if c.peek(i).type != "EQ":
                # IDENT not followed by `=` → end of properties.
                break
            key = _parse_dotted_or_single(c)
            c.expect("EQ", kind="KIND_BAD_EDIT_VERB")
            val = _parse_value(c)
            if "." in key:
                properties.append(PathOverride(path=key, value=val))
            else:
                properties.append(PropAssign(key=key, value=val))
            while c.peek().type == "EOL":
                c.advance()
            continue
        break
    return tuple(properties)


def _expect_kw(c: _Cursor, name: str, verb: str) -> Token:
    """Expect a bare IDENT with the given value (e.g., `to`, `into`,
    `with`, `position`) followed by `=`. Returns the IDENT token
    (callers usually only need its line/col for errors).
    """
    tok = c.peek()
    if tok.type != "IDENT" or tok.value != name:
        raise DDMarkupParseError(
            f"{verb} requires `{name}=` keyword arg",
            kind="KIND_BAD_EDIT_VERB",
            line=tok.line, col=tok.col,
        )
    c.advance()
    c.expect("EQ", kind="KIND_BAD_EDIT_VERB")
    return tok


def _parse_set_explicit(c: _Cursor) -> SetStatement:
    """`set @eid prop=val [prop=val ...]`."""
    set_tok = c.expect("IDENT", value="set", kind="KIND_BAD_EDIT_VERB")
    target = _parse_eref(c)
    props = _parse_property_list(c)
    if not props:
        raise DDMarkupParseError(
            "set statement requires at least one property assignment",
            kind="KIND_BAD_EDIT_VERB",
            line=set_tok.line, col=set_tok.col,
        )
    return SetStatement(
        target=target, properties=props,
        line=set_tok.line, col=set_tok.col, implicit=False,
    )


def _parse_implicit_set(c: _Cursor) -> SetStatement:
    """`@eid prop=val [prop=val ...]` — sugar for `set @eid ...`."""
    at_pos = c.peek()
    target = _parse_eref(c)
    props = _parse_property_list(c)
    if not props:
        raise DDMarkupParseError(
            "implicit set requires at least one property assignment",
            kind="KIND_BAD_EDIT_VERB",
            line=at_pos.line, col=at_pos.col,
        )
    return SetStatement(
        target=target, properties=props,
        line=at_pos.line, col=at_pos.col, implicit=True,
    )


def _parse_delete(c: _Cursor) -> DeleteStatement:
    """`delete @eid`."""
    del_tok = c.expect("IDENT", value="delete", kind="KIND_BAD_EDIT_VERB")
    nxt = c.peek()
    if nxt.type != "AT":
        raise DDMarkupParseError(
            "delete requires an @eid argument",
            kind="KIND_BAD_EDIT_VERB",
            line=del_tok.line, col=del_tok.col,
        )
    target = _parse_eref(c)
    return DeleteStatement(
        target=target, line=del_tok.line, col=del_tok.col,
    )


def _parse_append(c: _Cursor) -> AppendStatement:
    """`append to=@eid Block`."""
    app_tok = c.expect("IDENT", value="append", kind="KIND_BAD_EDIT_VERB")
    _expect_kw(c, "to", "append")
    to_eref = _parse_eref(c)
    c.skip_eols()
    if c.peek().type != "LBRACE":
        raise DDMarkupParseError(
            "append requires a block body `{ ... }`",
            kind="KIND_BAD_EDIT_VERB",
            line=app_tok.line, col=app_tok.col,
        )
    body = _parse_block(c)
    return AppendStatement(
        to=to_eref, body=body, line=app_tok.line, col=app_tok.col,
    )


def _parse_insert(c: _Cursor) -> InsertStatement:
    """`insert into=@eid (after=@eid | before=@eid) Block`."""
    ins_tok = c.expect("IDENT", value="insert", kind="KIND_BAD_EDIT_VERB")
    _expect_kw(c, "into", "insert")
    into_eref = _parse_eref(c)
    nxt = c.peek()
    if nxt.type == "IDENT" and nxt.value == "after":
        _expect_kw(c, "after", "insert")
        anchor = _parse_eref(c)
        anchor_rel: Literal["after", "before"] = "after"
    elif nxt.type == "IDENT" and nxt.value == "before":
        _expect_kw(c, "before", "insert")
        anchor = _parse_eref(c)
        anchor_rel = "before"
    else:
        raise DDMarkupParseError(
            "insert requires position anchor (`after=@eid` or "
            "`before=@eid`)",
            kind="KIND_BAD_EDIT_VERB",
            line=ins_tok.line, col=ins_tok.col,
        )
    c.skip_eols()
    if c.peek().type != "LBRACE":
        raise DDMarkupParseError(
            "insert requires a block body `{ ... }`",
            kind="KIND_BAD_EDIT_VERB",
            line=ins_tok.line, col=ins_tok.col,
        )
    body = _parse_block(c)
    return InsertStatement(
        into=into_eref, anchor=anchor, anchor_rel=anchor_rel,
        body=body, line=ins_tok.line, col=ins_tok.col,
    )


_MOVE_POSITION_VALUES = frozenset({"first", "last"})


def _parse_move(c: _Cursor) -> MoveStatement:
    """`move @eid to=@eid (position=first|last | after=@eid | before=@eid)?`."""
    mov_tok = c.expect("IDENT", value="move", kind="KIND_BAD_EDIT_VERB")
    target = _parse_eref(c)
    _expect_kw(c, "to", "move")
    to_eref = _parse_eref(c)
    nxt = c.peek()
    position: Literal["first", "last", "after", "before"] = "last"
    position_anchor: Optional[ERef] = None
    if nxt.type == "IDENT" and nxt.value == "position":
        _expect_kw(c, "position", "move")
        v_tok = c.expect("IDENT", kind="KIND_BAD_EDIT_VERB")
        if v_tok.value not in _MOVE_POSITION_VALUES:
            raise DDMarkupParseError(
                f"position must be `first` or `last` (got `{v_tok.value}`)",
                kind="KIND_BAD_EDIT_VERB",
                line=v_tok.line, col=v_tok.col,
            )
        position = v_tok.value  # type: ignore[assignment]
    elif nxt.type == "IDENT" and nxt.value == "after":
        _expect_kw(c, "after", "move")
        position_anchor = _parse_eref(c)
        position = "after"
    elif nxt.type == "IDENT" and nxt.value == "before":
        _expect_kw(c, "before", "move")
        position_anchor = _parse_eref(c)
        position = "before"
    return MoveStatement(
        target=target, to=to_eref,
        position=position, position_anchor=position_anchor,
        line=mov_tok.line, col=mov_tok.col,
    )


def _parse_swap(c: _Cursor) -> SwapStatement:
    """`swap @eid with=NodeExpr`."""
    sw_tok = c.expect("IDENT", value="swap", kind="KIND_BAD_EDIT_VERB")
    target = _parse_eref(c)
    nxt = c.peek()
    if nxt.type != "IDENT" or nxt.value != "with":
        raise DDMarkupParseError(
            "swap requires `with=<node-expr>` keyword arg",
            kind="KIND_BAD_EDIT_VERB",
            line=sw_tok.line, col=sw_tok.col,
        )
    _expect_kw(c, "with", "swap")
    with_node = _parse_node(c)
    return SwapStatement(
        target=target, with_node=with_node,
        line=sw_tok.line, col=sw_tok.col,
    )


def _parse_replace(c: _Cursor) -> ReplaceStatement:
    """`replace @eid Block`."""
    rep_tok = c.expect("IDENT", value="replace", kind="KIND_BAD_EDIT_VERB")
    target = _parse_eref(c)
    c.skip_eols()
    if c.peek().type != "LBRACE":
        raise DDMarkupParseError(
            "replace requires a block body `{ ... }`",
            kind="KIND_BAD_EDIT_VERB",
            line=rep_tok.line, col=rep_tok.col,
        )
    body = _parse_block(c)
    return ReplaceStatement(
        target=target, body=body,
        line=rep_tok.line, col=rep_tok.col,
    )


_EDIT_PARSERS = {
    "set": _parse_set_explicit,
    "delete": _parse_delete,
    "append": _parse_append,
    "insert": _parse_insert,
    "move": _parse_move,
    "swap": _parse_swap,
    "replace": _parse_replace,
}


def _parse_edit_statement(c: _Cursor) -> EditStatement:
    """Dispatch from the verb keyword to the per-verb parser."""
    tok = c.peek()
    if tok.type != "IDENT" or tok.value not in _EDIT_VERBS:
        raise DDMarkupParseError(
            f"expected edit verb, got {tok.type} `{tok.value}`",
            kind="KIND_BAD_EDIT_VERB",
            line=tok.line, col=tok.col,
        )
    return _EDIT_PARSERS[tok.value](c)


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
    """ScalarParam | SlotParam | OverrideParam per grammar §3 + §6.1.

    - ScalarParam: `name: type [= default]`
    - SlotParam:   `slot name [= NodeExpr]`
    - OverrideParam: `dotted.path = value` — declares a path-addressed
      override with a default; at call site the caller can override with
      `name.path = value`. The first dotted-path IDENT is the param's
      alias; the full path addresses an internal eid + property.
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

    # Could be ScalarParam (`name: type`) or OverrideParam (`a.b.c = val`).
    # Distinguish on what follows the first IDENT:
    #   - `:` → ScalarParam
    #   - `.` → OverrideParam (dotted path)
    #   - `=` → OverrideParam (single-segment path, rare)
    first = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
    if c.peek().type == "DOT" or (
        c.peek().type == "EQ" and c.peek(1).type != "COLON"
    ):
        # OverrideParam — accumulate the full dotted path
        path_parts = [first.value]
        while c.peek().type == "DOT":
            c.advance()
            seg = c.expect("IDENT", kind="KIND_BAD_PATH")
            path_parts.append(seg.value)
        c.expect("EQ", kind="KIND_BAD_SYNTAX")
        default_val: Optional[Value] = _parse_value(c)
        return Param(
            param_kind="override",
            name=".".join(path_parts),
            type_hint=None,
            default=default_val,
        )

    # ScalarParam — `name: type [= default]`
    c.expect("COLON", kind="KIND_BAD_SYNTAX")
    type_hint_tok = c.expect("IDENT", kind="KIND_BAD_SYNTAX")
    type_hint = type_hint_tok.value
    default2: Optional[Value] = None
    if c.peek().type == "EQ":
        c.advance()
        default2 = _parse_value(c)
    return Param(
        param_kind="scalar",
        name=first.value,
        type_hint=type_hint,
        default=default2,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_l3(source: str, *, source_path: Optional[str] = None) -> L3Document:
    """Parse a dd markup source file and return its L3Document.

    Stage 1.2 scope (slices A–I + semantic):
    - Full grammar (preamble, top-level nodes/defines, all value forms,
      trailers, pattern refs, slot fills/placeholders, path overrides,
      `$ext.*`, edit-context `@eid`)
    - Semantic passes enforcing the KIND catalog in §9.5:
      * KIND_DUPLICATE_EID (per-scope eid collision)
      * KIND_UNKNOWN_FUNCTION (closed function-name set)
      * KIND_AMBIGUOUS_PARAM (scalar-arg name clashes with internal eid
        inside the same define body)
      * KIND_SLOT_MISSING (pattern-ref call omits a required slot)
      * KIND_CIRCULAR_DEFINE (three-color DFS on the define graph)
      * KIND_CIRCULAR_TOKEN (topo sort on tokens block references)
      * KIND_UNRESOLVED_REF (token / param lookup miss)
    """
    toks = tokenize(source)
    c = _Cursor(toks)

    ns, uses, tokens_tuple = _parse_preamble(c)

    top_level: list[object] = []
    edits: list[object] = []
    warnings: list[Warning] = []

    c.skip_eols()
    while c.peek().type != "EOF":
        t = c.peek()
        if t.type == "IDENT" and t.value == "define":
            top_level.append(_parse_define(c))
        elif t.type == "IDENT" and t.value in _EDIT_VERBS:
            # Verb-statement at top level — M7.1 grammar §8.6.
            edits.append(_parse_edit_statement(c))
        elif t.type == "AT":
            # Implicit-set form `@eid prop=val` (§8.2 sugar).
            edits.append(_parse_implicit_set(c))
        else:
            top_level.append(_parse_node(c))
        c.skip_eols()

    # -----------------------------------------------------------------------
    # Semantic passes — hard-errors are raised inline, warnings are
    # collected. Ordering matters: pass earlier checks before later ones
    # that depend on a valid AST (e.g., cycle detection before slot
    # expansion).
    # -----------------------------------------------------------------------

    # 1. Per-node eid uniqueness (scope = direct-parent Block)
    _check_duplicate_eids(top_level)

    # 2. Closed function-name set
    _check_function_names(top_level, tokens_tuple)

    # 3. Cycle detection in `define` graph
    _check_define_cycles(top_level)

    # 4. Cycle detection in `tokens { }` self-references
    _check_token_cycles(tokens_tuple)

    # 5. Define-time ambiguous-param check — produces warnings rather
    # than hard errors (hard-error only fires at call site when the
    # disambiguation actually fails).
    warnings.extend(_check_ambiguous_params(top_level))

    # 6. Call-site slot-missing check
    _check_slot_missing(top_level)

    # 7. Token-ref resolution
    _check_unresolved_refs(top_level, tokens_tuple, uses)

    # 8. `KIND_UNUSED_IMPORT` warnings (non-fatal)
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
        edits=tuple(edits),
        warnings=tuple(warnings),
        source_path=source_path,
    )


# ---------------------------------------------------------------------------
# Semantic passes
# ---------------------------------------------------------------------------


# Closed set per grammar §4.3.
_KNOWN_FUNCTIONS = frozenset((
    "gradient-linear", "gradient-radial", "image", "rgba", "shadow",
))


def _iter_nodes(items: object):
    """Recursively yield every Node found in the AST."""
    if items is None:
        return
    if isinstance(items, (list, tuple)):
        for it in items:
            yield from _iter_nodes(it)
        return
    if isinstance(items, Node):
        yield items
        if items.block is not None:
            yield from _iter_nodes(items.block.statements)
        return
    if isinstance(items, Define):
        for p in items.params:
            yield from _iter_nodes(p.default)
        if items.body is not None:
            yield from _iter_nodes(items.body.statements)
        return
    if isinstance(items, SlotFill):
        yield from _iter_nodes(items.node)
        return
    # Values that can contain nodes
    if isinstance(items, (ComponentRefValue, PatternRefValue)):
        return


def _iter_function_calls(v: Value):
    """Recursively yield every FunctionCall inside a value tree."""
    if v is None:
        return
    if isinstance(v, FunctionCall):
        yield v
        for a in v.args:
            yield from _iter_function_calls(a.value)
        return
    if isinstance(v, PropGroup):
        for e in v.entries:
            yield from _iter_function_calls(e.value)
        return
    if isinstance(v, Node):
        # Node as a slot-default value — walk its properties too
        for p in v.head.properties:
            if isinstance(p, PropAssign):
                yield from _iter_function_calls(p.value)
        return


def _check_duplicate_eids(top_level: list[object]) -> None:
    """Grammar §5.1 — duplicate `#eid` within a scope is KIND_DUPLICATE_EID.

    Scope is the enclosing Block (or the document root). Walks every
    Block — including SlotFill nodes' own eids (not just their child
    blocks) and slot-default NodeExpr trees — so collisions in the full
    AST are caught.
    """
    def check_block(block: Optional[Block]) -> None:
        if block is None:
            return
        seen: dict[str, Node] = {}
        for stmt in block.statements:
            if isinstance(stmt, Node):
                if stmt.head.eid:
                    if stmt.head.eid in seen:
                        raise DDMarkupParseError(
                            f"duplicate `#{stmt.head.eid}` in this scope",
                            kind="KIND_DUPLICATE_EID",
                            eid=stmt.head.eid,
                        )
                    seen[stmt.head.eid] = stmt
                check_block(stmt.block)
            elif isinstance(stmt, SlotFill):
                # SlotFill node is a sibling in the same scope — its
                # head eid counts toward the enclosing scope's tally.
                node = stmt.node
                if node.head.eid:
                    if node.head.eid in seen:
                        raise DDMarkupParseError(
                            f"duplicate `#{node.head.eid}` in this scope "
                            f"(slot-fill `{stmt.slot_name}` collides)",
                            kind="KIND_DUPLICATE_EID",
                            eid=node.head.eid,
                        )
                    seen[node.head.eid] = node
                check_block(node.block)

    def check_slot_defaults(params: tuple[Param, ...]) -> None:
        """Walk slot-default NodeExpr trees — their internal eids
        count toward the enclosing Define's scope."""
        for p in params:
            if p.param_kind == "slot" and isinstance(p.default, Node):
                # The default's head eid is in a separate scope (the
                # slot-default site), not the define body, so we only
                # recurse into the default's child blocks.
                check_block(p.default.block)

    # Document-root scope
    root_seen: dict[str, Node] = {}
    for item in top_level:
        if isinstance(item, Node):
            if item.head.eid:
                if item.head.eid in root_seen:
                    raise DDMarkupParseError(
                        f"duplicate `#{item.head.eid}` at document root",
                        kind="KIND_DUPLICATE_EID",
                        eid=item.head.eid,
                    )
                root_seen[item.head.eid] = item
            check_block(item.block)
        elif isinstance(item, Define):
            check_slot_defaults(item.params)
            if item.body is not None:
                check_block(item.body)


def _check_function_names(
    top_level: list[object],
    tokens: tuple[TokenAssign, ...],
) -> None:
    """Grammar §4.3 — FunctionCall with unknown name is KIND_UNKNOWN_FUNCTION.

    Scans every value-position occurrence of FunctionCall, including
    inside CompRef `override_args` (inline `-> comp(key=val)` form),
    ValueTrailer attr values, NodeTrailer attr values, and slot-default
    NodeExpr subtrees.
    """
    def scan_value(v: Value) -> None:
        for fc in _iter_function_calls(v):
            if fc.name not in _KNOWN_FUNCTIONS:
                raise DDMarkupParseError(
                    f"unknown function `{fc.name}`; "
                    f"valid: {sorted(_KNOWN_FUNCTIONS)}",
                    kind="KIND_UNKNOWN_FUNCTION",
                )

    def scan_trailer_attrs(attrs: tuple[tuple[str, Value], ...]) -> None:
        for _, val in attrs:
            scan_value(val)

    def scan_node(node: Node) -> None:
        # Node-head properties, override_args, positional, trailer
        for p in node.head.properties:
            if isinstance(p, PropAssign):
                scan_value(p.value)
                if p.trailer:
                    scan_trailer_attrs(p.trailer.attrs)
            elif isinstance(p, PathOverride):
                scan_value(p.value)
        for a in node.head.override_args:
            scan_value(a.value)
        if node.head.positional is not None:
            scan_value(node.head.positional)
        if node.head.trailer is not None:
            scan_trailer_attrs(node.head.trailer.attrs)
        # Block body
        if node.block is not None:
            for stmt in node.block.statements:
                if isinstance(stmt, Node):
                    scan_node(stmt)
                elif isinstance(stmt, PropAssign):
                    scan_value(stmt.value)
                    if stmt.trailer:
                        scan_trailer_attrs(stmt.trailer.attrs)
                elif isinstance(stmt, PathOverride):
                    scan_value(stmt.value)
                elif isinstance(stmt, SlotFill):
                    scan_node(stmt.node)

    for ta in tokens:
        scan_value(ta.value)
    for item in top_level:
        if isinstance(item, Node):
            scan_node(item)
        elif isinstance(item, Define):
            for p in item.params:
                if p.default is not None:
                    if isinstance(p.default, Node):
                        scan_node(p.default)
                    else:
                        scan_value(p.default)
            if item.body is not None:
                for stmt in item.body.statements:
                    if isinstance(stmt, Node):
                        scan_node(stmt)
                    elif isinstance(stmt, PropAssign):
                        scan_value(stmt.value)
                    elif isinstance(stmt, PathOverride):
                        scan_value(stmt.value)
                    elif isinstance(stmt, SlotFill):
                        scan_node(stmt.node)


def _check_define_cycles(top_level: list[object]) -> None:
    """Grammar §6.3 — three-color DFS on the define reference graph."""
    defines: dict[str, Define] = {
        d.name: d for d in top_level if isinstance(d, Define)
    }

    def refs_in_define(d: Define) -> list[str]:
        """Return every `& name` target inside `d`'s body or slot defaults."""
        refs: list[str] = []
        for p in d.params:
            if p.param_kind == "slot" and p.default is not None:
                _collect_pattern_refs(p.default, refs)
        if d.body is not None:
            for stmt in d.body.statements:
                _collect_pattern_refs(stmt, refs)
        return refs

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {name: WHITE for name in defines}

    def dfs(name: str) -> None:
        color[name] = GRAY
        for target in refs_in_define(defines[name]):
            if target not in defines:
                continue                         # external ref (via alias)
            if color[target] == GRAY:
                raise DDMarkupParseError(
                    f"circular define reference involving `{name}` → `{target}`",
                    kind="KIND_CIRCULAR_DEFINE",
                )
            if color[target] == WHITE:
                dfs(target)
        color[name] = BLACK

    for name in defines:
        if color[name] == WHITE:
            dfs(name)


def _collect_pattern_refs(item: object, out: list[str]) -> None:
    if item is None:
        return
    if isinstance(item, PatternRefValue):
        out.append(item.path)
    if isinstance(item, Node):
        if item.head.head_kind == "pattern-ref":
            out.append(item.head.type_or_path)
        if item.block is not None:
            for s in item.block.statements:
                _collect_pattern_refs(s, out)
    if isinstance(item, SlotFill):
        _collect_pattern_refs(item.node, out)


def _check_token_cycles(tokens: tuple[TokenAssign, ...]) -> None:
    """L0↔L3 §2.10 — tokens block self-reference cycle detection."""
    graph: dict[str, list[str]] = {}
    for ta in tokens:
        graph[ta.path] = _token_value_refs(ta.value)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {k: WHITE for k in graph}

    def dfs(node: str) -> None:
        color[node] = GRAY
        for ref in graph.get(node, ()):
            if ref not in graph:
                continue                          # external / universal
            if color[ref] == GRAY:
                raise DDMarkupParseError(
                    f"circular token reference: `{node}` → `{ref}`",
                    kind="KIND_CIRCULAR_TOKEN",
                )
            if color[ref] == WHITE:
                dfs(ref)
        color[node] = BLACK

    for k in graph:
        if color[k] == WHITE:
            dfs(k)


def _token_value_refs(v: Value) -> list[str]:
    refs: list[str] = []
    if isinstance(v, TokenRef):
        # Only same-document refs (no scope alias)
        if v.scope_alias is None:
            refs.append(v.path)
    elif isinstance(v, FunctionCall):
        for a in v.args:
            refs.extend(_token_value_refs(a.value))
    elif isinstance(v, PropGroup):
        for e in v.entries:
            refs.extend(_token_value_refs(e.value))
    return refs


def _check_ambiguous_params(top_level: list[object]) -> list[Warning]:
    """Grammar Q3 — scalar-arg name collision with internal eid inside
    the same define body produces KIND_AMBIGUOUS_PARAM.

    Implementation note: the strict check would fire at call site when
    `name=X` could bind either to the scalar-arg OR to a path-override
    targeting the internal eid. Since bare `name=X` (no dot) is always
    a scalar-arg fill (§3.2 disambiguation), the AMBIGUITY only arises
    if a call site uses path-addressing syntax. That's a RUNTIME
    disambiguation, not a parse-time one — defer to Stage 4 pattern
    expansion.

    At parse time we emit a non-fatal warning so authors who introduce
    this collision see it surfaced, without blocking the fixture
    authoring patterns (fixture 01's `option-row(title: text, ... #title)`
    is a legitimate convention).
    """
    warnings: list[Warning] = []
    for item in top_level:
        if not isinstance(item, Define):
            continue
        scalar_names = {
            p.name for p in item.params if p.param_kind == "scalar"
        }
        internal_eids: set[str] = set()
        if item.body is not None:
            _collect_eids(item.body.statements, internal_eids)
        for p in item.params:
            if p.default is not None:
                _collect_eids((p.default,), internal_eids)
        collision = scalar_names & internal_eids
        for name in sorted(collision):
            warnings.append(Warning(
                kind="KIND_AMBIGUOUS_PARAM",
                message=(
                    f"in define `{item.name}`, scalar param `{name}` "
                    f"collides with internal `#{name}` eid; at call site "
                    f"use `{name}=X` for scalar fill, `{name}.prop=X` "
                    f"for path override"
                ),
            ))
    return warnings


def _collect_eids(items: object, out: set[str]) -> None:
    if items is None:
        return
    if isinstance(items, (list, tuple)):
        for it in items:
            _collect_eids(it, out)
        return
    if isinstance(items, Node):
        if items.head.eid:
            out.add(items.head.eid)
        if items.block is not None:
            _collect_eids(items.block.statements, out)
    elif isinstance(items, SlotFill):
        _collect_eids(items.node, out)


def _check_slot_missing(top_level: list[object]) -> None:
    """Grammar §6.1 — pattern-ref call must fill every required slot.

    Only same-file pattern refs are checked (cross-file `alias::name`
    are deferred — the resolver phase handles external lookups).
    Walks slot-default NodeExpr trees too, so nested pattern refs
    inside a define's slot defaults are validated.
    """
    defines: dict[str, Define] = {
        d.name: d for d in top_level if isinstance(d, Define)
    }

    def check(node: object) -> None:
        if isinstance(node, SlotFill):
            check(node.node)
            return
        if not isinstance(node, Node):
            return
        if node.head.head_kind == "pattern-ref" and not node.head.scope_alias:
            target = defines.get(node.head.type_or_path)
            if target:
                required_slots = {
                    p.name for p in target.params
                    if p.param_kind == "slot" and p.default is None
                }
                filled = _slot_fills(node)
                missing = required_slots - filled
                if missing:
                    name = sorted(missing)[0]
                    raise DDMarkupParseError(
                        f"pattern-ref `& {target.name}` is missing "
                        f"required slot `{name}`",
                        kind="KIND_SLOT_MISSING",
                    )
        if node.block is not None:
            for s in node.block.statements:
                check(s)

    for item in top_level:
        check(item)
        if isinstance(item, Define):
            # Walk slot defaults — nested pattern-ref calls inside
            # defaults must also satisfy their targets' required slots.
            for p in item.params:
                if p.param_kind == "slot" and isinstance(p.default, Node):
                    check(p.default)
            if item.body is not None:
                for s in item.body.statements:
                    check(s)


def _slot_fills(pattern_ref_node: Node) -> set[str]:
    """Return the set of slot names filled at a pattern-ref call site."""
    filled: set[str] = set()
    # Scalar args passed via property-assign on the ref head are NOT slot
    # fills — they're arg substitutions. Only SlotFill statements count.
    if pattern_ref_node.block is not None:
        for s in pattern_ref_node.block.statements:
            if isinstance(s, SlotFill):
                filled.add(s.slot_name)
    return filled


def _check_unresolved_refs(
    top_level: list[object],
    tokens: tuple[TokenAssign, ...],
    uses: tuple[UseDecl, ...],
) -> None:
    """Grammar §4.2 — `{path}` must resolve via the scope chain.

    Resolution order:
    1. Enclosing-define param scope (for scalar args)
    2. Top-level `tokens { }` block
    3. Imported tokens (via `use` alias) — deferred: can't load other
       files at parse time, so alias-qualified refs are accepted as
       "external" and deferred to expansion phase (Stage 4+)
    4. Universal catalog (shadcn defaults) — heuristic match
    5. Unresolved → KIND_UNRESOLVED_REF

    This pass does a CONSERVATIVE check: it errors only when a same-file
    `{path}` ref has no match in any of (1)–(4). Cross-alias refs are
    not checked here.
    """
    local_tokens = {ta.path for ta in tokens}
    alias_set = {u.alias for u in uses}

    def scan(v: Value, scalar_params: set[str]) -> None:
        if isinstance(v, TokenRef):
            if v.scope_alias is not None:
                # Cross-alias ref — defer to expansion phase
                return
            # Try: scalar-param scope → local tokens → universal prefix.
            # Scalar-param matching handles three cases:
            #   1. Exact path match: `{title}` resolves to scalar param `title`
            #   2. Dotted-prefix match: `{card.fill}` resolves to override
            #      param `card.fill` (full path as its name)
            #   3. First-segment match: `{title.text}` where `title` is a
            #      scalar-arg param whose value is itself a struct
            first_seg = v.path.split(".", 1)[0]
            if v.path in scalar_params:
                return                       # exact-match override param
            if first_seg in scalar_params:
                return                       # scalar param or sub-path
            if v.path in local_tokens:
                return
            if _matches_universal_prefix(v.path):
                return                       # universal-catalog default
            raise DDMarkupParseError(
                f"unresolved token reference `{{{v.path}}}`",
                kind="KIND_UNRESOLVED_REF",
            )
        if isinstance(v, FunctionCall):
            for a in v.args:
                scan(a.value, scalar_params)
        elif isinstance(v, PropGroup):
            for e in v.entries:
                scan(e.value, scalar_params)
        elif isinstance(v, Node):
            scan_node(v, scalar_params)
        # Literals and other value forms need no resolution

    def scan_node(node: Node, scalar_params: set[str]) -> None:
        if node.head.positional is not None:
            scan(node.head.positional, scalar_params)
        for p in node.head.properties:
            if isinstance(p, PropAssign):
                scan(p.value, scalar_params)
                if p.trailer:
                    for _, tv in p.trailer.attrs:
                        scan(tv, scalar_params)
            elif isinstance(p, PathOverride):
                scan(p.value, scalar_params)
        if node.head.trailer is not None:
            for _, tv in node.head.trailer.attrs:
                scan(tv, scalar_params)
        for a in node.head.override_args:
            scan(a.value, scalar_params)
        if node.block is not None:
            for s in node.block.statements:
                if isinstance(s, Node):
                    scan_node(s, scalar_params)
                elif isinstance(s, PropAssign):
                    scan(s.value, scalar_params)
                elif isinstance(s, PathOverride):
                    scan(s.value, scalar_params)
                elif isinstance(s, SlotFill):
                    scan_node(s.node, scalar_params)

    # Token-block values resolve against themselves + universal fallback
    for ta in tokens:
        scan(ta.value, scalar_params=set())

    # Walk nodes / defines
    for item in top_level:
        if isinstance(item, Define):
            param_names = {p.name for p in item.params}
            for p in item.params:
                if p.default is not None:
                    if isinstance(p.default, Node):
                        scan_node(p.default, param_names)
                    else:
                        scan(p.default, param_names)
            if item.body is not None:
                for s in item.body.statements:
                    if isinstance(s, Node):
                        scan_node(s, param_names)
        elif isinstance(item, Node):
            scan_node(item, scalar_params=set())


def _load_universal_tokens() -> frozenset[str]:
    """Load the keys of `_UNIVERSAL_MODE3_TOKENS` from `dd/compose.py`
    as the source of truth for step-4 of the resolution order (§4.2).

    Loaded lazily + cached so parse-time imports stay cheap. On import
    failure (e.g., compose.py not available), returns an empty set,
    which means every un-tokened ref raises KIND_UNRESOLVED_REF. That's
    the correct fail-closed behavior for a self-contained document.
    """
    try:
        from dd.compose import _UNIVERSAL_MODE3_TOKENS   # type: ignore
        return frozenset(_UNIVERSAL_MODE3_TOKENS.keys())
    except Exception:
        return frozenset()


_UNIVERSAL_CATALOG_KEYS: Optional[frozenset[str]] = None


def _matches_universal_prefix(path: str) -> bool:
    """Exact match against the universal catalog's token paths.

    Renamed for historical reasons; the check is now exact-path-match,
    not prefix-match, so that misspellings or paths with the right
    prefix but no matching entry do fire KIND_UNRESOLVED_REF.
    """
    global _UNIVERSAL_CATALOG_KEYS
    if _UNIVERSAL_CATALOG_KEYS is None:
        _UNIVERSAL_CATALOG_KEYS = _load_universal_tokens()
    return path in _UNIVERSAL_CATALOG_KEYS


def _collect_scope_aliases(items: object, out: set[str]) -> None:
    """Walk the AST by TYPE (not attribute-name strings) and collect
    every `scope_alias` use site. Replaces an earlier generic `getattr`
    walk that silently drifted when new AST node types were added.

    This visitor is the single source of truth for "where can a scope
    alias appear in an AST?" — update it (not the `_UNUSED_IMPORT`
    check) when new AST types gain scope-alias-bearing fields.
    """
    if items is None:
        return
    if isinstance(items, (list, tuple)):
        for it in items:
            _collect_scope_aliases(it, out)
        return

    # Dispatch by type — one arm per AST node. Missing a type produces
    # a silent skip, which is correct for leaf literals.
    if isinstance(items, L3Document):
        _collect_scope_aliases(items.top_level, out)
        _collect_scope_aliases(items.tokens, out)
        return
    if isinstance(items, TokenAssign):
        _collect_scope_aliases(items.value, out)
        return
    if isinstance(items, Define):
        _collect_scope_aliases(items.params, out)
        if items.body is not None:
            _collect_scope_aliases(items.body, out)
        return
    if isinstance(items, Param):
        _collect_scope_aliases(items.default, out)
        return
    if isinstance(items, Block):
        _collect_scope_aliases(items.statements, out)
        return
    if isinstance(items, Node):
        _collect_scope_aliases(items.head, out)
        _collect_scope_aliases(items.block, out)
        return
    if isinstance(items, NodeHead):
        if items.scope_alias:
            out.add(items.scope_alias)
        _collect_scope_aliases(items.positional, out)
        _collect_scope_aliases(items.override_args, out)
        _collect_scope_aliases(items.properties, out)
        _collect_scope_aliases(items.trailer, out)
        return
    if isinstance(items, PropAssign):
        _collect_scope_aliases(items.value, out)
        _collect_scope_aliases(items.trailer, out)
        return
    if isinstance(items, PathOverride):
        _collect_scope_aliases(items.value, out)
        return
    if isinstance(items, SlotFill):
        _collect_scope_aliases(items.node, out)
        return
    if isinstance(items, SlotPlaceholder):
        return
    if isinstance(items, TokenRef):
        if items.scope_alias:
            out.add(items.scope_alias)
        return
    if isinstance(items, ComponentRefValue):
        if items.scope_alias:
            out.add(items.scope_alias)
        _collect_scope_aliases(items.override_args, out)
        return
    if isinstance(items, PatternRefValue):
        if items.scope_alias:
            out.add(items.scope_alias)
        return
    if isinstance(items, FunctionCall):
        for a in items.args:
            _collect_scope_aliases(a.value, out)
        return
    if isinstance(items, PropGroup):
        _collect_scope_aliases(items.entries, out)
        return
    if isinstance(items, (NodeTrailer, ValueTrailer)):
        for _, v in items.attrs:
            _collect_scope_aliases(v, out)
        return
    # Literal_, SizingValue — leaves, no scope aliases.


def emit_l3(doc: L3Document) -> str:
    """Emit dd markup text for an L3Document.

    Deterministic: same input produces byte-identical output across
    runs. Idempotent through reparse: `parse_l3(emit_l3(doc)) == doc`.

    Canonical ordering:
    - Preamble: `namespace` (if present), then `use` in alias-lex
      order, then `tokens` block with token-path-lex ordering.
    - Top-level: items in source order (defines + nodes).
    - Node properties: structural → content → spatial → visual →
      extension → override → trailer ordering per grammar §7.5.
    - PropGroup entries: well-known groups (padding, radius, etc.)
      use their canonical side order per §7.6; unknown keys lex-sorted.
    """
    out = _Emitter()
    return out.emit_document(doc)


# ---------------------------------------------------------------------------
# Emitter — grammar §7.5 / §7.6 canonical ordering
# ---------------------------------------------------------------------------


# Grammar §7.5 — property-key ordering within a node. Lower index = earlier
# in the emission. Unknown keys fall back to lex order AFTER the enumerated.
_PROP_ORDER_STRUCTURAL = (
    "variant", "role", "as",
)
_PROP_ORDER_CONTENT = (
    "text", "label", "placeholder", "content", "value", "min", "max",
)
_PROP_ORDER_SPATIAL = (
    "x", "y", "width", "height",
    "min-width", "max-width", "min-height", "max-height",
    "rotation", "mirror",
    "layout", "gap", "padding",
    "mainAxis", "crossAxis", "align", "constraints",
)
_PROP_ORDER_VISUAL = (
    "fill", "fills", "stroke", "strokes", "stroke-weight",
    "effects", "shadow", "radius", "opacity", "blend", "visible",
    "font", "size", "weight", "color",
    "line-height", "letter-spacing",
)


def _prop_rank(key: str) -> tuple[int, str]:
    """Return a (block, key) sort tuple for canonical emission order."""
    # Strip $ext prefix for ordering decision
    if key.startswith("$ext."):
        return (4, key)                         # extension metadata last
    if "." in key:
        return (5, key)                         # path-overrides after ext
    for idx, bucket in enumerate((
        _PROP_ORDER_STRUCTURAL, _PROP_ORDER_CONTENT,
        _PROP_ORDER_SPATIAL, _PROP_ORDER_VISUAL,
    )):
        if key in bucket:
            return (idx, f"{bucket.index(key):04d}")
    # Unknown: after the recognized bucket but before ext/overrides
    return (3, "~" + key)


# Emitter-side table retained for name-keyed lookups in `_emit_propgroup`
# that need to match by PARENT PROPERTY NAME (e.g., `padding={...}` → order
# by `"padding"` key). The entries map to the same canonical tuples as
# `_PROPGROUP_CANONICAL_ORDER`; the two tables are consistent by
# construction (same right-hand sides).
_PROPGROUP_SIDE_ORDER = {
    "padding":      ("top", "right", "bottom", "left"),
    "radius":       ("top-left", "top-right", "bottom-right", "bottom-left"),
    "constraints":  ("horizontal", "vertical"),
    "sizing":       ("width", "height",
                     "min-width", "max-width",
                     "min-height", "max-height"),
}


class _Emitter:
    INDENT = "  "

    def __init__(self) -> None:
        self.out: list[str] = []

    def emit_document(self, doc: L3Document) -> str:
        if doc.namespace:
            self.out.append(f"namespace {doc.namespace}\n")
            self.out.append("\n")
        if doc.uses:
            for u in sorted(doc.uses, key=lambda u: (u.alias, u.path)):
                self.out.append(f'use "{u.path}" as {u.alias}\n')
            self.out.append("\n")
        if doc.tokens:
            self.out.append("tokens {\n")
            for ta in sorted(doc.tokens, key=lambda t: t.path):
                self.out.append(
                    self.INDENT + f"{ta.path} = {self.emit_value(ta.value)}\n"
                )
            self.out.append("}\n")
            self.out.append("\n")

        for i, item in enumerate(doc.top_level):
            if i > 0:
                self.out.append("\n")
            if isinstance(item, Define):
                self.emit_define(item, depth=0)
            elif isinstance(item, Node):
                self.emit_node(item, depth=0)
            else:
                raise DDMarkupSerializeError(
                    f"unknown top-level item type: {type(item).__name__}",
                    path="top_level",
                )

        # Edit statements emit as a separate section after the
        # construction tree, separated by a blank line. Per-edit
        # emission is one statement per logical block.
        if doc.edits:
            if doc.top_level:
                self.out.append("\n")
            for i, stmt in enumerate(doc.edits):
                if i > 0:
                    self.out.append("\n")
                self.emit_edit_statement(stmt, depth=0)

        return "".join(self.out)

    def emit_edit_statement(self, stmt: object, *, depth: int) -> None:
        """Dispatch to the per-verb emitter."""
        ind = self.INDENT * depth
        if isinstance(stmt, SetStatement):
            if stmt.implicit:
                head = f"{ind}@{stmt.target.path}"
            else:
                head = f"{ind}set @{stmt.target.path}"
            self.out.append(head)
            self._emit_props_inline(stmt.properties)
            self.out.append("\n")
        elif isinstance(stmt, DeleteStatement):
            self.out.append(f"{ind}delete @{stmt.target.path}\n")
        elif isinstance(stmt, AppendStatement):
            self.out.append(f"{ind}append to=@{stmt.to.path} ")
            self.emit_block(stmt.body, depth=depth)
        elif isinstance(stmt, InsertStatement):
            self.out.append(
                f"{ind}insert into=@{stmt.into.path} "
                f"{stmt.anchor_rel}=@{stmt.anchor.path} "
            )
            self.emit_block(stmt.body, depth=depth)
        elif isinstance(stmt, MoveStatement):
            head = f"{ind}move @{stmt.target.path} to=@{stmt.to.path}"
            if stmt.position in ("first", "last"):
                head += f" position={stmt.position}"
            elif stmt.position in ("after", "before") and stmt.position_anchor is not None:
                head += f" {stmt.position}=@{stmt.position_anchor.path}"
            self.out.append(head + "\n")
        elif isinstance(stmt, SwapStatement):
            self.out.append(f"{ind}swap @{stmt.target.path} with=")
            self.out.append(self._emit_node_inline(stmt.with_node))
            self.out.append("\n")
        elif isinstance(stmt, ReplaceStatement):
            self.out.append(f"{ind}replace @{stmt.target.path} ")
            self.emit_block(stmt.body, depth=depth)
        else:
            raise DDMarkupSerializeError(
                f"unknown edit-statement type: {type(stmt).__name__}",
                path="edits",
            )

    def _emit_props_inline(self, props: tuple[object, ...]) -> None:
        """Emit a list of PropAssign / PathOverride entries inline on
        the current line, space-separated. Used by SetStatement.
        """
        for p in props:
            if isinstance(p, PropAssign):
                self.out.append(f" {p.key}={self.emit_value(p.value)}")
            elif isinstance(p, PathOverride):
                self.out.append(f" {p.path}={self.emit_value(p.value)}")

    def emit_define(self, d: Define, *, depth: int) -> None:
        ind = self.INDENT * depth
        params_str = self._emit_params(d.params)
        if params_str:
            self.out.append(f"{ind}define {d.name}({params_str}) ")
        else:
            self.out.append(f"{ind}define {d.name}() ")
        if d.body is not None:
            self.emit_block(d.body, depth=depth)
        else:
            self.out.append("{}\n")

    def _emit_params(self, params: tuple[Param, ...]) -> str:
        if not params:
            return ""
        multi = len(params) > 2 or any(
            isinstance(p.default, Node) for p in params
        )
        sep = ",\n  " if multi else ", "
        inner: list[str] = []
        for p in params:
            if p.param_kind == "slot":
                s = f"slot {p.name}"
                if p.default is not None:
                    if isinstance(p.default, Node):
                        # Inline slot-default-as-node: CompRef form
                        s += " = " + self._emit_node_inline(p.default)
                    else:
                        s += f" = {self.emit_value(p.default)}"
                inner.append(s)
            else:
                s = f"{p.name}: {p.type_hint or 'text'}"
                if p.default is not None:
                    s += f" = {self.emit_value(p.default)}"
                inner.append(s)
        if multi:
            return "\n  " + sep.join(inner) + ",\n"
        return sep.join(inner)

    def emit_node(self, node: Node, *, depth: int) -> None:
        ind = self.INDENT * depth
        head_text = self._emit_node_head(node.head)
        self.out.append(ind + head_text)
        if node.block is not None:
            self.out.append(" ")
            self.emit_block(node.block, depth=depth)
        else:
            self.out.append("\n")

    def _emit_node_head(self, h: NodeHead) -> str:
        parts: list[str] = []
        # Head prefix
        if h.head_kind == "type":
            parts.append(h.type_or_path)
        elif h.head_kind == "comp-ref":
            scope = f"{h.scope_alias}::" if h.scope_alias else ""
            parts.append(f"-> {scope}{h.type_or_path}")
            if h.override_args:
                args_text = ", ".join(
                    f"{a.key}={self.emit_value(a.value)}"
                    for a in h.override_args
                )
                parts[-1] += f"({args_text})"
        elif h.head_kind == "pattern-ref":
            scope = f"{h.scope_alias}::" if h.scope_alias else ""
            parts.append(f"& {scope}{h.type_or_path}")
        elif h.head_kind == "edit-ref":
            # `@eid` addressing at construction context — emit via the
            # same `@<path>` form that parsed in (grammar §5.2, §8).
            parts.append(f"@{h.type_or_path}")

        # EID + alias
        if h.eid:
            parts.append(f"#{h.eid}")
        if h.alias:
            parts.append(f"as {h.alias}")

        # Positional content (text-bearing nodes)
        if h.positional is not None:
            parts.append(self.emit_value(h.positional))

        # Properties in canonical order
        props_sorted = sorted(
            h.properties,
            key=lambda p: _prop_rank(
                p.key if isinstance(p, PropAssign) else p.path
            ),
        )
        for p in props_sorted:
            if isinstance(p, PropAssign):
                v = self.emit_value(p.value)
                t = ""
                if p.trailer:
                    t = " " + self._emit_value_trailer(p.trailer)
                parts.append(f"{p.key}={v}{t}")
            elif isinstance(p, PathOverride):
                parts.append(f"{p.path}={self.emit_value(p.value)}")

        # Node trailer
        if h.trailer is not None:
            parts.append(self._emit_node_trailer(h.trailer))

        return " ".join(parts)

    def _emit_node_inline(self, node: Node) -> str:
        """Single-line form of a Node, used in slot-default / OverrideArgs
        value position. No nested block supported inline — a node with a
        body emits with its block on the same line."""
        head = self._emit_node_head(node.head)
        if node.block is not None:
            # Emit block inline (single-line)
            stmts = [self._emit_block_stmt_inline(s) for s in node.block.statements]
            return head + " { " + " ".join(stmts) + " }"
        return head

    def _emit_block_stmt_inline(self, s: object) -> str:
        if isinstance(s, Node):
            return self._emit_node_inline(s)
        if isinstance(s, SlotPlaceholder):
            return f"{{{s.name}}}"
        if isinstance(s, PropAssign):
            v = self.emit_value(s.value)
            t = ""
            if s.trailer:
                t = " " + self._emit_value_trailer(s.trailer)
            return f"{s.key}={v}{t}"
        if isinstance(s, PathOverride):
            return f"{s.path}={self.emit_value(s.value)}"
        if isinstance(s, SlotFill):
            return f"{s.slot_name} = {self._emit_node_inline(s.node)}"
        raise DDMarkupSerializeError(
            f"cannot emit inline block statement of type {type(s).__name__}",
            path="block",
        )

    def emit_block(self, block: Block, *, depth: int) -> None:
        self.out.append("{\n")
        inner_ind = self.INDENT * (depth + 1)
        for stmt in block.statements:
            if isinstance(stmt, Node):
                self.emit_node(stmt, depth=depth + 1)
            elif isinstance(stmt, SlotPlaceholder):
                self.out.append(f"{inner_ind}{{{stmt.name}}}\n")
            elif isinstance(stmt, PropAssign):
                v = self.emit_value(stmt.value)
                t = ""
                if stmt.trailer:
                    t = " " + self._emit_value_trailer(stmt.trailer)
                self.out.append(f"{inner_ind}{stmt.key}={v}{t}\n")
            elif isinstance(stmt, PathOverride):
                self.out.append(
                    f"{inner_ind}{stmt.path}={self.emit_value(stmt.value)}\n"
                )
            elif isinstance(stmt, SlotFill):
                self.out.append(f"{inner_ind}{stmt.slot_name} = ")
                # Emit the slot-fill node inline when it has no block,
                # or with a block when it does.
                n = stmt.node
                head = self._emit_node_head(n.head)
                self.out.append(head)
                if n.block is not None:
                    self.out.append(" ")
                    self.emit_block(n.block, depth=depth + 1)
                else:
                    self.out.append("\n")
            else:
                raise DDMarkupSerializeError(
                    f"unknown block statement type: {type(stmt).__name__}",
                    path="block",
                )
        self.out.append(self.INDENT * depth + "}\n")

    # -----------------------------------------------------------------------
    # Values
    # -----------------------------------------------------------------------

    def emit_value(self, v: Value) -> str:
        if isinstance(v, Literal_):
            return self._emit_literal(v)
        if isinstance(v, TokenRef):
            scope = f"{v.scope_alias}::" if v.scope_alias else ""
            return "{" + scope + v.path + "}"
        if isinstance(v, ComponentRefValue):
            scope = f"{v.scope_alias}::" if v.scope_alias else ""
            out = f"-> {scope}{v.path}"
            if v.override_args:
                args_text = ", ".join(
                    f"{a.key}={self.emit_value(a.value)}"
                    for a in v.override_args
                )
                out += f"({args_text})"
            return out
        if isinstance(v, PatternRefValue):
            scope = f"{v.scope_alias}::" if v.scope_alias else ""
            return f"& {scope}{v.path}"
        if isinstance(v, FunctionCall):
            args = ", ".join(self._emit_func_arg(a) for a in v.args)
            return f"{v.name}({args})"
        if isinstance(v, PropGroup):
            return self._emit_propgroup(v)
        if isinstance(v, SizingValue):
            if v.min is None and v.max is None:
                return v.size_kind
            pieces: list[str] = []
            if v.min is not None:
                pieces.append(f"min={_fmt_number(v.min)}")
            if v.max is not None:
                pieces.append(f"max={_fmt_number(v.max)}")
            return f"{v.size_kind}({', '.join(pieces)})"
        if isinstance(v, Node):
            return self._emit_node_inline(v)
        raise DDMarkupSerializeError(
            f"cannot emit value of type {type(v).__name__}",
            path="value",
        )

    def _emit_literal(self, lit: Literal_) -> str:
        if lit.lit_kind == "string":
            # Use the raw form if it round-trips cleanly; otherwise escape
            # from the py value.
            return lit.raw if lit.raw.startswith('"') else _quote_string(lit.py)
        if lit.lit_kind == "number":
            # Emit canonical form derived from `py`. This normalizes
            # `1e2` → `100` and `-0` → `0` at emit time. The parse-side
            # normalization rewrites `Literal_.raw` to match so round-
            # trip equality holds (see `_parse_value`).
            return _fmt_number(lit.py)
        if lit.lit_kind == "hex-color":
            return lit.raw
        if lit.lit_kind == "asset-hash":
            return lit.raw
        if lit.lit_kind == "bool":
            return "true" if lit.py else "false"
        if lit.lit_kind == "null":
            return "null"
        if lit.lit_kind == "enum":
            return lit.py if isinstance(lit.py, str) else str(lit.raw)
        raise DDMarkupSerializeError(
            f"unknown literal kind {lit.lit_kind}", path="literal",
        )

    def _emit_func_arg(self, a: FuncArg) -> str:
        if a.name is not None:
            return f"{a.name}={self.emit_value(a.value)}"
        return self.emit_value(a.value)

    def _emit_propgroup(self, pg: PropGroup) -> str:
        entries = list(pg.entries)
        # Canonical side order for well-known groups
        ordered: list[PropAssign] = []
        for e in entries:
            # Canonical ordering depends on context; we don't know the
            # parent property key here, so fall back to lex order with
            # the assumption that well-known entries like top/right/... fit
            # the §7.6 order naturally when sorted by insertion order.
            ordered.append(e)
        # Lex-sort unless entries match a known side-order pattern.
        keys = [e.key for e in entries]
        for group_name, order in _PROPGROUP_SIDE_ORDER.items():
            if set(keys).issubset(set(order)):
                # Sort per the group's canonical order
                pos = {k: i for i, k in enumerate(order)}
                ordered = sorted(entries, key=lambda e: pos.get(e.key, 999))
                break
        else:
            ordered = sorted(entries, key=lambda e: e.key)
        inner = " ".join(
            f"{e.key}={self.emit_value(e.value)}" for e in ordered
        )
        return "{" + inner + "}"

    def _emit_node_trailer(self, t: NodeTrailer) -> str:
        inner = " ".join(
            f"{k}={self.emit_value(v)}" for k, v in t.attrs
        )
        return f"({t.kind}" + (f" {inner}" if inner else "") + ")"

    def _emit_value_trailer(self, t: ValueTrailer) -> str:
        inner = " ".join(
            f"{k}={self.emit_value(v)}" for k, v in t.attrs
        )
        return f"#[{t.kind}" + (f" {inner}" if inner else "") + "]"


def _quote_string(s: object) -> str:
    """Emit a Python str as a dd StringLit. Chooses single-line or triple
    based on content.

    Escape sequences match `_unquote`'s decoder. Single-pass escape
    encoding: backslash FIRST so subsequent `\\"` → `\\\\"` chain
    substitutions can't double-escape. Order matters.
    """
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    if "\n" in s:
        # Triple-quoted multiline — preserve newlines literally.
        # (No escape processing inside triple-quoted strings.)
        return '"""' + s + '"""'
    # Single-line — single-pass escape
    out: list[str] = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\0":
            out.append("\\0")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _fmt_number(n: object) -> str:
    """Canonical shortest-lossless number form."""
    if isinstance(n, bool):                 # bool is subclass of int; guard
        return "true" if n else "false"
    if isinstance(n, int):
        return str(n)
    if isinstance(n, float):
        # Avoid `8.0` when `8` is lossless
        if n.is_integer() and abs(n) < 1e16:
            return str(int(n))
        # Prefer short representation; Python's `repr(float)` is shortest-
        # unique since 3.1
        return repr(n)
    return str(n)


def validate(doc: L3Document, *, mode: str = "E") -> list[Warning]:
    """Structural validator. Stage 5 expands per grammar-modes decision."""
    # Current slice: pass through any warnings from parse.
    return list(doc.warnings)


# ---------------------------------------------------------------------------
# Edit-application engine (M7.1) — grammar §8.7 / §8.8
# ---------------------------------------------------------------------------


def _resolve_eref(
    doc: L3Document, target: ERef,
) -> tuple[Optional[Node], list[tuple[object, int]]]:
    """Resolve an ERef against the construction tree.

    Returns ``(node, path)`` where:
    - ``node`` is the resolved Node (or None if not found / ambiguous;
      caller decides how to react via KIND_*).
    - ``path`` is the list of ``(parent, child_index)`` tuples from
      root to the target's parent. Used by tree-rebuilding handlers.

    Raises ``DDMarkupParseError`` with kind=KIND_EID_AMBIGUOUS for
    multi-match (callers must qualify with dotted/slash path) and for
    wildcard / cross-library targets (deferred to M7.3+).
    """
    if target.has_wildcard:
        raise DDMarkupParseError(
            f"wildcard ERef `@{target.path}` is not supported by "
            "apply_edits in M7.1 (deferred to M7.3+)",
            kind="KIND_EID_AMBIGUOUS",
            line=None, col=None,
        )
    if target.scope_alias is not None:
        raise DDMarkupParseError(
            f"cross-library ERef `@{target.scope_alias}::{target.path}` "
            "is not supported by apply_edits in M7.1 (deferred to "
            "post-v0.3)",
            kind="KIND_EID_AMBIGUOUS",
            line=None, col=None,
        )

    # Split dotted path: `card-1.title` → ["card-1", "title"]; the
    # apply-engine walks segment-by-segment.
    segments = target.path.split(".") if "." in target.path else [
        target.path,
    ]

    # For a single-segment path: walk the entire tree, collect all
    # nodes whose head.eid matches. Single match → resolved.
    # Multi-segment: descend through each segment as a parent → child
    # match.
    matches: list[tuple[Node, list[tuple[object, int]]]] = []
    if len(segments) == 1:
        eid = segments[0]
        for item in doc.top_level:
            if not isinstance(item, Node):
                continue
            _walk_for_eid(item, eid, [], matches)
    else:
        # Descend through each segment.
        for item in doc.top_level:
            if not isinstance(item, Node):
                continue
            _walk_dotted(item, segments, [], matches)

    if not matches:
        return (None, [])
    if len(matches) > 1:
        paths = [_describe_match_path(m[1]) for m in matches]
        raise DDMarkupParseError(
            f"ERef `@{target.path}` resolves to {len(matches)} "
            f"nodes; qualify with a dotted/slash path. Matches: "
            f"{paths}",
            kind="KIND_EID_AMBIGUOUS",
            line=None, col=None,
        )
    return matches[0]


def _walk_for_eid(
    node: Node, eid: str,
    path_so_far: list[tuple[object, int]],
    matches: list[tuple[Node, list[tuple[object, int]]]],
) -> None:
    """Depth-first walk; collect every node where head.eid matches."""
    if node.head.eid == eid:
        matches.append((node, list(path_so_far)))
    if node.block is None:
        return
    for idx, stmt in enumerate(node.block.statements):
        if isinstance(stmt, Node):
            _walk_for_eid(
                stmt, eid,
                path_so_far + [(node, idx)],
                matches,
            )


def _walk_dotted(
    node: Node, segments: list[str],
    path_so_far: list[tuple[object, int]],
    matches: list[tuple[Node, list[tuple[object, int]]]],
) -> None:
    """Depth-first walk for dotted-path resolution: each segment must
    match the next nesting level. The first segment can match anywhere;
    subsequent segments must be direct children of the previously-
    matched node.
    """
    first, *rest = segments
    if node.head.eid == first:
        if not rest:
            matches.append((node, list(path_so_far)))
            return
        # Descend into children for the next segment.
        if node.block is None:
            return
        for idx, stmt in enumerate(node.block.statements):
            if isinstance(stmt, Node) and stmt.head.eid == rest[0]:
                _walk_dotted(
                    stmt, rest,
                    path_so_far + [(node, idx)],
                    matches,
                )
        return
    # Not a match at this level; keep searching deeper for the first
    # segment.
    if node.block is None:
        return
    for idx, stmt in enumerate(node.block.statements):
        if isinstance(stmt, Node):
            _walk_dotted(
                stmt, segments,
                path_so_far + [(node, idx)],
                matches,
            )


def _describe_match_path(
    path: list[tuple[object, int]],
) -> str:
    """Render a (parent, idx)-list path for ambiguous-error messages."""
    parts = []
    for parent, _idx in path:
        eid = getattr(parent.head, "eid", None) if hasattr(parent, "head") else None
        parts.append(eid or "?")
    return "/".join(parts) if parts else "<root>"


def _replace_node_at_path(
    doc: L3Document,
    path: list[tuple[object, int]],
    final_node: Node,
    final_index_in_top: int,
    new_subtree: Node,
) -> L3Document:
    """Rebuild the document with `final_node` replaced by `new_subtree`.

    Walks back up the path, using `dataclasses.replace()` at each
    level to construct fresh frozen instances. The unchanged portions
    of the tree are shared.
    """
    if not path:
        # The target is a top-level Node; rebuild top_level tuple.
        new_top = list(doc.top_level)
        new_top[final_index_in_top] = new_subtree
        return replace(doc, top_level=tuple(new_top))

    # Walk path from the deepest parent up to the root, rebuilding.
    current = new_subtree
    # The deepest parent is path[-1]; its block.statements gets the
    # current at its child slot.
    for parent, child_idx in reversed(path):
        new_stmts = list(parent.block.statements)
        new_stmts[child_idx] = current
        new_block = replace(parent.block, statements=tuple(new_stmts))
        current = replace(parent, block=new_block)

    # `current` is now the new top-level node; replace at its index.
    new_top = list(doc.top_level)
    new_top[final_index_in_top] = current
    return replace(doc, top_level=tuple(new_top))


def _apply_set_to_node(node: Node, stmt: SetStatement) -> Node:
    """Merge new properties into the existing node head, last-wins per
    key. Returns a fresh Node with the merged head.
    """
    existing_props = list(node.head.properties)
    by_key: dict[str, int] = {}
    for i, p in enumerate(existing_props):
        if isinstance(p, PropAssign):
            by_key[p.key] = i
        elif isinstance(p, PathOverride):
            by_key[p.path] = i

    for new_p in stmt.properties:
        key = new_p.key if isinstance(new_p, PropAssign) else new_p.path
        if key in by_key:
            existing_props[by_key[key]] = new_p
        else:
            existing_props.append(new_p)
            by_key[key] = len(existing_props) - 1

    new_head = replace(node.head, properties=tuple(existing_props))
    return replace(node, head=new_head)


def apply_edits(
    doc: L3Document,
    stmts: Optional[list[object]] = None,
    *,
    strict: bool = True,
) -> L3Document:
    """Apply a sequence of edit statements to a document.

    Returns a new `L3Document`; never mutates the input. Statements
    apply sequentially, each operating on the result of all prior
    statements.

    `strict=True` (default) raises `DDMarkupParseError` on the first
    error (unresolvable ERef, contradiction). `strict=False` collects
    errors as `Warning` entries on the result document and continues.

    See `docs/spec-dd-markup-grammar.md` §8.7-§8.9 for semantics.
    Pass-2 implements `set` only; other verbs raise NotImplementedError.
    """
    if stmts is None:
        stmts = list(doc.edits)
    if not stmts:
        return doc

    current = doc
    accumulated_warnings = list(doc.warnings)
    deleted_targets: set[str] = set()

    for stmt in stmts:
        try:
            current = _apply_one(current, stmt, deleted_targets)
        except DDMarkupParseError as e:
            if strict:
                raise
            accumulated_warnings.append(Warning(
                kind=e.kind, message=str(e),
                line=e.line, col=e.col,
            ))

    return replace(current, warnings=tuple(accumulated_warnings))


def _apply_one(
    doc: L3Document,
    stmt: object,
    deleted_targets: set[str],
) -> L3Document:
    """Apply a single edit statement to the document. Internal helper
    so the per-statement loop in `apply_edits` can do error policy
    around each call. Per-verb branches expand here as Passes 3-8
    land.
    """
    if isinstance(stmt, SetStatement):
        return _apply_set(doc, stmt, deleted_targets)
    if isinstance(stmt, DeleteStatement):
        return _apply_delete(doc, stmt, deleted_targets)
    if isinstance(stmt, AppendStatement):
        return _apply_append(doc, stmt, deleted_targets)
    if isinstance(stmt, InsertStatement):
        return _apply_insert(doc, stmt, deleted_targets)
    if isinstance(stmt, MoveStatement):
        return _apply_move(doc, stmt, deleted_targets)
    if isinstance(stmt, ReplaceStatement):
        return _apply_replace(doc, stmt, deleted_targets)
    if isinstance(stmt, SwapStatement):
        return _apply_swap(doc, stmt, deleted_targets)
    raise NotImplementedError(
        f"apply for {type(stmt).__name__} arrives in a later M7.1 pass"
    )


def _apply_swap(
    doc: L3Document,
    stmt: SwapStatement,
    deleted_targets: set[str],
) -> L3Document:
    """M7.1: replace the addressed node with stmt.with_node, carrying
    the target's eid forward onto the replacement so subsequent edits
    can address it. Override preservation across CompRef swaps is
    deferred to M7.2 (requires component_slots data from M7.0.b).
    """
    if stmt.target.path in deleted_targets:
        raise DDMarkupParseError(
            f"swap targets `@{stmt.target.path}` which was deleted "
            "earlier in this edit sequence",
            kind="KIND_EDIT_CONFLICT",
            line=stmt.line, col=stmt.col,
        )
    target_node, target_path = _resolve_eref(doc, stmt.target)
    if target_node is None:
        raise DDMarkupParseError(
            f"swap target `@{stmt.target.path}` not found.",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    # Carry the target's eid forward onto the replacement so
    # subsequent edits can address by the same name.
    new_head = replace(stmt.with_node.head, eid=target_node.head.eid)
    new_node = replace(stmt.with_node, head=new_head)
    return _splice_node(doc, target_path, target_node, new_node)


def _apply_replace(
    doc: L3Document,
    stmt: ReplaceStatement,
    deleted_targets: set[str],
) -> L3Document:
    """OQ-3 Interpretation A: replaces the addressed node's BLOCK
    CONTENT; the node itself stays. To replace the node entirely,
    use `swap`.
    """
    if stmt.target.path in deleted_targets:
        raise DDMarkupParseError(
            f"replace targets `@{stmt.target.path}` which was deleted "
            "earlier in this edit sequence",
            kind="KIND_EDIT_CONFLICT",
            line=stmt.line, col=stmt.col,
        )
    target_node, target_path = _resolve_eref(doc, stmt.target)
    if target_node is None:
        raise DDMarkupParseError(
            f"replace target `@{stmt.target.path}` not found.",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    new_block = stmt.body if stmt.body is not None else Block()
    new_node = replace(target_node, block=new_block)
    return _splice_node(doc, target_path, target_node, new_node)


def _apply_move(
    doc: L3Document,
    stmt: MoveStatement,
    deleted_targets: set[str],
) -> L3Document:
    """`move` = atomic delete + insert. Resolve target + destination
    on the ORIGINAL doc (not on a delete-then-insert intermediate),
    so the destination's anchor index isn't invalidated by the
    target's removal.
    """
    if (
        stmt.target.path in deleted_targets
        or stmt.to.path in deleted_targets
    ):
        raise DDMarkupParseError(
            f"move references `@{stmt.target.path}`/`@{stmt.to.path}` "
            "which was deleted earlier in this edit sequence",
            kind="KIND_EDIT_CONFLICT",
            line=stmt.line, col=stmt.col,
        )

    target_node, target_path = _resolve_eref(doc, stmt.target)
    if target_node is None:
        raise DDMarkupParseError(
            f"move target `@{stmt.target.path}` not found.",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    dest_node, dest_path = _resolve_eref(doc, stmt.to)
    if dest_node is None:
        raise DDMarkupParseError(
            f"move destination `@{stmt.to.path}` not found.",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    if not target_path:
        raise DDMarkupParseError(
            "cannot move a top-level node (no parent to detach from)",
            kind="KIND_EDIT_INVALID_TARGET",
            line=stmt.line, col=stmt.col,
        )

    # Build the moved-into-destination block first.
    if dest_node.block is None:
        dest_block_stmts: list[object] = []
    else:
        dest_block_stmts = list(dest_node.block.statements)

    # Remove target from dest's children if it lives there (same-
    # parent move). This avoids duplicating it.
    dest_block_stmts = [
        s for s in dest_block_stmts if s is not target_node
    ]

    # Compute insertion index per `position` / `position_anchor`.
    if stmt.position == "first":
        ins_idx = 0
    elif stmt.position == "last":
        ins_idx = len(dest_block_stmts)
    elif stmt.position in ("after", "before"):
        if stmt.position_anchor is None:
            raise DDMarkupParseError(
                f"move position={stmt.position} requires an anchor",
                kind="KIND_BAD_EDIT_VERB",
                line=stmt.line, col=stmt.col,
            )
        anchor_eid = stmt.position_anchor.path
        anchor_idx: Optional[int] = None
        for i, sib in enumerate(dest_block_stmts):
            if isinstance(sib, Node) and sib.head.eid == anchor_eid:
                anchor_idx = i
                break
        if anchor_idx is None:
            raise DDMarkupParseError(
                f"move position={stmt.position} anchor "
                f"`@{anchor_eid}` not a child of `@{stmt.to.path}`",
                kind="KIND_EID_NOT_FOUND",
                line=stmt.line, col=stmt.col,
            )
        ins_idx = anchor_idx + 1 if stmt.position == "after" else anchor_idx
    else:
        ins_idx = len(dest_block_stmts)

    new_dest_stmts = (
        tuple(dest_block_stmts[:ins_idx])
        + (target_node,)
        + tuple(dest_block_stmts[ins_idx:])
    )
    new_dest_block = (
        Block(statements=new_dest_stmts) if dest_node.block is None
        else replace(dest_node.block, statements=new_dest_stmts)
    )
    new_dest_node = replace(dest_node, block=new_dest_block)

    # Remove target from its original parent (only if NOT same parent
    # as dest; for same-parent we already filtered out target above
    # and rebuilt the block with the new position).
    target_parent, target_idx = target_path[-1]

    # Build a doc with both rewrites applied. The challenge: we need
    # to rebuild the tree such that BOTH the target's old parent and
    # the dest get their new states. They may share ancestors.
    same_parent = target_parent is dest_node

    if same_parent:
        # The dest_node's new state already reflects the move (we
        # filtered out the target before re-inserting). Just put
        # new_dest_node back in place via dest_path.
        return _splice_node(doc, dest_path, dest_node, new_dest_node)

    # Different parents. Two-step structural rewrite:
    # 1) Build the new target_parent without the target.
    new_target_parent_stmts = list(target_parent.block.statements)
    del new_target_parent_stmts[target_idx]
    new_target_parent = replace(
        target_parent,
        block=replace(
            target_parent.block, statements=tuple(new_target_parent_stmts),
        ),
    )

    # 2) Apply both rewrites, with the wrinkle that one can be
    # nested under the other. _splice_node operates on the original
    # doc; if we splice them sequentially, the second splice runs on
    # a doc where the first splice already changed the ancestor,
    # which means the second splice's `path` is stale. Resolve by
    # re-resolving after the first splice.

    doc_after_target = _splice_node(
        doc, target_path[:-1], target_parent, new_target_parent,
    )

    # Now find dest_node again in the new doc — its identity may
    # have changed if it was an ancestor/descendant of target_parent,
    # but we resolved on the original. Re-resolve.
    fresh_dest, fresh_dest_path = _resolve_eref(doc_after_target, stmt.to)
    if fresh_dest is None:
        raise DDMarkupParseError(
            f"internal: dest `@{stmt.to.path}` lost during move splice",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    # Rebuild the dest node's block with the moved target inserted
    # at the same index we computed earlier (the anchor index does
    # not change since we already filtered out the target if it
    # lived there).
    fresh_dest_block_stmts = list(
        fresh_dest.block.statements if fresh_dest.block else []
    )
    new_fresh_dest_stmts = (
        tuple(fresh_dest_block_stmts[:ins_idx])
        + (target_node,)
        + tuple(fresh_dest_block_stmts[ins_idx:])
    )
    new_fresh_dest_block = (
        Block(statements=new_fresh_dest_stmts) if fresh_dest.block is None
        else replace(fresh_dest.block, statements=new_fresh_dest_stmts)
    )
    new_fresh_dest_node = replace(fresh_dest, block=new_fresh_dest_block)

    return _splice_node(
        doc_after_target, fresh_dest_path, fresh_dest, new_fresh_dest_node,
    )


def _splice_node(
    doc: L3Document,
    path: list[tuple[object, int]],
    old_subtree: Node,
    new_subtree: Node,
) -> L3Document:
    """Replace `old_subtree` with `new_subtree` at the position given
    by `path`. Walks back up the path with dataclasses.replace.
    """
    if not path:
        # Top-level — `old_subtree` is in doc.top_level by identity.
        new_top = list(doc.top_level)
        for i, item in enumerate(new_top):
            if item is old_subtree:
                new_top[i] = new_subtree
                return replace(doc, top_level=tuple(new_top))
        raise DDMarkupParseError(
            "internal: top-level node not located in splice",
            kind="KIND_EID_NOT_FOUND",
            line=None, col=None,
        )
    current = new_subtree
    for parent, child_idx in reversed(path):
        ps = list(parent.block.statements)
        ps[child_idx] = current
        current = replace(
            parent, block=replace(parent.block, statements=tuple(ps)),
        )
    root_parent = path[0][0]
    new_top = list(doc.top_level)
    for i, item in enumerate(new_top):
        if item is root_parent:
            new_top[i] = current
            return replace(doc, top_level=tuple(new_top))
    raise DDMarkupParseError(
        "internal: root parent not found during splice",
        kind="KIND_EID_NOT_FOUND",
        line=None, col=None,
    )


def _apply_insert(
    doc: L3Document,
    stmt: InsertStatement,
    deleted_targets: set[str],
) -> L3Document:
    if stmt.into.path in deleted_targets:
        raise DDMarkupParseError(
            f"insert targets `@{stmt.into.path}` which was deleted "
            "earlier in this edit sequence",
            kind="KIND_EDIT_CONFLICT",
            line=stmt.line, col=stmt.col,
        )
    parent_node, path = _resolve_eref(doc, stmt.into)
    if parent_node is None:
        raise DDMarkupParseError(
            f"insert into=@{stmt.into.path} not found in document.",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )

    # Find the anchor as a direct child of the resolved parent.
    if parent_node.block is None:
        raise DDMarkupParseError(
            f"insert anchor=@{stmt.anchor.path} not found "
            f"(parent `@{stmt.into.path}` has no children)",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    anchor_idx: Optional[int] = None
    for i, sib in enumerate(parent_node.block.statements):
        if isinstance(sib, Node) and sib.head.eid == stmt.anchor.path:
            anchor_idx = i
            break
    if anchor_idx is None:
        raise DDMarkupParseError(
            f"insert anchor=@{stmt.anchor.path} is not a child of "
            f"`@{stmt.into.path}`",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )

    body_stmts = stmt.body.statements if stmt.body is not None else ()
    insertion_idx = anchor_idx + 1 if stmt.anchor_rel == "after" else anchor_idx
    new_stmts = (
        parent_node.block.statements[:insertion_idx]
        + tuple(body_stmts)
        + parent_node.block.statements[insertion_idx:]
    )
    new_block = replace(parent_node.block, statements=new_stmts)
    new_parent = replace(parent_node, block=new_block)

    if not path:
        for i, item in enumerate(doc.top_level):
            if item is parent_node:
                new_top = list(doc.top_level)
                new_top[i] = new_parent
                return replace(doc, top_level=tuple(new_top))
        raise DDMarkupParseError(
            "internal: top-level node not located in insert",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    current = new_parent
    for grandparent, child_idx in reversed(path):
        gs = list(grandparent.block.statements)
        gs[child_idx] = current
        current = replace(
            grandparent,
            block=replace(grandparent.block, statements=tuple(gs)),
        )
    root_parent = path[0][0]
    new_top = list(doc.top_level)
    for i, item in enumerate(new_top):
        if item is root_parent:
            new_top[i] = current
            return replace(doc, top_level=tuple(new_top))
    raise DDMarkupParseError(
        "internal: root parent not found during insert",
        kind="KIND_EID_NOT_FOUND",
        line=stmt.line, col=stmt.col,
    )


def _apply_append(
    doc: L3Document,
    stmt: AppendStatement,
    deleted_targets: set[str],
) -> L3Document:
    if stmt.to.path in deleted_targets:
        raise DDMarkupParseError(
            f"append targets `@{stmt.to.path}` which was deleted "
            "earlier in this edit sequence",
            kind="KIND_EDIT_CONFLICT",
            line=stmt.line, col=stmt.col,
        )
    parent_node, path = _resolve_eref(doc, stmt.to)
    if parent_node is None:
        raise DDMarkupParseError(
            f"append target `@{stmt.to.path}` not found in document.",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )

    # Build the new block: existing statements + body.statements.
    body_stmts = stmt.body.statements if stmt.body is not None else ()
    if parent_node.block is None:
        new_block = Block(statements=tuple(body_stmts))
    else:
        new_block = replace(
            parent_node.block,
            statements=parent_node.block.statements + tuple(body_stmts),
        )
    new_parent = replace(parent_node, block=new_block)

    # Reconstruct the tree with the modified parent in place.
    if not path:
        # Top-level node — replace at its index.
        for i, item in enumerate(doc.top_level):
            if item is parent_node:
                new_top = list(doc.top_level)
                new_top[i] = new_parent
                return replace(doc, top_level=tuple(new_top))
        raise DDMarkupParseError(
            "internal: top-level node not located in append",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )

    # Non-top-level: walk back up the path with the new parent.
    current = new_parent
    for grandparent, child_idx in reversed(path):
        gs = list(grandparent.block.statements)
        gs[child_idx] = current
        new_block_g = replace(grandparent.block, statements=tuple(gs))
        current = replace(grandparent, block=new_block_g)

    root_parent = path[0][0]
    new_top = list(doc.top_level)
    for i, item in enumerate(new_top):
        if item is root_parent:
            new_top[i] = current
            return replace(doc, top_level=tuple(new_top))
    raise DDMarkupParseError(
        "internal: root parent not found during append",
        kind="KIND_EID_NOT_FOUND",
        line=stmt.line, col=stmt.col,
    )


def _apply_delete(
    doc: L3Document,
    stmt: DeleteStatement,
    deleted_targets: set[str],
) -> L3Document:
    if stmt.target.path in deleted_targets:
        raise DDMarkupParseError(
            f"delete targets `@{stmt.target.path}` which was already "
            "deleted earlier in this edit sequence",
            kind="KIND_EDIT_CONFLICT",
            line=stmt.line, col=stmt.col,
        )
    node, path = _resolve_eref(doc, stmt.target)
    if node is None:
        raise DDMarkupParseError(
            f"delete target `@{stmt.target.path}` not found in document.",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    deleted_targets.add(stmt.target.path)

    if not path:
        # Top-level delete — drop from doc.top_level.
        new_top = [
            item for item in doc.top_level if item is not node
        ]
        return replace(doc, top_level=tuple(new_top))

    # Walk path from deepest parent up; drop the child at the slot.
    deepest_parent, child_idx = path[-1]
    new_stmts = list(deepest_parent.block.statements)
    del new_stmts[child_idx]
    new_block = replace(deepest_parent.block, statements=tuple(new_stmts))
    current = replace(deepest_parent, block=new_block)

    # Walk back further up the path with `current` as the new
    # subtree, replacing it at each level.
    for parent, idx in reversed(path[:-1]):
        ps = list(parent.block.statements)
        ps[idx] = current
        nb = replace(parent.block, statements=tuple(ps))
        current = replace(parent, block=nb)

    # Top-level: replace the root.
    root_parent = path[0][0]
    new_top = list(doc.top_level)
    for i, item in enumerate(new_top):
        if item is root_parent:
            new_top[i] = current
            return replace(doc, top_level=tuple(new_top))
    raise DDMarkupParseError(
        "internal: root parent not found during delete",
        kind="KIND_EID_NOT_FOUND",
        line=stmt.line, col=stmt.col,
    )


def _apply_set(
    doc: L3Document,
    stmt: SetStatement,
    deleted_targets: set[str],
) -> L3Document:
    if stmt.target.path in deleted_targets:
        raise DDMarkupParseError(
            f"set targets `@{stmt.target.path}` which was deleted "
            "earlier in this edit sequence",
            kind="KIND_EDIT_CONFLICT",
            line=stmt.line, col=stmt.col,
        )
    node, path = _resolve_eref(doc, stmt.target)
    if node is None:
        raise DDMarkupParseError(
            f"set target `@{stmt.target.path}` not found in document. "
            "If this eid was auto-generated by the parser, promote "
            "it to an explicit `#eid` before editing.",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    new_node = _apply_set_to_node(node, stmt)

    # Find the top-level index for this branch by walking path[0]'s
    # parent — but path may be empty if the target IS top-level.
    if not path:
        # Top-level node. Find its index by identity.
        for i, item in enumerate(doc.top_level):
            if item is node:
                return _replace_node_at_path(doc, [], new_node, i, new_node)
        raise DDMarkupParseError(
            "internal: top-level node could not be located by identity",
            kind="KIND_EID_NOT_FOUND",
            line=stmt.line, col=stmt.col,
        )
    # Find top index from the root parent.
    root_parent = path[0][0]
    for i, item in enumerate(doc.top_level):
        if item is root_parent:
            return _replace_node_at_path(doc, path, node, i, new_node)
    raise DDMarkupParseError(
        "internal: root parent of resolved ERef not found in top_level",
        kind="KIND_EID_NOT_FOUND",
        line=stmt.line, col=stmt.col,
    )
