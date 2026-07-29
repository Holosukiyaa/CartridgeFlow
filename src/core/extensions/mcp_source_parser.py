from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any


SOURCE_MODEL_SCHEMA = "cartridgeflow.mcp_source_model.v1"
SOURCE_FORMAT = "cartridgeflow.mcp_python.v1"
TRANSPARENCY_LEVELS = {"atomic", "declared_graph", "contract_only", "opaque", "legacy_opaque"}

_FORBIDDEN_IMPORTS = {
    "aiohttp", "builtins", "ctypes", "http", "http.client", "httpx", "importlib",
    "multiprocessing", "os", "pathlib", "requests", "shutil", "socket", "subprocess",
    "tempfile", "urllib", "urllib.request",
}
_FORBIDDEN_CALL_NAMES = {"eval", "exec", "compile", "__import__", "open"}
_FORBIDDEN_ATTRIBUTE_NAMES = {
    "Popen", "check_call", "check_output", "chmod", "chown", "execv", "execve",
    "mkdir", "popen", "rename", "replace", "rmdir", "run", "socket", "symlink_to",
    "system", "touch", "unlink", "urlopen", "write_bytes", "write_text",
}


def parse_mcp_python_file(path: str | Path, *, display_path: str | None = None) -> dict:
    """Parse a DLC MCP source file without importing or executing it."""
    source_path = Path(path)
    visible_path = display_path or source_path.as_posix()
    try:
        raw = source_path.read_bytes()
    except OSError as exc:
        return _empty_model(visible_path, "MCP_SOURCE_READ_FAILED", str(exc))
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _empty_model(visible_path, "MCP_SOURCE_UTF8_INVALID", f"source is not valid UTF-8: {exc}")
    return parse_mcp_python_source(source, display_path=visible_path)


def parse_mcp_python_source(source: str, *, display_path: str = "<memory>") -> dict:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    model = _empty_model(display_path, None, None, digest=digest, line_count=source.count("\n") + 1)
    try:
        tree = ast.parse(source, filename=display_path, mode="exec")
    except SyntaxError as exc:
        _add_finding(model, "blocker", "MCP_SOURCE_SYNTAX_INVALID", f"{exc.msg} at line {exc.lineno}", exc.lineno)
        return _finish(model)

    mcp_assignments = [
        node for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and _defines_name(node, "MCP_NODE")
    ]
    if len(mcp_assignments) != 1:
        _add_finding(model, "blocker", "MCP_NODE_COUNT_INVALID", f"expected exactly one MCP_NODE declaration, found {len(mcp_assignments)}")
        return _finish(model)

    node_assignment = mcp_assignments[0]
    node_value = node_assignment.value
    try:
        node_data = ast.literal_eval(node_value)
    except (ValueError, TypeError, SyntaxError):
        _add_finding(model, "blocker", "MCP_NODE_NOT_STATIC", "MCP_NODE must be a static literal", node_value.lineno)
        return _finish(model)
    if not isinstance(node_data, dict):
        _add_finding(model, "blocker", "MCP_NODE_NOT_OBJECT", "MCP_NODE must be an object literal", node_value.lineno)
        return _finish(model)

    model["node_id"] = _string_value(node_data.get("node_id"))
    model["tool_identity"] = _tool_identity(node_data)
    model["format"] = _string_value(node_data.get("schema"))
    model["source_map"]["mcp_node"] = _location(node_assignment, display_path, "MCP_NODE")
    if model["format"] != SOURCE_FORMAT:
        _add_finding(model, "blocker", "MCP_SOURCE_FORMAT_UNSUPPORTED", f"expected {SOURCE_FORMAT}", node_value.lineno)
    if not model["node_id"]:
        _add_finding(model, "blocker", "MCP_NODE_ID_MISSING", "MCP_NODE.node_id is required", node_value.lineno)
    if not model["tool_identity"]:
        _add_finding(model, "blocker", "MCP_TOOL_IDENTITY_MISSING", "MCP_NODE.server and MCP_NODE.tool are required", node_value.lineno)

    model["operations"] = _normalize_operations(_static_list(node_data, "operations", model), model, node_value.lineno)
    model["edges"] = _normalize_edges(_static_list(node_data, "edges", model), model, node_value.lineno)
    model["fallbacks"] = _normalize_fallbacks(_static_list(node_data, "fallbacks", model), model, node_value.lineno)
    model["inputs"] = dict(node_data.get("inputs") or {}) if isinstance(node_data.get("inputs"), dict) else {}
    model["outputs"] = dict(node_data.get("outputs") or {}) if isinstance(node_data.get("outputs"), dict) else {}
    model["capabilities"] = _collect_capabilities(model["operations"], node_data.get("capabilities"))

    function_map = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    decorated_operations = _decorated_operations(tree, model)
    declared_ids = {item["id"] for item in model["operations"] if item.get("id")}
    decorated_ids = set(decorated_operations)
    for operation_id in sorted(declared_ids - decorated_ids):
        _add_finding(model, "blocker", "MCP_OPERATION_DECORATOR_MISSING", f"operation is not decorated: {operation_id}")
    for operation_id in sorted(decorated_ids - declared_ids):
        _add_finding(model, "blocker", "MCP_OPERATION_UNDECLARED", f"decorated operation is not declared: {operation_id}")

    operation_map = _static_operations_mapping(_find_assignment(tree, "OPERATIONS"), model)
    if operation_map is not None:
        for operation_id in sorted(declared_ids - set(operation_map)):
            _add_finding(model, "blocker", "MCP_OPERATION_REGISTRY_MISSING", f"OPERATIONS is missing: {operation_id}")
        for operation_id in sorted(set(operation_map) - declared_ids):
            _add_finding(model, "blocker", "MCP_OPERATION_REGISTRY_EXTRA", f"OPERATIONS contains undeclared operation: {operation_id}")
        for operation_id, function_name in operation_map.items():
            expected_name = f"op_{operation_id}"
            if function_name != expected_name:
                _add_finding(model, "blocker", "MCP_OPERATION_FUNCTION_NAME_INVALID", f"{operation_id} must map to {expected_name}")
            function = function_map.get(function_name)
            if function is None:
                _add_finding(model, "blocker", "MCP_OPERATION_FUNCTION_MISSING", f"function not found: {function_name}")
            else:
                model["source_map"][f"operation:{operation_id}"] = _location(function, display_path, function_name)

    _validate_run_function(function_map.get("run"), model)
    _validate_forbidden_constructs(tree, model)
    return _finish(model)


def _empty_model(display_path: str, code: str | None, message: str | None = None, *, digest: str = "", line_count: int = 0) -> dict:
    model = {
        "schema": SOURCE_MODEL_SCHEMA,
        "node_id": None,
        "tool_identity": None,
        "format": None,
        "source": {"path": display_path.replace("\\", "/"), "sha256": digest, "line_count": line_count},
        "operations": [],
        "edges": [],
        "data_relations": [],
        "fallbacks": [],
        "inputs": {},
        "outputs": {},
        "capabilities": [],
        "source_map": {},
        "findings": [],
        "source_digest": f"sha256:{digest}" if digest else "",
    }
    if code:
        _add_finding(model, "blocker", code, message or code)
    return model


def _finish(model: dict) -> dict:
    model["ok"] = not any(item.get("severity") == "blocker" for item in model["findings"])
    return model


def _add_finding(model: dict, severity: str, code: str, message: str, line: int | None = None) -> None:
    item = {"id": f"finding:{code}:{model['source']['path']}", "severity": severity, "code": code, "message": message}
    if line:
        item["line"] = line
    model["findings"].append(item)


def _defines_name(node: ast.Assign | ast.AnnAssign, name: str) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return any(isinstance(target, ast.Name) and target.id == name for target in targets)


def _find_assignment(tree: ast.Module, name: str) -> ast.Assign | ast.AnnAssign | None:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and _defines_name(node, name):
            return node
    return None


def _static_list(data: dict, key: str, model: dict) -> list:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        _add_finding(model, "blocker", f"MCP_NODE_{key.upper()}_NOT_STATIC", f"MCP_NODE.{key} must be a static list of objects")
        return []
    return value


def _normalize_operations(items: list, model: dict, line: int) -> list[dict]:
    result = []
    seen = set()
    for item in items:
        operation_id = _string_value(item.get("id"))
        if not operation_id or operation_id in seen:
            _add_finding(model, "blocker", "MCP_OPERATION_ID_INVALID", "operation ids must be unique non-empty strings", line)
            continue
        seen.add(operation_id)
        result.append(dict(item, id=operation_id))
    return result


def _normalize_edges(items: list, model: dict, line: int) -> list[dict]:
    result = []
    operation_ids = set()
    for item in model["operations"]:
        if item.get("id"):
            operation_ids.add(item["id"])
    for item in items:
        source = _string_value(item.get("from"))
        target = _string_value(item.get("to"))
        kind = _string_value(item.get("kind"))
        if not source or not target or kind != "control":
            _add_finding(model, "blocker", "MCP_OPERATION_EDGE_INVALID", "operation edges require from, to and kind=control", line)
            continue
        if operation_ids and (source not in operation_ids or target not in operation_ids):
            _add_finding(model, "blocker", "MCP_OPERATION_EDGE_TARGET_MISSING", f"edge references missing operation: {source}->{target}", line)
        result.append(dict(item))
    return result


def _normalize_fallbacks(items: list, model: dict, line: int) -> list[dict]:
    result = []
    seen = set()
    for item in items:
        fallback_id = _string_value(item.get("id"))
        if not fallback_id or fallback_id in seen:
            _add_finding(model, "blocker", "MCP_FALLBACK_ID_INVALID", "fallback ids must be unique non-empty strings", line)
            continue
        seen.add(fallback_id)
        if item.get("visible") is not True:
            _add_finding(model, "blocker", "MCP_FALLBACK_NOT_VISIBLE", f"fallback must be visible: {fallback_id}", line)
        result.append(dict(item))
    return result


def _decorated_operations(tree: ast.Module, model: dict) -> dict[str, str]:
    result = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Name) or decorator.func.id != "mcp_operation":
                continue
            if len(decorator.args) != 1 or not isinstance(decorator.args[0], ast.Constant) or not isinstance(decorator.args[0].value, str):
                _add_finding(model, "blocker", "MCP_OPERATION_DECORATOR_NOT_STATIC", f"decorator on {node.name} must contain one static id", decorator.lineno)
                continue
            operation_id = decorator.args[0].value
            if operation_id in result:
                _add_finding(model, "blocker", "MCP_OPERATION_DUPLICATE_DECORATOR", f"duplicate decorator: {operation_id}", decorator.lineno)
            result[operation_id] = node.name
    return result


def _static_operations_mapping(assignment: ast.Assign | ast.AnnAssign | None, model: dict) -> dict[str, str] | None:
    if assignment is None:
        _add_finding(model, "blocker", "MCP_OPERATIONS_MISSING", "OPERATIONS declaration is required")
        return None
    if not isinstance(assignment.value, ast.Dict):
        _add_finding(model, "blocker", "MCP_OPERATIONS_NOT_STATIC", "OPERATIONS must be a static dict literal", assignment.value.lineno)
        return None
    result = {}
    for key, value in zip(assignment.value.keys, assignment.value.values):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str) or not isinstance(value, ast.Name):
            _add_finding(model, "blocker", "MCP_OPERATIONS_NOT_STATIC", "OPERATIONS keys and values must be static names", assignment.value.lineno)
            continue
        result[key.value] = value.id
    return result


def _validate_run_function(function: ast.FunctionDef | ast.AsyncFunctionDef | None, model: dict) -> None:
    if function is None:
        _add_finding(model, "blocker", "MCP_RUN_FUNCTION_MISSING", "run(ctx, inputs) is required")
        return
    if len(function.body) != 1 or not isinstance(function.body[0], ast.Return):
        _add_finding(model, "blocker", "MCP_RUN_NOT_STANDARD_GRAPH_RUNNER", "run() must only return ctx.run_declared_graph(...)", function.lineno)
        return
    value = function.body[0].value
    if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute) or value.func.attr != "run_declared_graph":
        _add_finding(model, "blocker", "MCP_RUN_NOT_STANDARD_GRAPH_RUNNER", "run() must only return ctx.run_declared_graph(...)", function.lineno)


def _validate_forbidden_constructs(tree: ast.Module, model: dict) -> None:
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for name in names:
            if name in _FORBIDDEN_IMPORTS or any(name.startswith(f"{prefix}.") for prefix in _FORBIDDEN_IMPORTS):
                _add_finding(model, "blocker", "MCP_DIRECT_CAPABILITY_IMPORT", f"direct capability import is forbidden: {name}", node.lineno)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALL_NAMES:
                _add_finding(model, "blocker", "MCP_DIRECT_CAPABILITY_CALL", f"direct capability call is forbidden: {node.func.id}", node.lineno)
            if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_ATTRIBUTE_NAMES:
                _add_finding(model, "blocker", "MCP_DIRECT_CAPABILITY_CALL", f"direct capability call is forbidden: {node.func.attr}", node.lineno)


def _collect_capabilities(operations: list[dict], declared: Any) -> list[str]:
    result = []
    candidates = declared if isinstance(declared, list) else []
    for item in [*candidates, *[operation.get("capability") for operation in operations]]:
        value = _string_value(item)
        if value and value not in result:
            result.append(value)
    return result


def _tool_identity(data: dict) -> str | None:
    server = _string_value(data.get("server"))
    tool = _string_value(data.get("tool"))
    return f"{server}/{tool}" if server and tool else None


def _string_value(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _location(node: ast.AST, path: str, symbol: str) -> dict:
    return {
        "path": path.replace("\\", "/"),
        "symbol": symbol,
        "start_line": int(getattr(node, "lineno", 1)),
        "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
    }
