from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import json
import sys
from pathlib import Path


def _run_transparent_tool(package: Path, tool: dict, request: dict) -> dict:
    implementation = tool.get("implementation") if isinstance(tool.get("implementation"), dict) else {}
    entry = str(implementation.get("entry") or "").replace("\\", "/")
    source = (package / entry).resolve()
    if not entry or (source != package and package not in source.parents) or not source.is_file():
        return {"ok": False, "code": "dlc_implementation_missing", "error": "Transparent DLC implementation is unavailable"}
    module_name = f"_cartridgeflow_dlc_{abs(hash((str(source), request.get('request_id'))))}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        return {"ok": False, "code": "dlc_implementation_invalid", "error": "Transparent DLC implementation cannot be loaded"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, "run", None)
    if not callable(handler):
        return {"ok": False, "code": "dlc_handler_invalid", "error": "Transparent DLC implementation must define run(ctx, inputs)"}
    from cartridgeflow_dlc import McpContext

    return handler(McpContext(request=request, tool=tool), request.get("params") or {})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--descriptor", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    package = Path(args.package).resolve()
    descriptor_path = Path(args.descriptor).resolve()
    # Base owns the SDK. A package must not be able to shadow it with a file
    # placed at the DLC root.
    sys.path.insert(0, str(workspace / "src"))

    request = json.loads((sys.stdin.buffer.read() or b"{}").decode("utf-8"))
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    server = str(request.get("server") or "")
    tool_name = str(request.get("tool") or "")
    tool = next(
        (item for item in descriptor.get("tools") or [] if item.get("server") == server and item.get("tool") == tool_name),
        None,
    )
    if not tool:
        result = {"ok": False, "code": "dlc_tool_not_declared", "error": f"Tool not declared: {server}/{tool_name}"}
    elif (
        str(tool.get("handler") or "") == "run"
        and isinstance(tool.get("implementation"), dict)
        and tool["implementation"].get("format") == "cartridgeflow.mcp_python.v1"
    ):
        try:
            with contextlib.redirect_stdout(sys.stderr):
                result = _run_transparent_tool(package, tool, request)
            if not isinstance(result, dict):
                raise TypeError("DLC handler must return an object")
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "dlc_handler_failed")
            result = {
                "ok": False,
                "code": code,
                "error": str(exc) if code != "dlc_handler_failed" else f"{type(exc).__name__}: {exc}",
            }
            operation_id = str(getattr(exc, "operation_id", "") or "")
            if operation_id:
                result["operation_id"] = operation_id
    else:
        module_name, separator, function_name = str(tool.get("handler") or "").partition(":")
        if not separator or not module_name or not function_name:
            result = {"ok": False, "code": "dlc_handler_invalid", "error": "DLC handler must use module:function"}
        else:
            try:
                # Legacy module:function handlers still resolve modules from
                # the package. Transparent graph handlers never receive this
                # path and can only import the Base-owned SDK or stdlib.
                sys.path.insert(1, str(package / "dlc"))
                module = importlib.import_module(module_name)
                handler = getattr(module, function_name)
                with contextlib.redirect_stdout(sys.stderr):
                    result = handler({**request, "workspace_root": str(workspace), "package_path": str(package)})
                if not isinstance(result, dict):
                    raise TypeError("DLC handler must return an object")
            except Exception as exc:
                result = {"ok": False, "code": "dlc_handler_failed", "error": f"{type(exc).__name__}: {exc}"}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
