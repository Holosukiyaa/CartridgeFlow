import platform
import re
import subprocess


OS_NAMES = {
    "windows": "windows",
    "darwin": "macos",
    "linux": "linux",
}


class EnvironmentChecker:
    def current_os(self) -> str:
        return OS_NAMES.get(platform.system().lower(), platform.system().lower())

    def init_environment_state(self, manifest: dict) -> dict:
        return {
            "status": "unchecked",
            "os": self.current_os(),
            "items": [],
            "summary": "环境尚未检查",
        }

    def check(self, manifest: dict) -> dict:
        environment = manifest.get("environment") or {}
        items = []
        os_item = self._check_os(environment.get("os") or [])
        if os_item:
            items.append(os_item)
        for requirement in environment.get("requires") or []:
            item = self._check_requirement(requirement)
            if item:
                items.append(item)
        status = self._resolve_status(items)
        return {
            "status": status,
            "os": self.current_os(),
            "items": items,
            "summary": self._summary(status),
        }

    def _check_os(self, allowed: list) -> dict | None:
        if not allowed:
            return None
        current = self.current_os()
        if current in allowed:
            status = "ok"
        else:
            status = "blocked"
        return {
            "id": "os",
            "type": "os",
            "status": status,
            "detected": current,
            "required": allowed,
            "required_level": "required",
            "fixable": False,
            "message": "当前操作系统可运行" if status == "ok" else "当前操作系统不在支持范围内",
        }

    def _check_requirement(self, requirement: dict) -> dict | None:
        req_type = requirement.get("type")
        if req_type == "command":
            return self._check_command(requirement)
        if req_type == "app_config":
            return self._check_app_config(requirement)
        return {
            "id": requirement.get("id", "unknown"),
            "type": req_type or "unknown",
            "status": "warning",
            "required_level": self._required_level(requirement),
            "fixable": False,
            "message": requirement.get("message") or "暂不支持该环境检查类型",
        }

    def _check_command(self, requirement: dict) -> dict:
        command = requirement.get("command") or requirement.get("id")
        required_level = self._required_level(requirement)
        try:
            result = subprocess.run(command.split(), capture_output=True, text=True, timeout=5)
            output = (result.stdout or result.stderr or "").strip()
            detected = self._extract_version(output) or output
            if result.returncode != 0:
                return self._missing_item(requirement, required_level, detected or None)
            status = self._check_version(detected, requirement.get("version"))
            return {
                "id": requirement.get("id"),
                "type": "command",
                "status": status,
                "detected": detected,
                "required": requirement.get("version"),
                "required_level": required_level,
                "fixable": False,
                "action": requirement.get("action"),
                "message": requirement.get("message") or self._item_message(status),
            }
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return self._missing_item(requirement, required_level, None)

    def _check_app_config(self, requirement: dict) -> dict:
        required_level = self._required_level(requirement)
        return {
            "id": requirement.get("id"),
            "type": "app_config",
            "status": "blocked" if required_level == "required" else "warning",
            "required": requirement.get("key"),
            "required_level": required_level,
            "fixable": False,
            "action": requirement.get("action"),
            "message": requirement.get("message") or "需要完成应用配置",
        }

    def _missing_item(self, requirement: dict, required_level: str, detected: str | None) -> dict:
        return {
            "id": requirement.get("id"),
            "type": requirement.get("type"),
            "status": "blocked" if required_level == "required" else "missing",
            "detected": detected,
            "required": requirement.get("version"),
            "required_level": required_level,
            "fixable": bool(requirement.get("action")),
            "action": requirement.get("action"),
            "message": requirement.get("message") or "缺少运行所需组件",
        }

    def _required_level(self, requirement: dict) -> str:
        return "required" if requirement.get("required", False) else "optional"

    def _extract_version(self, value: str) -> str:
        match = re.search(r"\d+(?:\.\d+)+", value or "")
        return match.group(0) if match else value

    def _check_version(self, detected: str, required: str | None) -> str:
        if not required:
            return "ok"
        if required.startswith(">="):
            return "ok" if self._version_tuple(detected) >= self._version_tuple(required[2:]) else "warning"
        return "ok"

    def _version_tuple(self, value: str) -> tuple:
        return tuple(int(part) for part in re.findall(r"\d+", value or "0"))

    def _resolve_status(self, items: list[dict]) -> str:
        statuses = {item.get("status") for item in items}
        if "blocked" in statuses:
            return "blocked"
        if "missing" in statuses or "warning" in statuses:
            return "warning"
        return "ok"

    def _summary(self, status: str) -> str:
        labels = {
            "ok": "环境已准备好",
            "warning": "可以运行，但建议完善环境",
            "blocked": "需要处理环境问题后才能继续",
        }
        return labels.get(status, "环境状态未知")

    def _item_message(self, status: str) -> str:
        labels = {
            "ok": "已准备好",
            "warning": "可以运行，但建议升级",
            "missing": "缺少组件，可安装",
            "blocked": "需要处理后才能继续",
        }
        return labels.get(status, "环境状态未知")
