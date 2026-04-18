"""dd markup — Priority 0 investigation probe.

THROWAWAY PROTOTYPE. Purpose: prove whether the dict IR can be losslessly
serialized and re-parsed through a KDL-v2-based markup dialect. Lives on
branch `v0.3-dd-markup-probe`; reverts if 204/204 parity drops.

Grammar (KDL v2 lexical substrate):

    Document  := Node*
    Node      := IDENT (Value | IDENT '=' Value)* ('{' NEWLINE Node* '}')? NEWLINE
    Value     := STRING | NUMBER | BOOL | NULL

IR → markup mapping:
    spec["version"]        → version "1.0"
    spec["root"]           → root "<eid>"
    spec["elements"]       → elements { element "<eid>" ... }
    spec["tokens"]         → tokens { ... }
    spec["_node_id_map"]   → _node_id_map { map "<eid>" <node_id> }
    element scalar field   → KDL property on the element node
    element children list  → child node `children` with positional args
    element nested dict    → child node with same name, properties + children

See:
- `docs/continuation-v0.3-next-session.md` §4 Priority 0
"""

from __future__ import annotations

from typing import Any

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


def _tokenize(source: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]

        if ch == "\n":
            tokens.append((T_NEWLINE, None))
            i += 1
            continue

        if ch in " \t\r":
            i += 1
            continue

        if ch == "{":
            tokens.append((T_LBRACE, None))
            i += 1
            continue

        if ch == "}":
            tokens.append((T_RBRACE, None))
            i += 1
            continue

        if ch == "=":
            tokens.append((T_EQUALS, None))
            i += 1
            continue

        if ch == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                if source[j] == "\\" and j + 1 < n:
                    nxt = source[j + 1]
                    if nxt == "n":
                        buf.append("\n")
                    elif nxt == "t":
                        buf.append("\t")
                    elif nxt == '"':
                        buf.append('"')
                    elif nxt == "\\":
                        buf.append("\\")
                    else:
                        buf.append(nxt)
                    j += 2
                    continue
                if source[j] == '"':
                    break
                buf.append(source[j])
                j += 1
            if j >= n:
                raise ValueError(f"Unterminated string starting at {i}")
            tokens.append((T_STRING, "".join(buf)))
            i = j + 1
            continue

        if ch.isdigit() or (ch == "-" and i + 1 < n and source[i + 1].isdigit()):
            j = i + 1
            while j < n and (source[j].isdigit() or source[j] in ".eE+-"):
                j += 1
            raw = source[i:j]
            try:
                if "." in raw or "e" in raw or "E" in raw:
                    tokens.append((T_NUMBER, float(raw)))
                else:
                    tokens.append((T_NUMBER, int(raw)))
            except ValueError:
                raise ValueError(f"Invalid number {raw!r} at {i}") from None
            i = j
            continue

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (source[j].isalnum() or source[j] in "_-."):
                j += 1
            word = source[i:j]
            if word == "true":
                tokens.append((T_BOOL, True))
            elif word == "false":
                tokens.append((T_BOOL, False))
            elif word == "null":
                tokens.append((T_NULL, None))
            else:
                tokens.append((T_IDENT, word))
            i = j
            continue

        raise ValueError(f"Unexpected char {ch!r} at position {i}")

    return tokens


# ---------------------------------------------------------------------------
# Parser — produces an AST of raw KDL nodes
# ---------------------------------------------------------------------------


class _Node:
    __slots__ = ("name", "args", "props", "children")

    def __init__(self, name: str) -> None:
        self.name = name
        self.args: list[Any] = []
        self.props: dict[str, Any] = {}
        self.children: list[_Node] = []


def _parse_document(tokens: list[tuple[str, Any]]) -> list[_Node]:
    pos = [0]
    nodes: list[_Node] = []
    _skip_newlines(tokens, pos)
    while pos[0] < len(tokens):
        nodes.append(_parse_node(tokens, pos))
        _skip_newlines(tokens, pos)
    return nodes


def _skip_newlines(tokens: list[tuple[str, Any]], pos: list[int]) -> None:
    while pos[0] < len(tokens) and tokens[pos[0]][0] == T_NEWLINE:
        pos[0] += 1


def _parse_node(tokens: list[tuple[str, Any]], pos: list[int]) -> _Node:
    kind, value = tokens[pos[0]]
    if kind != T_IDENT:
        raise ValueError(f"Expected identifier at {pos[0]}, got {kind} ({value!r})")
    pos[0] += 1
    node = _Node(value)

    while pos[0] < len(tokens):
        k, v = tokens[pos[0]]

        if k in (T_NEWLINE, T_RBRACE):
            break

        if k == T_LBRACE:
            pos[0] += 1
            _skip_newlines(tokens, pos)
            while tokens[pos[0]][0] != T_RBRACE:
                node.children.append(_parse_node(tokens, pos))
                _skip_newlines(tokens, pos)
            pos[0] += 1
            break

        if (
            k == T_IDENT
            and pos[0] + 1 < len(tokens)
            and tokens[pos[0] + 1][0] == T_EQUALS
        ):
            key = v
            pos[0] += 2
            node.props[key] = _parse_value(tokens, pos)
            continue

        node.args.append(_parse_value(tokens, pos))

    return node


def _parse_value(tokens: list[tuple[str, Any]], pos: list[int]) -> Any:
    k, v = tokens[pos[0]]
    if k in (T_STRING, T_NUMBER, T_BOOL, T_NULL):
        pos[0] += 1
        return v
    if k == T_IDENT:
        pos[0] += 1
        return v
    raise ValueError(f"Expected value at {pos[0]}, got {k} ({v!r})")


# ---------------------------------------------------------------------------
# Serialize: dict IR → markup text
# ---------------------------------------------------------------------------


def serialize_ir(spec: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"version {_emit_value(spec['version'])}")
    lines.append(f"root {_emit_value(spec['root'])}")
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
    header_parts = [f"element {_emit_value(eid)}"]

    children_list: list[str] | None = None
    nested: list[tuple[str, dict[str, Any]]] = []
    scalar_props: list[tuple[str, Any]] = []

    for key, val in element.items():
        if key == "children" and isinstance(val, list):
            children_list = val
        elif isinstance(val, dict):
            nested.append((key, val))
        else:
            scalar_props.append((key, val))

    for key, val in scalar_props:
        header_parts.append(f"{key}={_emit_value(val)}")

    has_body = children_list is not None or nested
    if not has_body:
        return [f"{pad}{' '.join(header_parts)}"]

    out = [f"{pad}{' '.join(header_parts)} {{"]
    inner = "  " * (indent + 1)

    if children_list is not None:
        if children_list:
            args = " ".join(_emit_value(c) for c in children_list)
            out.append(f"{inner}children {args}")
        else:
            out.append(f"{inner}children")

    for nested_key, nested_val in nested:
        out.extend(_emit_nested(nested_key, nested_val, indent + 1))

    out.append(f"{pad}}}")
    return out


def _emit_nested(name: str, data: dict[str, Any], indent: int) -> list[str]:
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
        header.append(f"{k}={_emit_value(v)}")

    if not dicts and not lists:
        return [f"{pad}{' '.join(header)}"]

    out = [f"{pad}{' '.join(header)} {{"]
    for nk, nv in dicts:
        out.extend(_emit_nested(nk, nv, indent + 1))
    for nk, nv in lists:
        out.extend(_emit_list(nk, nv, indent + 1))
    out.append(f"{pad}}}")
    return out


def _emit_list(name: str, items: list[Any], indent: int) -> list[str]:
    """A dd-markup list node: `name { _entry ... _entry ... }`.

    Empty list uses a `_list_empty` marker to disambiguate from empty dict.
    """
    pad = "  " * indent
    inner = "  " * (indent + 1)

    if not items:
        return [f"{pad}{name} {{", f"{inner}_list_empty", f"{pad}}}"]

    out = [f"{pad}{name} {{"]
    for item in items:
        if isinstance(item, dict):
            out.extend(_emit_nested("_entry", item, indent + 1))
        elif isinstance(item, list):
            out.extend(_emit_list("_entry", item, indent + 1))
        else:
            out.append(f"{inner}_entry {_emit_value(item)}")
    out.append(f"{pad}}}")
    return out


def _emit_tokens_block(tokens: dict[str, Any]) -> list[str]:
    if not tokens:
        return ["tokens {}"]
    raise NotImplementedError("Non-empty token maps not yet supported")


def _emit_nid_map_block(nid_map: dict[str, int]) -> list[str]:
    if not nid_map:
        return ["_node_id_map {}"]
    out = ["_node_id_map {"]
    for eid, nid in nid_map.items():
        out.append(f"  map {_emit_value(eid)} {_emit_value(nid)}")
    out.append("}")
    return out


def _emit_value(value: Any) -> str:
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
        )
        return f'"{escaped}"'
    raise ValueError(f"Cannot serialize value of type {type(value).__name__}: {value!r}")


# ---------------------------------------------------------------------------
# Parse: markup text → dict IR
# ---------------------------------------------------------------------------


def parse_dd(source: str) -> dict[str, Any]:
    tokens = _tokenize(source)
    ast = _parse_document(tokens)

    spec: dict[str, Any] = {}
    for node in ast:
        if node.name == "version":
            spec["version"] = node.args[0]
        elif node.name == "root":
            spec["root"] = node.args[0]
        elif node.name == "elements":
            spec["elements"] = _parse_elements_block(node)
        elif node.name == "tokens":
            spec["tokens"] = _parse_tokens_block(node)
        elif node.name == "_node_id_map":
            spec["_node_id_map"] = _parse_nid_map_block(node)
        else:
            raise ValueError(f"Unknown top-level node {node.name!r}")
    return spec


def _parse_elements_block(node: _Node) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for child in node.children:
        if child.name != "element":
            raise ValueError(f"Expected 'element' inside elements, got {child.name!r}")
        if not child.args:
            raise ValueError("element node missing eid arg")
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
    """Convert a KDL AST node into a dict or list.

    Detects list-nodes: if all children are named `_entry` OR a single
    `_list_empty` marker child is present, the node represents a list.
    """
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
    """A `_entry` node: args for scalars, props+children for dicts."""
    if entry.args and not entry.props and not entry.children:
        return entry.args[0] if len(entry.args) == 1 else list(entry.args)
    return _ast_to_nested(entry)


def _parse_tokens_block(node: _Node) -> dict[str, Any]:
    if node.children:
        raise NotImplementedError("Non-empty token maps not yet supported")
    return {}


def _parse_nid_map_block(node: _Node) -> dict[str, int]:
    result: dict[str, int] = {}
    for child in node.children:
        if child.name != "map":
            raise ValueError(f"Expected 'map' inside _node_id_map, got {child.name!r}")
        if len(child.args) != 2:
            raise ValueError(f"map expected 2 args, got {child.args!r}")
        result[child.args[0]] = child.args[1]
    return result
