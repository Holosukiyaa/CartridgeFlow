import json
from pathlib import Path

from core.data_paths import DEV_CARTRIDGES_DIR, INSTALLED_CARTRIDGES_DIR
from core.protocol.tuning import materialize_tuning
from core.studio.tuning_repository import TuningRepositoryStore

from .validator import ManifestValidator, ManifestValidationError, resolve_package_entry


class CartridgeRegistry:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.builtin_dir = self.root / "cartridges" / "builtin"
        self.dev_dir = self.root / DEV_CARTRIDGES_DIR
        self.installed_dir = self.root / INSTALLED_CARTRIDGES_DIR
        self.validator = ManifestValidator()
        self.tuning = TuningRepositoryStore(self.root)

    def list_cartridges(self) -> list[dict]:
        items = []
        for source, directory in (("dev", self.dev_dir), ("installed", self.installed_dir), ("builtin", self.builtin_dir)):
            if not directory.exists():
                continue
            for path in sorted(directory.iterdir()):
                if not path.is_dir():
                    continue
                manifest_path = path / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = self.validator.validate_package(path, self._read_json(manifest_path))
                    if source != "dev" and self._uses_recipe_release(manifest):
                        self._materialize_published_tuning(path, manifest)
                except (ManifestValidationError, OSError, ValueError, json.JSONDecodeError):
                    continue
                item = self._public_manifest(manifest)
                item["source"] = source
                item["editable"] = source == "dev"
                items.append(item)
        return items

    def get_cartridge(self, cartridge_id: str, *, tuning_mode: str = "draft") -> dict:
        if tuning_mode not in {"draft", "runtime"}:
            raise ValueError(f"Unknown tuning materialization mode: {tuning_mode}")
        path = self._find_cartridge_path(cartridge_id)
        manifest = self.validator.validate_package(path, self._read_json(path / "manifest.json"))
        root_flow_path = resolve_package_entry(
            path,
            manifest.get("root_flow", {}).get("entry", "root.flow.json"),
            "manifest.root_flow.entry",
        )
        try:
            root_flow = self._read_json(root_flow_path) if root_flow_path.exists() else {}
        except json.JSONDecodeError:
            root_flow = {}
        root_flow = root_flow if isinstance(root_flow, dict) else {}
        source = self._source_for_path(path)
        tuning_context = None
        tuning_contract = manifest.get("tuning_contract") if isinstance(manifest.get("tuning_contract"), dict) else None
        if tuning_contract and self._uses_recipe_release(manifest):
            if source == "dev":
                repository = self.tuning.load(cartridge_id, root_flow)
                root_flow, tuning_context = materialize_tuning(
                    root_flow,
                    repository,
                    draft=tuning_mode == "draft",
                )
            else:
                root_flow, tuning_context = self._materialize_published_tuning(path, manifest, root_flow)
        welcome_content = self._read_welcome(path, manifest)
        welcome_html_content = self._read_ui_html_welcome(path, root_flow) if not welcome_content else ""
        if not welcome_html_content and not welcome_content:
            welcome_html_content = self._read_storage_html_welcome(path, root_flow)
        return {
            **self._public_manifest(manifest),
            "manifest": manifest,
            "root_flow": root_flow,
            "package_path": str(path),
            "source": source,
            "editable": source == "dev",
            "tuning_context": tuning_context,
            "welcome_content": welcome_content,
            "welcome_html_content": welcome_html_content,
        }

    def get_runtime_cartridge(self, cartridge_id: str) -> dict:
        return self.get_cartridge(cartridge_id, tuning_mode="runtime")

    def get_packaging_cartridge(self, cartridge_id: str) -> dict:
        cartridge = self.get_runtime_cartridge(cartridge_id)
        tuning_contract = cartridge.get("tuning_contract") if isinstance(cartridge.get("tuning_contract"), dict) else None
        if not tuning_contract or not self._uses_recipe_release(cartridge.get("manifest") or {}) or cartridge.get("source") != "dev":
            return cartridge
        package_path = Path(cartridge["package_path"])
        packaged_flow, packaged_context = self._materialize_published_tuning(
            package_path,
            cartridge["manifest"],
        )
        active_context = cartridge.get("tuning_context") or {}
        if (
            packaged_context.get("release_id") != active_context.get("release_id")
            or packaged_context.get("release_digest") != active_context.get("release_digest")
        ):
            raise ValueError("Published recipe snapshot does not match the active recipe release")
        return {**cartridge, "root_flow": packaged_flow, "tuning_context": packaged_context}

    def _materialize_published_tuning(
        self,
        path: Path,
        manifest: dict,
        root_flow: dict | None = None,
    ) -> tuple[dict, dict]:
        tuning_contract = manifest.get("tuning_contract") if isinstance(manifest.get("tuning_contract"), dict) else {}
        release_path = resolve_package_entry(
            path,
            str(tuning_contract.get("release_entry") or "tuning/release.json"),
            "manifest.tuning_contract.release_entry",
        )
        if not release_path.is_file():
            raise ValueError(f"Published recipe release is missing: {release_path.relative_to(path).as_posix()}")
        if root_flow is None:
            root_flow_path = resolve_package_entry(
                path,
                manifest.get("root_flow", {}).get("entry", "root.flow.json"),
                "manifest.root_flow.entry",
            )
            root_flow = self._read_json(root_flow_path)
        release = self._read_json(release_path)
        if not isinstance(root_flow, dict) or not isinstance(release, dict):
            raise ValueError("Published recipe root flow and release must be objects")
        if release.get("flow_id") != manifest.get("id"):
            raise ValueError("Published recipe release flow identity does not match manifest")
        return materialize_tuning(root_flow, release, draft=False)

    @staticmethod
    def _uses_recipe_release(manifest: dict) -> bool:
        contract = manifest.get("tuning_contract") if isinstance(manifest.get("tuning_contract"), dict) else {}
        return bool(str(contract.get("release_entry") or "").strip())

    def _find_cartridge_path(self, cartridge_id: str) -> Path:
        for directory in (self.dev_dir, self.installed_dir, self.builtin_dir):
            path = directory / cartridge_id
            if path.exists() and path.is_dir():
                return path
        raise FileNotFoundError(f"Cartridge not found: {cartridge_id}")

    def _source_for_path(self, path: Path) -> str:
        try:
            resolved = path.resolve()
            if self.dev_dir.resolve() in resolved.parents:
                return "dev"
            if self.installed_dir.resolve() in resolved.parents:
                return "installed"
        except OSError:
            pass
        return "builtin"

    def _read_json(self, path: Path) -> dict:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _read_welcome(self, package_path: Path, manifest: dict) -> str:
        welcome = manifest.get("welcome") or {}
        if welcome.get("type") != "markdown":
            return ""
        entry = welcome.get("entry")
        if not entry:
            return ""
        try:
            welcome_path = resolve_package_entry(package_path, entry, "manifest.welcome.entry")
        except ValueError:
            return ""
        if not welcome_path.exists():
            return ""
        return welcome_path.read_text(encoding="utf-8")

    def _read_storage_html_welcome(self, package_path: Path, root_flow: dict) -> str:
        """Fallback welcome: if first runnable node is a store node pointing at HTML, show it on shelf."""
        states = root_flow.get("states") or {}
        start_id = root_flow.get("start")
        first_id = (states.get(start_id) or {}).get("next") if start_id in states else start_id
        first_state = states.get(first_id) or {}
        params = first_state.get("params") or {}
        preset_config = params.get("preset_config") or {}
        category = params.get("node_category") or preset_config.get("node_category")
        is_store = category == "store" or first_state.get("action") in {"save_context", "store_html", "show_html"}
        if not is_store:
            return ""
        inline_html = params.get("html") or preset_config.get("html")
        if isinstance(inline_html, str) and inline_html.strip():
            return inline_html
        candidate = (
            params.get("path")
            or params.get("save_to")
            or params.get("output")
            or preset_config.get("path")
            or preset_config.get("file")
            or preset_config.get("html_path")
        )
        if not isinstance(candidate, str) or not candidate.lower().endswith((".html", ".htm")):
            return ""
        target = (package_path / candidate).resolve()
        try:
            if package_path.resolve() not in target.parents and target != package_path.resolve():
                return ""
        except OSError:
            return ""
        if not target.is_file():
            return ""
        return target.read_text(encoding="utf-8", errors="replace")

    def _read_ui_html_welcome(self, package_path: Path, root_flow: dict) -> str:
        """Preferred welcome: if first runnable node is a UI node pointing at HTML, show it on shelf."""
        states = root_flow.get("states") or {}
        start_id = root_flow.get("start")
        first_id = (states.get(start_id) or {}).get("next") if start_id in states else start_id
        first_state = states.get(first_id) or {}
        params = first_state.get("params") or {}
        preset_config = params.get("preset_config") or {}
        category = params.get("node_category") or preset_config.get("node_category")
        is_ui = category == "ui" or first_state.get("type") == "ui" or first_state.get("action") in {"show_welcome", "show_ui", "render_ui", "show_result"}
        if not is_ui:
            return ""
        inline_html = params.get("html") or preset_config.get("html")
        if isinstance(inline_html, str) and inline_html.strip():
            return inline_html
        candidate = (
            params.get("path")
            or preset_config.get("path")
            or preset_config.get("html_path")
            or preset_config.get("file")
        )
        if not isinstance(candidate, str) or not candidate.lower().endswith((".html", ".htm")):
            return ""
        target = (package_path / candidate).resolve()
        try:
            if package_path.resolve() not in target.parents and target != package_path.resolve():
                return ""
        except OSError:
            return ""
        if not target.is_file():
            return ""
        return target.read_text(encoding="utf-8", errors="replace")

    def _public_manifest(self, manifest: dict) -> dict:
        return {
            "id": manifest.get("id"),
            "name": manifest.get("name"),
            "version": manifest.get("version"),
            "kind": manifest.get("kind"),
            "category": manifest.get("category"),
            "description": manifest.get("description"),
            "publisher": manifest.get("publisher", {}),
            "branding": manifest.get("branding", {}),
            "runtime": manifest.get("runtime", {}),
            "base_contract": manifest.get("base_contract", {}),
            "runtime_contract": manifest.get("runtime_contract", {}),
            "delivery_readiness": manifest.get("delivery_readiness", {}),
            "protocol_certification": manifest.get("protocol_certification", {}),
            "workspace": manifest.get("workspace", {}),
            "inputs": manifest.get("inputs", []),
            "outputs": manifest.get("outputs", []),
            "mcp_tools": manifest.get("mcp_tools", []),
            "resource_requirements": manifest.get("resource_requirements", []),
            "llm_recipe": manifest.get("llm_recipe"),
            "portable_dlc": manifest.get("portable_dlc"),
            "tuning_contract": manifest.get("tuning_contract"),
        }
