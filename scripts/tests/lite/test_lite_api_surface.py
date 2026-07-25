import unittest

from backend.lite_main import is_lite_api_allowed


class LiteApiSurfaceTests(unittest.TestCase):
    def test_workbench_routes_are_available(self):
        allowed = [
            "/api/health",
            "/api/lab/flows",
            "/api/lab/flows/dev.example/nodes",
            "/api/lab/flows/dev.example/test-run",
            "/api/llm/providers",
            "/api/studio/resources",
            "/api/studio/environment/credentials/IMAGE_API_KEY",
            "/api/cartridge-runs/run_123/events",
            "/api/cartridges/dev.example/clone-to-dev",
        ]
        for path in allowed:
            with self.subTest(path=path):
                self.assertTrue(is_lite_api_allowed(path))

    def test_global_and_removed_routes_are_blocked(self):
        blocked = [
            "/api/base",
            "/api/studio/conformance",
            "/api/studio/todo",
            "/api/studio/packages",
            "/api/settings",
            "/api/cartridge-runs",
            "/api/lab/flows/dev.example/assistant",
            "/api/lab/flows/dev.example/steward/suggest",
            "/api/lab/flows/dev.example/certification",
        ]
        for path in blocked:
            with self.subTest(path=path):
                self.assertFalse(is_lite_api_allowed(path))


if __name__ == "__main__":
    unittest.main()
