class RuntimeAdapter:
    runtime_type = "none"

    def start(self, run: dict) -> dict:
        return {"status": "ready"}
