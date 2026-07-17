class CodingRuntimeAdapter:
    runtime_type = "coding"

    def start(self, run: dict) -> dict:
        return {
            "runtime_run_id": f"coding_{run['run_id']}",
            "runtime_type": "coding",
            "status": "ready",
        }
