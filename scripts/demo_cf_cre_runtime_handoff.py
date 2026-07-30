"""Build and stage a CF-CRE@1 release candidate for runtime integration demos."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.protocol import ReleaseBuildError, build_release_archive, inspect_release_archive


def main() -> int:
    parser = argparse.ArgumentParser(description="构建并暂存验证 CF-CRE@1 发行候选包")
    parser.add_argument("--source", required=True, help="开发卡带目录")
    parser.add_argument("--output", required=True, help="候选包 .zip 输出路径")
    parser.add_argument("--publisher", default="demo.publisher", help="稳定发布者 ID")
    parser.add_argument("--product-name", default="每日摘要演示", help="公开产品名称")
    args = parser.parse_args()
    experience = {
        "schema": "cartridgeflow.cartridge_experience.v1",
        "product": {"name": args.product_name, "category": "content"},
        "inputs": [{"id": "topic", "label": "主题", "type": "string", "required": True, "sensitive": False}],
        "stages": [{"id": "prepare", "label": "准备内容"}, {"id": "deliver", "label": "交付摘要"}],
    }
    delivery = {
        "schema": "cartridgeflow.delivery_contract.v1",
        "primary_artifacts": [{"id": "daily_brief", "label": "每日摘要", "mime_types": ["text/markdown"]}],
        "attachments": [],
        "revision": {"mode": "new_run"},
        "delivery_states": ["produced", "delivered", "failed"],
    }
    try:
        built = build_release_archive(args.source, args.output, publisher_id=args.publisher, experience=experience, delivery=delivery)
    except ReleaseBuildError as exc:
        print(json.dumps({"ok": False, "stage": "build_rejected", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    staged = inspect_release_archive(args.output)
    result = {
        "ok": staged["report"]["ok"],
        "stage": staged["status"],
        "activation_allowed": staged["activation_allowed"],
        "release_id": built["release_id"],
        "archive": built["archive"],
        "public_contracts": staged["public_contracts"],
        "findings": staged["report"]["findings"],
        "next_required_step": "验签、兼容性检查、资源重绑定和原子激活尚未实现；不得把该候选包安装或运行。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
