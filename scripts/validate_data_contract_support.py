from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from core.protocol import DataContractError, build_data_contract_support_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail unless Base has exact, implemented, positive/failure-tested support for every active data contract."
    )
    parser.add_argument("--json", action="store_true", help="Print the complete machine-readable report.")
    args = parser.parse_args()
    try:
        report = build_data_contract_support_report(ROOT)
    except (DataContractError, OSError, ValueError) as exc:
        print(f"Data contract support validation failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["ok"]:
        summary = report["summary"]
        print(
            "Data contract support validation passed: "
            f"{summary['supported_releases']}/{summary['active_releases']} active releases supported."
        )
    else:
        print("Data contract support validation failed:")
        print("\n".join(f"- [{item['code']}] {item['message']}" for item in report["findings"]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
