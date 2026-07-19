from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--descriptor", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    package = Path(args.package).resolve()
    descriptor_path = Path(args.descriptor).resolve()
    sys.path.insert(0, str(workspace))
    sys.path.insert(0, str(package / "dlc"))

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
    else:
        module_name, separator, function_name = str(tool.get("handler") or "").partition(":")
        if not separator or not module_name or not function_name:
            result = {"ok": False, "code": "dlc_handler_invalid", "error": "DLC handler must use module:function"}
        else:
            try:
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
