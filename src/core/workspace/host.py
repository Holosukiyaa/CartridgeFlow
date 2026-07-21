class WorkspaceHostManager:
    def open(self, run: dict) -> dict:
        workspace = run.get("workspace") or {}
        workspace_type = workspace.get("type", "none")
        return {
            "type": workspace_type,
            "url": None,
            "status": "not_required" if workspace_type == "none" else "declared",
        }
