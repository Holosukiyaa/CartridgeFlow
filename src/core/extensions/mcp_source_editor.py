"""Safe structured edits for protocol-transparent MCP Python source files."""

from __future__ import annotations

import ast
import hashlib
import json
import pprint
import re
import uuid
from pathlib import Path
from typing import Any

from .mcp_source_parser import parse_mcp_python_source


class McpSourceEditError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


OPERATION_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GRAPH_FIELDS = {"operations", "edges", "fallbacks", "capabilities", "inputs", "outputs"}


def edit_mcp_source_graph(
    source: str,
    *,
    expected_source_digest: str,
    graph: dict[str, Any],
) -> tuple[str, dict]:
    model = _load_editable_model(source, expected_source_digest)
    if not isinstance(graph, dict):
        raise McpSourceEditError("MCP_GRAPH_INVALID", "operation graph must be an object")
    unknown = sorted(set(graph) - GRAPH_FIELDS)
    if unknown:
        raise McpSourceEditError("MCP_GRAPH_FIELD_UNSUPPORTED", f"unsupported operation graph fields: {', '.join(unknown)}")

    node_data, tree = _node_literal(source)
    next_node = dict(node_data)
    for field in GRAPH_FIELDS:
        if field not in graph:
            continue
        value = graph[field]
        if field in {"operations", "edges", "fallbacks"} and (
            not isinstance(value, list) or any(not isinstance(item, dict) for item in value)
        ):
            raise McpSourceEditError("MCP_GRAPH_FIELD_INVALID", f"{field} must be an array of objects")
        if field == "capabilities" and (
            not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise McpSourceEditError("MCP_GRAPH_FIELD_INVALID", "capabilities must be an array of non-empty strings")
        if field in {"inputs", "outputs"} and not isinstance(value, dict):
            raise McpSourceEditError("MCP_GRAPH_FIELD_INVALID", f"{field} must be an object")
        next_node[field] = value

    updated_source = _replace_ast_value(source, tree, "MCP_NODE", next_node)
    return _validate_edited_source(updated_source, model["node_id"])


def add_mcp_operation(
    source: str,
    *,
    expected_source_digest: str,
    operation: dict[str, Any],
) -> tuple[str, dict]:
    model = _load_editable_model(source, expected_source_digest)
    if not isinstance(operation, dict):
        raise McpSourceEditError("MCP_OPERATION_INVALID", "operation must be an object")
    operation_id = str(operation.get("id") or "").strip()
    if not OPERATION_ID_RE.fullmatch(operation_id):
        raise McpSourceEditError("MCP_OPERATION_ID_INVALID", "operation.id must be a valid Python identifier")
    if any(str(item.get("id") or "") == operation_id for item in model.get("operations") or []):
        raise McpSourceEditError("MCP_OPERATION_EXISTS", f"operation already exists: {operation_id}")

    node_data, tree = _node_literal(source)
    next_node = dict(node_data)
    next_node["operations"] = [*(node_data.get("operations") or []), dict(operation, id=operation_id)]
    updated_source = _replace_ast_value(source, tree, "MCP_NODE", next_node)

    operations_assignment = _find_assignment(ast.parse(updated_source), "OPERATIONS")
    if operations_assignment is None or not isinstance(operations_assignment.value, ast.Dict):
        raise McpSourceEditError("MCP_OPERATIONS_NOT_STATIC", "OPERATIONS must be a static dict literal")
    operations_map = _literal_dict(operations_assignment.value)
    operations_map[operation_id] = f"op_{operation_id}"
    updated_source = _replace_ast_value(
        updated_source,
        ast.parse(updated_source),
        "OPERATIONS",
        operations_map,
        renderer=_render_operations_mapping,
    )

    tree_after_registry = ast.parse(updated_source)
    operations_assignment = _find_assignment(tree_after_registry, "OPERATIONS")
    if operations_assignment is None:
        raise McpSourceEditError("MCP_OPERATIONS_NOT_STATIC", "OPERATIONS declaration is required")
    insertion_offset = _byte_offset(updated_source, operations_assignment.lineno, operations_assignment.col_offset)
    stub = (
        f'@mcp_operation("{operation_id}")\n'
        f"def op_{operation_id}(ctx: McpContext, data: dict) -> dict:\n"
        "    return data\n\n\n"
    ).encode("utf-8")
    raw = updated_source.encode("utf-8")
    updated_source = (raw[:insertion_offset] + stub + raw[insertion_offset:]).decode("utf-8")
    return _validate_edited_source(updated_source, model["node_id"])


def _load_editable_model(source: str, expected_source_digest: str) -> dict:
    model = parse_mcp_python_source(source)
    if not model.get("ok"):
        raise McpSourceEditError("MCP_SOURCE_INVALID", "source must pass the protocol static parser before editing")
    expected = str(expected_source_digest or "").strip().lower()
    actual = str(model.get("source_digest") or "").strip().lower()
    if not expected:
        raise McpSourceEditError("MCP_SOURCE_DIGEST_REQUIRED", "expected_source_digest is required")
    if expected != actual:
        raise McpSourceEditError("MCP_SOURCE_DIGEST_CONFLICT", "source changed since the editor loaded it")
    return model


def _validate_edited_source(source: str, node_id: str) -> tuple[str, dict]:
    model = parse_mcp_python_source(source)
    if model.get("node_id") != node_id:
        raise McpSourceEditError("MCP_NODE_ID_CHANGED", "structured editing cannot change MCP_NODE.node_id")
    if not model.get("ok"):
        codes = ", ".join(str(item.get("code")) for item in model.get("findings") or [])
        raise McpSourceEditError("MCP_SOURCE_EDIT_INVALID", f"edited source failed static validation: {codes}")
    return source, model


def _node_literal(source: str) -> tuple[dict, ast.Module]:
    tree = ast.parse(source)
    assignment = _find_assignment(tree, "MCP_NODE")
    if assignment is None:
        raise McpSourceEditError("MCP_NODE_MISSING", "MCP_NODE declaration is required")
    try:
        value = ast.literal_eval(assignment.value)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise McpSourceEditError("MCP_NODE_NOT_STATIC", "MCP_NODE must be a static literal") from exc
    if not isinstance(value, dict):
        raise McpSourceEditError("MCP_NODE_NOT_OBJECT", "MCP_NODE must be an object literal")
    return value, tree


def _replace_ast_value(source: str, tree: ast.Module, name: str, value: Any, *, renderer=None) -> str:
    assignment = _find_assignment(tree, name)
    if assignment is None:
        raise McpSourceEditError("MCP_DECLARATION_MISSING", f"{name} declaration is required")
    rendered = renderer(value) if renderer else pprint.pformat(value, sort_dicts=False, width=100)
    raw = source.encode("utf-8")
    start = _byte_offset(source, assignment.value.lineno, assignment.value.col_offset)
    end = _byte_offset(source, assignment.value.end_lineno, assignment.value.end_col_offset)
    return (raw[:start] + rendered.encode("utf-8") + raw[end:]).decode("utf-8")


def _find_assignment(tree: ast.Module, name: str) -> ast.Assign | ast.AnnAssign | None:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return node
    return None


def _literal_dict(node: ast.Dict) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str) or not isinstance(value, ast.Name):
            raise McpSourceEditError("MCP_OPERATIONS_NOT_STATIC", "OPERATIONS keys and values must be static names")
        result[key.value] = value.id
    return result


def _render_operations_mapping(value: dict[str, str]) -> str:
    lines = ["{"]
    for operation_id, function_name in value.items():
        if not OPERATION_ID_RE.fullmatch(operation_id) or not OPERATION_ID_RE.fullmatch(str(function_name)):
            raise McpSourceEditError("MCP_OPERATIONS_NOT_STATIC", "OPERATIONS keys and values must be static names")
        lines.append(f'    "{operation_id}": {function_name},')
    lines.append("}")
    return "\n".join(lines)


def _byte_offset(source: str, line: int, column: int) -> int:
    lines = source.splitlines(keepends=True)
    return len("".join(lines[: line - 1]).encode("utf-8")) + len(lines[line - 1][:column].encode("utf-8"))


def update_descriptor_source_digest(
    package_root: str | Path,
    manifest: dict,
    *,
    node_id: str,
    source_model: dict,
) -> dict:
    portable = manifest.get("portable_dlc") if isinstance(manifest.get("portable_dlc"), dict) else {}
    descriptor_ref = str(portable.get("descriptor") or "").replace("\\", "/")
    descriptor_path = _resolve_package_path(Path(package_root), descriptor_ref)
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    matching_tool = next(
        (
            item for item in descriptor.get("tools") or []
            if isinstance(item, dict) and str(item.get("node_id") or "") == node_id
        ),
        None,
    )
    if matching_tool is None:
        raise McpSourceEditError("MCP_DESCRIPTOR_TOOL_NOT_FOUND", f"descriptor tool not found: {node_id}")
    entry = str((matching_tool.get("implementation") or {}).get("entry") or "").replace("\\", "/")
    source_path = _resolve_package_path(Path(package_root), entry)
    digest = str(source_model.get("source_digest") or "")
    matching_tool["source_digest"] = digest
    for file_item in descriptor.get("files") or []:
        if isinstance(file_item, dict) and str(file_item.get("path") or "").replace("\\", "/") == entry:
            file_item["sha256"] = _sha256_file(source_path)
    _atomic_write_bytes(descriptor_path, (json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    for tool in manifest.get("mcp_tools") or []:
        if not isinstance(tool, dict):
            continue
        if str(tool.get("node_id") or "") == node_id or (
            str(tool.get("server") or "") == str(matching_tool.get("server") or "")
            and str(tool.get("tool") or "") == str(matching_tool.get("tool") or "")
        ):
            tool["source_digest"] = digest
    return {"descriptor": descriptor, "entry": entry, "source_digest": digest}


def _resolve_package_path(package_root: Path, relative: str) -> Path:
    value = str(relative or "").strip().replace("\\", "/")
    if not value or Path(value).is_absolute():
        raise McpSourceEditError("MCP_SOURCE_PATH_INVALID", "source path must be package-relative")
    root = package_root.resolve()
    path = (root / value).resolve()
    if path != root and root not in path.parents:
        raise McpSourceEditError("MCP_SOURCE_PATH_INVALID", "source path escapes the cartridge package")
    if not path.is_file():
        raise McpSourceEditError("MCP_SOURCE_NOT_FOUND", f"source file not found: {value}")
    return path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
