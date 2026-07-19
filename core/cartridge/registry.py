import json
from pathlib import Path

from .validator import ManifestValidator, ManifestValidationError


class CartridgeRegistry:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.builtin_dir = self.root / "cartridges" / "builtin"
        self.dev_dir = self.root / "cartridges" / "dev"
        self.installed_dir = self.root / ".data" / "installed_cartridges"
        self.validator = ManifestValidator()

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
                except ManifestValidationError:
                    continue
                item = self._public_manifest(manifest)
                item["source"] = source
                item["editable"] = source == "dev"
                items.append(item)
        return items

    def get_cartridge(self, cartridge_id: str) -> dict:
        path = self._find_cartridge_path(cartridge_id)
        manifest = self.validator.validate_package(path, self._read_json(path / "manifest.json"))
        root_flow_path = path / manifest.get("root_flow", {}).get("entry", "root.flow.json")
        try:
            root_flow = self._read_json(root_flow_path) if root_flow_path.exists() else {}
        except json.JSONDecodeError:
            root_flow = {}
        root_flow = root_flow if isinstance(root_flow, dict) else {}
        welcome_content = self._read_welcome(path, manifest)
        welcome_html_content = self._read_ui_html_welcome(path, root_flow) if not welcome_content else ""
        if not welcome_html_content and not welcome_content:
            welcome_html_content = self._read_storage_html_welcome(path, root_flow)
        return {
            **self._public_manifest(manifest),
            "manifest": manifest,
            "root_flow": root_flow,
            "package_path": str(path),
            "source": self._source_for_path(path),
            "editable": self._source_for_path(path) == "dev",
            "welcome_content": welcome_content,
            "welcome_html_content": welcome_html_content,
        }

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
        welcome_path = package_path / entry
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
            "portable_dlc": manifest.get("portable_dlc"),
        }
