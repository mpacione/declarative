"""dd markup — KDL v2 substrate + our extensions.

A serde for the dict IR. Conservative position per
`docs/decisions/v0.3-canonical-ir.md`: dict IR remains canonical; dd markup
is a lossless projection used at LLM boundaries, for editing, and for
diagnostic/archival representations of the IR.

**Grammar (minimum dialect for IR round-trip):**

    Document  := Node*
    Node      := IDENT (Arg | Property)* ('{' NEWLINE Node* '}')? NEWLINE
    Arg       := Value
    Property  := IDENT '=' Value
    Value     := STRING | NUMBER | BOOL | NULL | IDENT

Extensions over bare KDL v2 (fully documented; not hidden):

- `children <eid>*` — positional-arg list for element children
  (KDL properties are single-valued; children are a list)
- `<name> { _entry ... _entry ... }` — list-of-dicts pattern (each entry
  is a child node named `_entry`)
- `<name> { _list_empty }` — empty-list marker (disambiguates from
  empty-dict `{}`)
- `_<field>` underscore prefix on property names — preserved literally;
  round-trips through serde without interpretation (see
  `docs/decisions/v0.3-underscore-field-contracts.md`)

**Public API:**

- `serialize_ir(spec) -> str` — dict IR to markup text
- `parse_dd(source) -> dict` — markup text back to dict IR
- `validate(ir, mode) -> list[StructuredError]` — validation pass, mode
  E/S/R per `docs/decisions/v0.3-grammar-modes.md`

**Exceptions:**

- `DDMarkupError` — base
- `DDMarkupParseError` — carries line/col of offending token
- `DDMarkupSerializeError` — carries Python type path of offending value

**Invariants:**

1. `parse_dd(serialize_ir(ir)) == ir` for every valid IR (proven on 204
   corpus at three tiers; see canonical-IR decision record §3).
2. `serialize_ir(parse_dd(text))` is idempotent (re-parsed text produces
   the same canonical form).
3. Unknown property names serialize and parse untouched (fail-open
   principle; see `feedback_fail_open_not_closed`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "DDMarkupError",
    "DDMarkupParseError",
    "DDMarkupSerializeError",
    "parse_dd",
    "serialize_ir",
    "validate",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DDMarkupError(Exception):
    """Base class for all dd-markup errors."""


class DDMarkupParseError(DDMarkupError):
    """Raised when parsing fails.

    Carries ``line`` / ``col`` of the offending token (1-indexed) and the
    surrounding context snippet when available.
    """

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        col: int | None = None,
        snippet: str | None = None,
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


class DDMarkupSerializeError(DDMarkupError):
    """Raised when a value cannot be serialized to markup text.

    Carries ``path`` (dotted key trail from the IR root) when available.
    """

    def __init__(self, message: str, *, path: str | None = None) -> None:
        parts = [message]
        if path:
            parts.append(f"(at {path})")
        super().__init__(" ".join(parts))
        self.path = path


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


T_IDENT = "IDENT"
T_STRING = "STRING"
T_NUMBER = "NUMBER"
T_BOOL = "BOOL"
T_NULL = "NULL"
T_LBRACE = "LBRACE"
T_RBRACE = "RBRACE"
T_EQUALS = "EQUALS"
T_NEWLINE = "NEWLINE"


@dataclass(frozen=True)
class _Tok:
    kind: str
    value: Any
    line: int  # 1-indexed
    col: int   # 1-indexed


def _tokenize(source: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    i = 0
    n = len(source)
    line = 1
    line_start = 0  # index of first char of current line

    def col_at(idx: int) -> int:
        return idx - line_start + 1

    while i < n:
        ch = source[i]

        if ch == "\n":
            tokens.append(_Tok(T_NEWLINE, None, line, col_at(i)))
            i += 1
            line += 1
            line_start = i
            continue

        if ch in " \t\r":
            i += 1
            continue

        start_line, start_col = line, col_at(i)

        if ch == "{":
            tokens.append(_Tok(T_LBRACE, None, start_line, start_col))
            i += 1
            continue

        if ch == "}":
            tokens.append(_Tok(T_RBRACE, None, start_line, start_col))
            i += 1
            continue

        if ch == "=":
            tokens.append(_Tok(T_EQUALS, None, start_line, start_col))
            i += 1
            continue

        if ch == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                if source[j] == "\\" and j + 1 < n:
                    nxt = source[j + 1]
                    mapped = {
                        "n": "\n",
                        "t": "\t",
                        "r": "\r",
                        '"': '"',
                        "\\": "\\",
                        "0": "\0",
                    }.get(nxt)
                    if mapped is None:
                        # Unknown escape: preserve literally (fail-open)
                        buf.append(nxt)
                    else:
                        buf.append(mapped)
                    j += 2
                    continue
                if source[j] == "\n":
                    raise DDMarkupParseError(
                        "unterminated string literal (newline before closing quote)",
                        line=start_line,
                        col=start_col,
                        snippet=_snippet(source, i),
                    )
                if source[j] == '"':
                    break
                buf.append(source[j])
                j += 1
            if j >= n:
                raise DDMarkupParseError(
                    "unterminated string literal (end of source before closing quote)",
                    line=start_line,
                    col=start_col,
                    snippet=_snippet(source, i),
                )
            tokens.append(_Tok(T_STRING, "".join(buf), start_line, start_col))
            i = j + 1
            continue

        if ch.isdigit() or (
            ch == "-" and i + 1 < n and (source[i + 1].isdigit() or source[i + 1] == ".")
        ):
            j = i + 1
            saw_dot = False
            saw_exp = False
            while j < n:
                c = source[j]
                if c.isdigit():
                    j += 1
                elif c == "." and not saw_dot and not saw_exp:
                    saw_dot = True
                    j += 1
                elif c in "eE" and not saw_exp:
                    saw_exp = True
                    j += 1
                    if j < n and source[j] in "+-":
                        j += 1
                else:
                    break
            raw = source[i:j]
            try:
                if "." in raw or "e" in raw or "E" in raw:
                    tokens.append(_Tok(T_NUMBER, float(raw), start_line, start_col))
                else:
                    tokens.append(_Tok(T_NUMBER, int(raw), start_line, start_col))
            except ValueError:
                raise DDMarkupParseError(
                    f"invalid number literal {raw!r}",
                    line=start_line,
                    col=start_col,
                    snippet=_snippet(source, i),
                ) from None
            i = j
            continue

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (source[j].isalnum() or source[j] in "_-."):
                j += 1
            word = source[i:j]
            if word == "true":
                tokens.append(_Tok(T_BOOL, True, start_line, start_col))
            elif word == "false":
                tokens.append(_Tok(T_BOOL, False, start_line, start_col))
            elif word == "null":
                tokens.append(_Tok(T_NULL, None, start_line, start_col))
            else:
                tokens.append(_Tok(T_IDENT, word, start_line, start_col))
            i = j
            continue

        raise DDMarkupParseError(
            f"unexpected character {ch!r}",
            line=start_line,
            col=start_col,
            snippet=_snippet(source, i),
        )

    return tokens


def _snippet(source: str, idx: int, radius: int = 40) -> str:
    """Grab a short context window around ``idx``, single-line."""
    start = max(0, idx - radius)
    end = min(len(source), idx + radius)
    raw = source[start:end]
    return raw.replace("\n", "⏎ ")


# ---------------------------------------------------------------------------
# Parser — produces a raw AST of KDL-style nodes
# ---------------------------------------------------------------------------


class _Node:
    __slots__ = ("name", "args", "props", "children", "line", "col")

    def __init__(self, name: str, line: int, col: int) -> None:
        self.name = name
        self.args: list[Any] = []
        self.props: dict[str, Any] = {}
        self.children: list[_Node] = []
        self.line = line
        self.col = col


def _parse_document(tokens: list[_Tok]) -> list[_Node]:
    pos = [0]
    nodes: list[_Node] = []
    _skip_newlines(tokens, pos)
    while pos[0] < len(tokens):
        nodes.append(_parse_node(tokens, pos))
        _skip_newlines(tokens, pos)
    return nodes


def _skip_newlines(tokens: list[_Tok], pos: list[int]) -> None:
    while pos[0] < len(tokens) and tokens[pos[0]].kind == T_NEWLINE:
        pos[0] += 1


def _parse_node(tokens: list[_Tok], pos: list[int]) -> _Node:
    tok = tokens[pos[0]]
    if tok.kind != T_IDENT:
        raise DDMarkupParseError(
            f"expected node identifier, got {tok.kind.lower()}",
            line=tok.line,
            col=tok.col,
        )
    pos[0] += 1
    node = _Node(tok.value, tok.line, tok.col)

    while pos[0] < len(tokens):
        t = tokens[pos[0]]

        if t.kind in (T_NEWLINE, T_RBRACE):
            break

        if t.kind == T_LBRACE:
            pos[0] += 1
            _skip_newlines(tokens, pos)
            while pos[0] < len(tokens) and tokens[pos[0]].kind != T_RBRACE:
                node.children.append(_parse_node(tokens, pos))
                _skip_newlines(tokens, pos)
            if pos[0] >= len(tokens):
                raise DDMarkupParseError(
                    f"unclosed block opened at line {t.line}",
                    line=t.line,
                    col=t.col,
                )
            pos[0] += 1  # consume RBRACE
            break

        if (
            t.kind == T_IDENT
            and pos[0] + 1 < len(tokens)
            and tokens[pos[0] + 1].kind == T_EQUALS
        ):
            key = t.value
            pos[0] += 2
            if pos[0] >= len(tokens):
                raise DDMarkupParseError(
                    f"property {key!r} missing value",
                    line=t.line,
                    col=t.col,
                )
            node.props[key] = _parse_value(tokens, pos)
            continue

        node.args.append(_parse_value(tokens, pos))

    return node


def _parse_value(tokens: list[_Tok], pos: list[int]) -> Any:
    t = tokens[pos[0]]
    if t.kind in (T_STRING, T_NUMBER, T_BOOL, T_NULL):
        pos[0] += 1
        return t.value
    if t.kind == T_IDENT:
        pos[0] += 1
        return t.value
    raise DDMarkupParseError(
        f"expected value, got {t.kind.lower()}",
        line=t.line,
        col=t.col,
    )


# ---------------------------------------------------------------------------
# Serialize: dict IR → markup text
# ---------------------------------------------------------------------------


_TOP_LEVEL_EXPECTED_KEYS = ("version", "root", "elements", "tokens", "_node_id_map")


def serialize_ir(spec: dict[str, Any]) -> str:
    """Serialize a dict IR to dd-markup text.

    Raises ``DDMarkupSerializeError`` if a value cannot be represented.
    """
    for key in ("version", "root"):
        if key not in spec:
            raise DDMarkupSerializeError(
                f"missing required top-level key {key!r}",
                path=key,
            )

    lines: list[str] = []
    lines.append(f"version {_emit_value(spec['version'], path='version')}")
    lines.append(f"root {_emit_value(spec['root'], path='root')}")
    lines.extend(_emit_elements_block(spec.get("elements", {})))
    lines.extend(_emit_tokens_block(spec.get("tokens", {})))
    lines.extend(_emit_nid_map_block(spec.get("_node_id_map", {})))
    return "\n".join(lines) + "\n"


def _emit_elements_block(elements: dict[str, Any]) -> list[str]:
    if not elements:
        return ["elements {}"]
    out = ["elements {"]
    for eid, element in elements.items():
        out.extend(_emit_element(eid, element, indent=1))
    out.append("}")
    return out


def _emit_element(eid: str, element: dict[str, Any], indent: int) -> list[str]:
    pad = "  " * indent
    header_parts = [f"element {_emit_value(eid, path=f'elements.{eid}')}"]

    children_list: list[str] | None = None
    scalars: list[tuple[str, Any]] = []
    dicts: list[tuple[str, dict[str, Any]]] = []
    lists: list[tuple[str, list[Any]]] = []

    for key, val in element.items():
        if key == "children" and isinstance(val, list):
            children_list = val
        elif isinstance(val, dict):
            dicts.append((key, val))
        elif isinstance(val, list):
            lists.append((key, val))
        else:
            scalars.append((key, val))

    for key, val in scalars:
        header_parts.append(
            f"{key}={_emit_value(val, path=f'elements.{eid}.{key}')}"
        )

    has_body = children_list is not None or dicts or lists
    if not has_body:
        return [f"{pad}{' '.join(header_parts)}"]

    out = [f"{pad}{' '.join(header_parts)} {{"]
    inner = "  " * (indent + 1)

    if children_list is not None:
        if children_list:
            args = " ".join(
                _emit_value(c, path=f"elements.{eid}.children[{i}]")
                for i, c in enumerate(children_list)
            )
            out.append(f"{inner}children {args}")
        else:
            out.append(f"{inner}children")

    for key, val in dicts:
        out.extend(_emit_nested(key, val, indent + 1, f"elements.{eid}.{key}"))
    for key, val in lists:
        out.extend(_emit_list(key, val, indent + 1, f"elements.{eid}.{key}"))

    out.append(f"{pad}}}")
    return out


def _emit_nested(name: str, data: dict[str, Any], indent: int, path: str) -> list[str]:
    pad = "  " * indent
    scalars: list[tuple[str, Any]] = []
    dicts: list[tuple[str, dict[str, Any]]] = []
    lists: list[tuple[str, list[Any]]] = []

    for k, v in data.items():
        if isinstance(v, dict):
            dicts.append((k, v))
        elif isinstance(v, list):
            lists.append((k, v))
        else:
            scalars.append((k, v))

    header = [name]
    for k, v in scalars:
        header.append(f"{k}={_emit_value(v, path=f'{path}.{k}')}")

    if not dicts and not lists:
        return [f"{pad}{' '.join(header)}"]

    out = [f"{pad}{' '.join(header)} {{"]
    for k, v in dicts:
        out.extend(_emit_nested(k, v, indent + 1, f"{path}.{k}"))
    for k, v in lists:
        out.extend(_emit_list(k, v, indent + 1, f"{path}.{k}"))
    out.append(f"{pad}}}")
    return out


def _emit_list(name: str, items: list[Any], indent: int, path: str) -> list[str]:
    pad = "  " * indent
    inner = "  " * (indent + 1)

    if not items:
        return [f"{pad}{name} {{", f"{inner}_list_empty", f"{pad}}}"]

    out = [f"{pad}{name} {{"]
    for i, item in enumerate(items):
        item_path = f"{path}[{i}]"
        if isinstance(item, dict):
            out.extend(_emit_nested("_entry", item, indent + 1, item_path))
        elif isinstance(item, list):
            out.extend(_emit_list("_entry", item, indent + 1, item_path))
        else:
            out.append(f"{inner}_entry {_emit_value(item, path=item_path)}")
    out.append(f"{pad}}}")
    return out


def _emit_tokens_block(tokens: dict[str, Any]) -> list[str]:
    if not tokens:
        return ["tokens {}"]
    out = ["tokens {"]
    for k, v in tokens.items():
        out.append(f"  token {_emit_value(k, path=f'tokens.{k}')} {_emit_value(v, path=f'tokens.{k}')}")
    out.append("}")
    return out


def _emit_nid_map_block(nid_map: dict[str, int]) -> list[str]:
    if not nid_map:
        return ["_node_id_map {}"]
    out = ["_node_id_map {"]
    for eid, nid in nid_map.items():
        out.append(
            f"  map {_emit_value(eid, path=f'_node_id_map.{eid}')} "
            f"{_emit_value(nid, path=f'_node_id_map.{eid}')}"
        )
    out.append("}")
    return out


def _emit_value(value: Any, *, path: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            .replace("\r", "\\r")
        )
        return f'"{escaped}"'
    raise DDMarkupSerializeError(
        f"cannot serialize value of type {type(value).__name__}: {value!r}",
        path=path,
    )


# ---------------------------------------------------------------------------
# Parse: markup text → dict IR
# ---------------------------------------------------------------------------


def parse_dd(source: str) -> dict[str, Any]:
    """Parse dd-markup text back into a dict IR.

    Raises ``DDMarkupParseError`` on any grammar violation; the exception
    carries ``line`` / ``col`` of the offending token.
    """
    tokens = _tokenize(source)
    ast = _parse_document(tokens)

    spec: dict[str, Any] = {}
    for node in ast:
        if node.name == "version":
            if not node.args:
                raise DDMarkupParseError(
                    "'version' node missing value argument",
                    line=node.line,
                    col=node.col,
                )
            spec["version"] = node.args[0]
        elif node.name == "root":
            if not node.args:
                raise DDMarkupParseError(
                    "'root' node missing value argument",
                    line=node.line,
                    col=node.col,
                )
            spec["root"] = node.args[0]
        elif node.name == "elements":
            spec["elements"] = _parse_elements_block(node)
        elif node.name == "tokens":
            spec["tokens"] = _parse_tokens_block(node)
        elif node.name == "_node_id_map":
            spec["_node_id_map"] = _parse_nid_map_block(node)
        else:
            raise DDMarkupParseError(
                f"unknown top-level node {node.name!r}; "
                f"expected one of: {', '.join(_TOP_LEVEL_EXPECTED_KEYS)}",
                line=node.line,
                col=node.col,
            )
    return spec


def _parse_elements_block(node: _Node) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for child in node.children:
        if child.name != "element":
            raise DDMarkupParseError(
                f"expected 'element' node inside 'elements' block, got {child.name!r}",
                line=child.line,
                col=child.col,
            )
        if not child.args:
            raise DDMarkupParseError(
                "'element' node missing eid argument",
                line=child.line,
                col=child.col,
            )
        eid = child.args[0]
        element: dict[str, Any] = {}
        element.update(child.props)
        for inner in child.children:
            if inner.name == "children":
                element["children"] = list(inner.args)
            else:
                element[inner.name] = _ast_to_nested(inner)
        result[eid] = element
    return result


def _ast_to_nested(node: _Node) -> Any:
    """Turn an AST node into dict or list per sentinel conventions."""
    children_names = {c.name for c in node.children}

    if children_names == {"_list_empty"} and not node.props:
        return []

    if children_names == {"_entry"} and not node.props:
        return [_entry_to_value(c) for c in node.children]

    data: dict[str, Any] = dict(node.props)
    for child in node.children:
        data[child.name] = _ast_to_nested(child)
    return data


def _entry_to_value(entry: _Node) -> Any:
    if entry.args and not entry.props and not entry.children:
        return entry.args[0] if len(entry.args) == 1 else list(entry.args)
    return _ast_to_nested(entry)


def _parse_tokens_block(node: _Node) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for child in node.children:
        if child.name != "token":
            raise DDMarkupParseError(
                f"expected 'token' node inside 'tokens' block, got {child.name!r}",
                line=child.line,
                col=child.col,
            )
        if len(child.args) != 2:
            raise DDMarkupParseError(
                f"'token' node expects 2 args (key, value), got {len(child.args)}",
                line=child.line,
                col=child.col,
            )
        result[child.args[0]] = child.args[1]
    return result


def _parse_nid_map_block(node: _Node) -> dict[str, int]:
    result: dict[str, int] = {}
    for child in node.children:
        if child.name != "map":
            raise DDMarkupParseError(
                f"expected 'map' node inside '_node_id_map' block, got {child.name!r}",
                line=child.line,
                col=child.col,
            )
        if len(child.args) != 2:
            raise DDMarkupParseError(
                f"'map' node expects 2 args (eid, node_id), got {len(child.args)}",
                line=child.line,
                col=child.col,
            )
        result[child.args[0]] = child.args[1]
    return result


# ---------------------------------------------------------------------------
# Validation (Mode E / S / R — see grammar-modes decision record)
# ---------------------------------------------------------------------------


def validate(ir: dict[str, Any], mode: str = "E") -> list[dict[str, Any]]:
    """Validate an IR against a grammar mode.

    Modes:

    - ``"E"`` (Extract) — structural soundness only. Raw values permitted.
    - ``"S"`` (Synthesis) — clusterable-axis values must be token refs.
      Currently a stub; full capability-table integration lands with
      ADR-001 sync work.
    - ``"R"`` (Render) — backend-capability-gated. Stub.

    Returns a list of problem dicts. Empty list = valid under the mode.
    """
    if mode not in ("E", "S", "R"):
        raise ValueError(f"unknown validation mode {mode!r}; expected E, S, or R")

    errors: list[dict[str, Any]] = []

    # Mode-E structural checks (all modes run these)
    for key in ("version", "root", "elements"):
        if key not in ir:
            errors.append({
                "kind": "missing_top_level",
                "path": key,
                "message": f"missing required top-level key {key!r}",
            })

    elements = ir.get("elements", {})
    root_eid = ir.get("root", "")
    if root_eid and root_eid not in elements:
        errors.append({
            "kind": "root_not_in_elements",
            "path": "root",
            "message": f"root eid {root_eid!r} not found in elements",
        })

    # Each element must have a type; children must reference known eids.
    for eid, element in elements.items():
        if "type" not in element:
            errors.append({
                "kind": "element_missing_type",
                "path": f"elements.{eid}",
                "message": f"element {eid!r} missing 'type'",
            })
        for i, child_eid in enumerate(element.get("children", [])):
            if child_eid not in elements:
                errors.append({
                    "kind": "child_eid_unknown",
                    "path": f"elements.{eid}.children[{i}]",
                    "message": (
                        f"element {eid!r} references child eid "
                        f"{child_eid!r} which is not in elements"
                    ),
                })

    if mode == "E":
        return errors

    # Mode-S / Mode-R full impls land with ADR-001 capability sync.
    # Return Mode-E result + a structured warning flagging the stub.
    errors.append({
        "kind": "validator_stub",
        "path": "",
        "message": (
            f"mode {mode!r} validation is a stub; only structural (Mode E) "
            "checks ran. Full Mode-S/R impl lands with ADR-001 capability "
            "table sync."
        ),
    })
    return errors
