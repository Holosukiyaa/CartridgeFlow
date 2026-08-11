from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import DataContractError, build_clean_protocol_support_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail unless Base supports the complete clean-v1 four-layer protocol generation."
    )
    parser.add_argument("--registry", type=Path, help="Override the product registry for staging.")
    parser.add_argument("--json", action="store_true", help="Print the complete report.")
    args = parser.parse_args()
    try:
        report = build_clean_protocol_support_report(
            ROOT,
            registry_path=args.registry.resolve() if args.registry else None,
        )
    except (DataContractError, OSError, ValueError) as exc:
        print(f"Clean protocol validation failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["ok"]:
        summary = report["summary"]
        print(
            "Clean protocol validation passed: "
            f"{summary['protocols']} layers, {summary['contracts']} contracts."
        )
    else:
        print("Clean protocol validation failed:")
        print("\n".join(f"- [{item['code']}] {item['message']}" for item in report["findings"]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
