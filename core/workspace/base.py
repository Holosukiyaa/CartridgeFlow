class WorkspaceHost:
    workspace_type = "none"

    def open(self, run: dict) -> dict:
        return {"type": self.workspace_type, "url": None}
