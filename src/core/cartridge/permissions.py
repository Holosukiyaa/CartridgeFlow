from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


PERMISSION_LEVELS = ("safe", "sensitive", "dangerous")

AUTH_MODES = ("always_allow", "ask_once", "ask_each_time", "deny", "limited")

BUILTIN_PERMISSIONS = {
    "create_artifact": {
        "id": "create_artifact",
        "label": "生成产物",
        "level": "safe",
        "description": "允许卡带在运行目录中创建产物文件（HTML、Markdown 等）",
    },
    "read_workspace": {
        "id": "read_workspace",
        "label": "读取项目文件",
        "level": "sensitive",
        "description": "用于理解项目代码结构",
    },
    "write_workspace": {
        "id": "write_workspace",
        "label": "修改项目文件",
        "level": "dangerous",
        "description": "用于实现你的开发任务",
    },
    "run_command": {
        "id": "run_command",
        "label": "运行终端命令",
        "level": "dangerous",
        "description": "用于安装依赖、运行测试或构建",
    },
    "access_network": {
        "id": "access_network",
        "label": "访问网络",
        "level": "sensitive",
        "description": "用于下载依赖或查询公开文档",
    },
    "install_dependency": {
        "id": "install_dependency",
        "label": "安装依赖",
        "level": "dangerous",
        "description": "用于安装项目所需的第三方依赖包",
    },
    "use_browser": {
        "id": "use_browser",
        "label": "使用浏览器",
        "level": "sensitive",
        "description": "用于访问网页、抓取信息或自动化测试",
    },
}


class PermissionManager:
    def __init__(self):
        self._catalog = dict(BUILTIN_PERMISSIONS)

    def resolve_permissions(self, manifest: dict) -> list[dict]:
        items = manifest.get("permissions") or []
        resolved = []
        for item in items:
            perm_id = item.get("id") if isinstance(item, dict) else str(item)
            definition = self._catalog.get(perm_id, {"id": perm_id, "label": perm_id, "level": "sensitive", "description": ""})
            resolved.append({
                "id": perm_id,
                "label": item.get("label", definition.get("label", perm_id)) if isinstance(item, dict) else definition.get("label", perm_id),
                "level": item.get("level", definition.get("level", "sensitive")) if isinstance(item, dict) else definition.get("level", "sensitive"),
                "description": item.get("description", definition.get("description", "")) if isinstance(item, dict) else definition.get("description", ""),
                "auth_mode": item.get("auth_mode", "ask_once") if isinstance(item, dict) else "ask_once",
            })
        return resolved

    def init_permission_state(self, manifest: dict) -> dict:
        resolved = self.resolve_permissions(manifest)
        state = {}
        for perm in resolved:
            state[perm["id"]] = {
                "id": perm["id"],
                "label": perm["label"],
                "level": perm["level"],
                "description": perm["description"],
                "auth_mode": perm["auth_mode"],
                "status": "pending",
                "granted_at": None,
            }
        return state

    def get_risk_summary(self, permissions_state: dict) -> dict:
        safe_count = 0
        sensitive_count = 0
        dangerous_count = 0
        for perm in permissions_state.values():
            level = perm.get("level", "sensitive")
            if level == "safe":
                safe_count += 1
            elif level == "dangerous":
                dangerous_count += 1
            else:
                sensitive_count += 1
        if dangerous_count > 0:
            overall = "high"
        elif sensitive_count > 0:
            overall = "medium"
        else:
            overall = "low"
        labels = {
            "low": "低风险：只读、只生成文本",
            "medium": "中风险：访问项目文件、访问网络",
            "high": "高风险：修改文件、运行命令、安装依赖",
        }
        return {
            "overall": overall,
            "label": labels.get(overall, ""),
            "counts": {"safe": safe_count, "sensitive": sensitive_count, "dangerous": dangerous_count},
            "total": len(permissions_state),
        }

    def grant(self, run: dict, permission_id: str, auth_mode: str | None = None) -> dict:
        permissions = run.get("permissions", {})
        if permission_id not in permissions:
            raise ValueError(f"Unknown permission: {permission_id}")
        if auth_mode and auth_mode not in AUTH_MODES:
            raise ValueError(f"Invalid auth_mode: {auth_mode}")
        permissions[permission_id]["status"] = "granted"
        permissions[permission_id]["granted_at"] = now_iso()
        if auth_mode:
            permissions[permission_id]["auth_mode"] = auth_mode
        run["permissions"] = permissions
        return run

    def deny(self, run: dict, permission_id: str) -> dict:
        permissions = run.get("permissions", {})
        if permission_id not in permissions:
            raise ValueError(f"Unknown permission: {permission_id}")
        permissions[permission_id]["status"] = "denied"
        permissions[permission_id]["granted_at"] = now_iso()
        run["permissions"] = permissions
        return run

    def is_granted(self, run: dict, permission_id: str) -> bool:
        permissions = run.get("permissions", {})
        perm = permissions.get(permission_id)
        return perm is not None and perm.get("status") == "granted"
