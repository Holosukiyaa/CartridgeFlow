from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


DEPENDENCY_TYPES = {
    "system_package",
    "python_package",
    "node_package",
    "runtime_plugin",
    "browser_extension",
    "model",
    "local_asset",
}


INSTALL_STRATEGIES = {"manual", "assisted", "automatic"}


class DependencyResolver:
    def init_dependency_state(self, manifest: dict) -> dict:
        return {
            "status": "unresolved",
            "items": [],
            "summary": "依赖尚未解析",
            "updated_at": None,
        }

    def resolve(self, manifest: dict, environment: dict | None = None) -> dict:
        items = []
        for dependency in manifest.get("dependencies") or []:
            items.append(self._resolve_item(dependency, environment or {}))
        status = self._resolve_status(items)
        return {
            "status": status,
            "items": items,
            "summary": self._summary(status, len(items)),
            "updated_at": now_iso(),
        }

    def confirm(self, run: dict, dependency_id: str) -> dict:
        item = self._find(run, dependency_id)
        if item.get("status") == "skipped":
            raise ValueError(f"Dependency already skipped: {dependency_id}")
        item["user_choice"] = "confirmed"
        item["confirmed_at"] = now_iso()
        if item.get("strategy") == "automatic":
            item["status"] = "blocked"
            item["message"] = "automatic 安装需要后续受控 installer 支持"
        else:
            item["status"] = "confirmed"
        run["dependencies"] = self._refresh(run.get("dependencies") or {})
        return run

    def skip(self, run: dict, dependency_id: str) -> dict:
        item = self._find(run, dependency_id)
        if item.get("required"):
            raise ValueError(f"Required dependency cannot be skipped: {dependency_id}")
        item["user_choice"] = "skipped"
        item["status"] = "skipped"
        item["skipped_at"] = now_iso()
        run["dependencies"] = self._refresh(run.get("dependencies") or {})
        return run

    def _resolve_item(self, dependency: dict, environment: dict) -> dict:
        strategy = self._strategy(dependency)
        required = bool(dependency.get("required", False))
        env_item = self._match_environment_item(dependency, environment)
        missing = env_item is not None and env_item.get("status") in {"missing", "blocked", "warning"}
        status = self._item_status(strategy, required, missing)
        return {
            "id": dependency.get("id"),
            "type": dependency.get("type"),
            "provider": dependency.get("provider", "unknown"),
            "version": dependency.get("version"),
            "required": required,
            "permission": dependency.get("permission", "install_dependency"),
            "strategy": strategy,
            "status": status,
            "install": dependency.get("install") or {},
            "reason": dependency.get("reason") or dependency.get("message") or "卡带声明的运行依赖",
            "environment_status": env_item.get("status") if env_item else None,
            "user_choice": None,
            "confirmed_at": None,
            "skipped_at": None,
            "message": self._item_message(status, strategy),
        }

    def _match_environment_item(self, dependency: dict, environment: dict) -> dict | None:
        dependency_id = dependency.get("environment_id") or dependency.get("id")
        for item in environment.get("items") or []:
            if item.get("id") == dependency_id:
                return item
        return None

    def _strategy(self, dependency: dict) -> str:
        install = dependency.get("install") or {}
        strategy = install.get("strategy") or dependency.get("strategy") or "manual"
        return strategy if strategy in INSTALL_STRATEGIES else "manual"

    def _item_status(self, strategy: str, required: bool, missing: bool) -> str:
        if not missing:
            return "ok"
        if strategy == "automatic":
            return "blocked"
        if strategy == "assisted":
            return "assisted_available"
        return "manual_required" if required else "manual_optional"

    def _resolve_status(self, items: list[dict]) -> str:
        statuses = {item.get("status") for item in items}
        if not items:
            return "ok"
        if "blocked" in statuses or "manual_required" in statuses:
            return "blocked"
        if "assisted_available" in statuses or "manual_optional" in statuses:
            return "actionable"
        return "ok"

    def _summary(self, status: str, count: int) -> str:
        if count == 0:
            return "没有声明额外依赖"
        labels = {
            "ok": "依赖已满足",
            "actionable": "有可选依赖可处理",
            "blocked": "存在必须处理的依赖",
        }
        return labels.get(status, "依赖状态未知")

    def _item_message(self, status: str, strategy: str) -> str:
        labels = {
            "ok": "依赖已满足",
            "assisted_available": "可以引导用户安装",
            "manual_optional": "可选依赖，可跳过或手动安装",
            "manual_required": "必需依赖，需要手动安装",
            "blocked": "自动安装暂未开放，需要后续受控 installer 支持",
        }
        return labels.get(status, f"安装策略：{strategy}")

    def _find(self, run: dict, dependency_id: str) -> dict:
        dependencies = run.get("dependencies") or {}
        for item in dependencies.get("items") or []:
            if item.get("id") == dependency_id:
                return item
        raise ValueError(f"Unknown dependency: {dependency_id}")

    def _refresh(self, dependencies: dict) -> dict:
        items = dependencies.get("items") or []
        dependencies["status"] = self._resolve_status(items)
        dependencies["summary"] = self._summary(dependencies["status"], len(items))
        dependencies["updated_at"] = now_iso()
        return dependencies
