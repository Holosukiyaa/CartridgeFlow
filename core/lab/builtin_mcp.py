"""内置 MCP 服务注册表。

提供无需外部 MCP 服务器即可使用的内置工具，
节点 tools 字段中 type="builtin" 的工具从这里分发执行。

当前内置服务：
- filesystem: read_file, write_file, list_dir, exists
- media: probe, extract_keyframes, style_keyframes, remote_upgrade_keyframes, qc_outputs, generate_short_video, generate_pixel_shot_plan, check_pixel_assets, comfyui_generate_asset, forge_pixel_asset_batch, update_pixel_world_state, godot_render_pixel_episode, ffmpeg_mux_episode
"""

import html
import base64
from copy import deepcopy
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
import zlib
from pathlib import Path




class BuiltinMcpRegistry:
    """??????????????? DLC ?????"""

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        *,
        package_path: str | Path | None = None,
        manifest: dict | None = None,
        protocol_extensions=None,
        capabilities=None,
        supported_protocols=None,
    ):
        self._workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self._package_path = Path(package_path).resolve() if package_path else None
        self._manifest = manifest if isinstance(manifest, dict) else {}
        self._protocol_extensions = protocol_extensions
        self._capabilities = capabilities
        self._supported_protocols = supported_protocols
        self._registry: dict[str, dict[str, callable]] = {}
        self._tool_dlc: dict[str, dict] = {}
        self._extension_tool_descriptions: dict[tuple[str, str], dict] = {}
        self._package_dlc_descriptor: dict | None = None
        self._dlc_report: list[dict] = []
        self._register_filesystem()
        self._register_media()
        self._register_package_dlc()

    @classmethod
    def for_manifest(
        cls,
        workspace_root: str | Path | None,
        manifest: dict,
        capabilities=None,
        supported_protocols=None,
        package_path: str | Path | None = None,
    ):
        """Build an explicitly scoped registry for one cartridge manifest.

        Ordinary callers should keep using ``BuiltinMcpRegistry(root)``. This
        factory is the only supported path for a future companion protocol to
        receive a manifest extension declaration.
        """
        manifest = manifest if isinstance(manifest, dict) else {}
        return cls(
            workspace_root,
            package_path=package_path,
            manifest=manifest,
            protocol_extensions=manifest.get("protocol_extensions") or [],
            capabilities=capabilities,
            supported_protocols=supported_protocols,
        )

    def _register_package_dlc(self):
        from core.extensions import register_package_dlc

        register_package_dlc(self, self._package_path, self._manifest)
    def _safe_path(self, path_str: str) -> Path:
        resolved = (self._workspace_root / path_str).resolve()
        if not str(resolved).startswith(str(self._workspace_root.resolve())):
            raise PermissionError(f"路径越界，不允许访问工作区外的路径：{path_str}")
        return resolved
    def _register_filesystem(self):
        registry = self

        def read_file(params: dict) -> dict:
            path_str = params.get("path") or ""
            if not path_str:
                return {"ok": False, "error": "缺少 path 参数"}
            try:
                path_items = [
                    item.strip()
                    for item in str(path_str).replace("\r", "\n").replace(",", "\n").split("\n")
                    if item.strip()
                ]
                if len(path_items) > 1:
                    chunks = []
                    total_size = 0
                    for item in path_items:
                        target = registry._safe_path(item)
                        if not target.exists():
                            return {"ok": False, "error": f"文件不存在：{item}"}
                        if not target.is_file():
                            return {"ok": False, "error": f"路径不是文件：{item}"}
                        content = target.read_text(encoding="utf-8", errors="replace")
                        total_size += len(content)
                        chunks.append(f"--- FILE: {item} ---\n{content}")
                    return {"ok": True, "path": path_items, "content": "\n\n".join(chunks), "size": total_size, "count": len(path_items)}
                target = registry._safe_path(path_str)
                if not target.exists():
                    return {"ok": False, "error": f"文件不存在：{path_str}"}
                if not target.is_file():
                    return {"ok": False, "error": f"路径不是文件：{path_str}"}
                content = target.read_text(encoding="utf-8", errors="replace")
                return {"ok": True, "path": str(target), "content": content, "size": len(content)}
            except PermissionError as exc:
                return {"ok": False, "error": str(exc)}
            except Exception as exc:
                return {"ok": False, "error": f"读取失败：{exc}"}

        def write_file(params: dict) -> dict:
            path_str = params.get("path") or ""
            content = params.get("content") or ""
            if not path_str:
                return {"ok": False, "error": "缺少 path 参数"}
            try:
                target = registry._safe_path(path_str)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return {"ok": True, "path": str(target), "written": len(content)}
            except PermissionError as exc:
                return {"ok": False, "error": str(exc)}
            except Exception as exc:
                return {"ok": False, "error": f"写入失败：{exc}"}

        def list_dir(params: dict) -> dict:
            path_str = params.get("path") or "."
            try:
                target = registry._safe_path(path_str)
                if not target.exists():
                    return {"ok": False, "error": f"目录不存在：{path_str}"}
                if not target.is_dir():
                    return {"ok": False, "error": f"路径不是目录：{path_str}"}
                entries = []
                for item in sorted(target.iterdir()):
                    entries.append({
                        "name": item.name,
                        "type": "dir" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    })
                return {"ok": True, "path": str(target), "entries": entries, "count": len(entries)}
            except PermissionError as exc:
                return {"ok": False, "error": str(exc)}
            except Exception as exc:
                return {"ok": False, "error": f"列目录失败：{exc}"}

        def exists(params: dict) -> dict:
            path_str = params.get("path") or ""
            if not path_str:
                return {"ok": False, "error": "缺少 path 参数"}
            try:
                target = registry._safe_path(path_str)
                return {"ok": True, "path": str(target), "exists": target.exists(), "is_file": target.is_file(), "is_dir": target.is_dir()}
            except PermissionError as exc:
                return {"ok": False, "error": str(exc)}

        def append_file(params: dict) -> dict:
            path_str = params.get("path") or ""
            content = params.get("content") or ""
            if not path_str:
                return {"ok": False, "error": "缺少 path 参数"}
            try:
                target = registry._safe_path(path_str)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("a", encoding="utf-8") as fh:
                    fh.write(content)
                return {"ok": True, "path": str(target), "appended": len(content)}
            except PermissionError as exc:
                return {"ok": False, "error": str(exc)}
            except Exception as exc:
                return {"ok": False, "error": f"追加写入失败：{exc}"}

        self._registry["filesystem"] = {
            "read_file": read_file,
            "write_file": write_file,
            "list_dir": list_dir,
            "exists": exists,
            "append_file": append_file,
        }
    def _register_media(self):
        from .mcp.dlc import register_media_modules

        self._registry.setdefault("media", {})
        register_media_modules(
            self,
            protocol_extensions=self._protocol_extensions,
            capabilities=self._capabilities,
            supported_protocols=self._supported_protocols,
        )

    def call(self, server: str, tool: str, params: dict) -> dict:
        server_tools = self._registry.get(server)
        if not server_tools:
            return {"ok": False, "error": f"内置服务不存在：{server}，当前支持：{list(self._registry.keys())}"}
        handler = server_tools.get(tool)
        if not handler:
            return {"ok": False, "error": f"内置工具不存在：{server}/{tool}，当前支持：{list(server_tools.keys())}"}
        return handler(params)
    def list_tools(self) -> dict:
        return {server: list(tools.keys()) for server, tools in self._registry.items()}

    def dlc_report(self) -> list[dict]:
        """Return a snapshot of extension loading decisions."""
        return deepcopy(self._dlc_report)

    def describe(self) -> list[dict]:
        descriptions = {
            "filesystem": {
                "read_file": {"description": "读取文件内容", "params": {"path": "相对于工作区的文件路径"}},
                "write_file": {"description": "写入文件（覆盖）", "params": {"path": "文件路径", "content": "写入内容"}},
                "append_file": {"description": "追加写入文件", "params": {"path": "文件路径", "content": "追加内容"}},
                "list_dir": {"description": "列出目录内容", "params": {"path": "目录路径，默认为工作区根目录"}},
                "exists": {"description": "检查路径是否存在", "params": {"path": "路径"}},
            },
            "media": {
                "probe": {
                    "description": "Probe local media providers such as ComfyUI, FFmpeg, Godot, and local Python helpers.",
                    "params": {
                        "providers": "Comma or newline separated provider list: local,ffmpeg,comfyui,godot",
                        "comfyui_url": "ComfyUI base URL, default http://127.0.0.1:8188",
                        "timeout": "Probe timeout in seconds",
                    },
                },
                "extract_keyframes": {
                    "description": "Extract a reusable control bundle of keyframes from a rendered frame sequence.",
                    "params": {
                        "render_bundle": "Optional render bundle object or JSON string from a render tool",
                        "frame_dir": "Frame directory when render_bundle.frame_dir is not provided",
                        "shot_plan_path": "Path to shot_plan.json",
                        "shot_plan_content": "Optional shot plan JSON content",
                        "output_dir": "Control bundle output directory",
                        "frames_per_shot": "1-3 keyframes per shot",
                        "mode": "start/middle/end when frames_per_shot is 1",
                    },
                },
                "style_keyframes": {
                    "description": "Style keyframes with ComfyUI when configured, otherwise use a deterministic local fallback.",
                    "params": {
                        "input_manifest": "Path to comfy_control_manifest.json",
                        "manifest_content": "Optional manifest JSON content",
                        "provider": "auto/comfyui/local/off",
                        "comfyui_url": "ComfyUI base URL",
                        "workflow_path": "ComfyUI API-format workflow JSON path",
                        "style_prompt": "Positive style prompt",
                        "negative_prompt": "Negative prompt",
                        "seed": "Base seed",
                        "denoise": "Img2img denoise/strength value",
                        "output_dir": "Upgrade output directory",
                    },
                },
                "remote_upgrade_keyframes": {
                    "description": "Run the remote media upgrade channel as one node: extract control keyframes, call ComfyUI, and write QC output.",
                    "params": {
                        "render_bundle": "Render bundle object or JSON string from the Godot/local render node",
                        "shot_plan_path": "Path to shot_plan.json",
                        "shot_plan_content": "Optional shot plan JSON content",
                        "provider": "auto/comfyui/local/off",
                        "comfyui_url": "ComfyUI base URL",
                        "workflow_path": "ComfyUI API-format workflow JSON path",
                        "style_prompt": "Positive style prompt",
                        "negative_prompt": "Negative prompt",
                        "denoise": "Img2img denoise/strength value",
                        "output_dir": "Remote upgrade bundle output directory",
                    },
                },
                "qc_outputs": {
                    "description": "Validate media output manifests and produce a structured QC report.",
                    "params": {
                        "input_manifest": "Path to media upgrade/control manifest",
                        "manifest_content": "Optional manifest JSON content",
                        "output_path": "QC report output path",
                        "min_outputs": "Minimum required output count",
                        "require_images": "Whether image dimensions must be readable",
                        "fallback": "Fallback source label when QC fails",
                    },
                },
                "generate_pixel_shot_plan": {
                    "description": "Generate a deterministic 3-shot pixel 2.5D episode plan and write it to JSON.",
                    "params": {
                        "episode_id": "Episode id, for example ep001",
                        "episode_goal": "One-sentence story goal",
                        "style_notes": "Optional visual notes",
                        "shot_count": "Requested shot count, clamped to 3-6",
                        "output_path": "JSON output path",
                        "world_state_path": "Path to world_state.json",
                        "world_state_content": "Optional world state JSON content",
                        "shot_presets_path": "Path to shot_presets.json",
                        "shot_presets_content": "Optional shot preset library JSON content",
                        "asset_specs": "Optional asset_spec_batch.v1 JSON object/string for plan metadata",
                        "draft_asset_bundle": "Optional asset_forge_batch_result.v1 object/string for plan metadata",
                    },
                },
                "validate_pixel_shot_plan": {
                    "description": "Validate a pixel 2.5D shot plan against the series bible and approved assets.",
                    "params": {
                        "shot_plan_path": "Path to shot_plan.json",
                        "shot_plan_content": "Optional shot plan JSON content",
                        "series_bible_path": "Path to series_bible.json",
                        "asset_manifest_path": "Path to asset_manifest.json",
                        "shot_presets_path": "Path to shot_presets.json",
                        "shot_presets_content": "Optional shot preset library JSON content",
                        "output_path": "Validation report output path",
                    },
                },
                "update_pixel_world_state": {
                    "description": "Update persistent pixel series world_state.json after an episode completes.",
                    "params": {
                        "world_state_path": "Path to world_state.json",
                        "world_state_content": "Optional current world state JSON content",
                        "shot_plan_path": "Path to shot_plan.json",
                        "shot_plan_content": "Optional shot plan JSON content",
                        "episode_id": "Episode id",
                        "episode_goal": "Episode goal summary",
                        "continuity_policy": "read_and_write/read_only/off",
                        "output_path": "World state update report output path",
                    },
                },
                "check_pixel_assets": {
                    "description": "Check that every series bible character/location has an approved asset profile.",
                    "params": {
                        "series_bible_path": "Path to series_bible.json",
                        "series_bible_content": "Optional series bible JSON content",
                        "asset_manifest_path": "Path to asset_manifest.json",
                        "asset_manifest_content": "Optional asset manifest JSON content",
                        "output_path": "Asset check report output path",
                    },
                },
                "comfyui_generate_asset": {
                    "description": "Generate a draft pixel asset candidate with ComfyUI when configured, otherwise a deterministic local PNG.",
                    "params": {
                        "asset_id": "Draft asset id, for example night_market_bg",
                        "asset_kind": "background/prop/character/location",
                        "prompt": "Asset visual prompt",
                        "style_notes": "Optional style notes",
                        "asset_policy": "approved_only skips draft generation; draft_allowed/auto_draft allow draft candidates",
                        "provider": "auto/comfyui/local/off",
                        "comfyui_url": "ComfyUI base URL",
                        "workflow_path": "Optional ComfyUI workflow JSON path",
                        "asset_manifest_path": "Path to asset_manifest.json",
                        "output_dir": "Draft asset output directory",
                        "report_path": "Draft asset report output path",
                    },
                },
                "forge_pixel_asset_batch": {
                    "description": "Consume an asset_spec_batch.v1 object and forge draft pixel assets for review.",
                    "params": {
                        "asset_specs": "asset_spec_batch.v1 JSON object or JSON string",
                        "asset_specs_path": "Optional path to an asset_spec_batch.v1 JSON file",
                        "asset_policy": "approved_only skips forging; draft_allowed writes draft assets",
                        "provider": "Local forge provider label for character/location assets",
                        "image_provider": "auto/comfyui/local/off for background/prop draft images",
                        "output_dir": "Pixel stage asset root",
                        "draft_output_dir": "Draft image asset root, default output_dir/drafts",
                        "asset_manifest_path": "Path to asset_manifest.json",
                        "report_path": "Batch forge report output path",
                    },
                },
                "forge_pixel_character_asset": {
                    "description": "Forge an offline pixel character spritesheet, metadata JSON, profile, preview, and asset manifest entry.",
                    "params": {
                        "character_id": "Character id, for example hero",
                        "display_name": "Display name",
                        "role": "Character role",
                        "actions": "Comma/newline list or JSON array of actions",
                        "palette": "Optional palette JSON object",
                        "frame_size": "Frame size, default 96x128",
                        "frames_per_action": "Frames per action, default 6",
                        "animation_fps": "Animation FPS, default 12",
                        "register_mode": "draft or approved",
                        "output_dir": "Pixel stage asset root",
                        "asset_manifest_path": "Path to asset_manifest.json",
                        "report_path": "Forge report output path",
                    },
                },
                "forge_pixel_location_asset": {
                    "description": "Forge offline parallax location layer PNGs, profile, preview, and asset manifest entry for Godot native rendering.",
                    "params": {
                        "location_id": "Location id, for example night_alley",
                        "display_name": "Display name",
                        "resolution": "Layer resolution, default 1280x720",
                        "layers": "Optional JSON/list layer specs",
                        "register_mode": "draft or approved",
                        "output_dir": "Pixel stage asset root",
                        "asset_manifest_path": "Path to asset_manifest.json",
                        "report_path": "Forge report output path",
                    },
                },
                "godot_render_pixel_episode": {
                    "description": "Render a pixel 2.5D episode plan into a native Godot Movie Maker AVI when available, with optional fallback control.",
                    "params": {
                        "shot_plan_path": "Path to shot_plan.json",
                        "shot_plan_content": "Optional shot plan JSON content",
                        "output_dir": "Output directory",
                        "filename_prefix": "Output filename prefix",
                        "require_godot_native": "Fail instead of using the Python fallback when Godot is unavailable or fails.",
                    },
                },
                "ffmpeg_mux_episode": {
                    "description": "Convert the rendered AVI into MP4 with FFmpeg when available, otherwise keep AVI.",
                    "params": {
                        "video_path": "Rendered AVI/video path",
                        "shot_plan_path": "Path to shot_plan.json",
                        "output_path": "MP4 output path",
                        "preview_path": "HTML preview output path",
                        "compose_provider": "auto/ffmpeg/local/off",
                        "target_product": "mp4/preview/render_bundle",
                    },
                },
                "generate_short_video": {
                    "description": "根据一个想法自动生成短视频标题、分镜、字幕、配音、预览页和视频文件",
                    "params": {
                        "idea": "短视频想法，一句话即可",
                        "title": "可选视频标题，留空自动生成",
                        "topic": "可选补充细节，留空自动扩写",
                        "style": "风格",
                        "audience": "可选目标受众",
                        "duration_seconds": "时长，6-60 秒",
                        "output_dir": "输出目录",
                        "filename_prefix": "输出文件名前缀",
                        "plan": "可选 AI 策划结果",
                        "image_provider": "auto/openai/stability/huggingface/local/off",
                        "voice_provider": "auto/openai/local/off",
                        "compose_provider": "auto/ffmpeg/local/off",
                    },
                },
                "forge_spatial_blockout": {
                    "description": "Generate a deterministic low-poly 3D animation previz as GLB proxy, animation JSON, manifest, and playable preview HTML.",
                    "params": {
                        "scene_spec": "scene_animation.v1 JSON object or JSON string",
                        "title": "Optional scene title",
                        "output_dir": "Output directory for GLB/preview/manifest",
                        "filename_prefix": "Output filename prefix",
                    },
                },
            },
        }
        result = []
        for server, tools in self._registry.items():
            for tool_name in tools:
                meta = descriptions.get(server, {}).get(tool_name, {}) or self._extension_tool_descriptions.get((server, tool_name), {})
                item = {
                    "server": server,
                    "tool": tool_name,
                    "type": "builtin",
                    "description": meta.get("description", ""),
                    "params": meta.get("params", {}),
                }
                if tool_name in self._tool_dlc:
                    item["dlc"] = self._tool_dlc[tool_name]
                result.append(item)
        return result
