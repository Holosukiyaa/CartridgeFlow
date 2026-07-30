import json
import os
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from core.studio.resource_catalog import (
    ResourceCatalogError,
    build_flow_resource_catalog,
    check_flow_resource_connectivity,
    get_flow_resource_detail,
)


ROOT = Path(__file__).resolve().parents[3]


class _HealthyConnectorHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, _format, *_args):
        return


@contextmanager
def _healthy_connector():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthyConnectorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/connector"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _manifest(tool_id="external_news", tool_type="remote"):
    return {
        "id": "dev.eng021-resource-contract",
        "mcp_tools": [{
            "id": tool_id,
            "name": "External news",
            "type": tool_type,
            "server": "news-service",
            "tool": "fetch_news",
            "required": True,
            "contract": {
                "input_schema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                },
                "output_schema": {"type": "object", "properties": {"items": {"type": "array"}}},
                "permissions": ["network:read"],
                "side_effect": "read_only",
                "timeout_ms": 4_000,
                "retry": {"max_retries": 2, "backoff": "exponential"},
                "idempotent": True,
            },
        }],
    }


def _flow(tool_id="external_news"):
    return {
        "states": {
            "fetch": {"kind": "mcp_read", "executor": "mcp", "allowed_tools": [tool_id]},
        },
    }


def _resources(endpoint, *, bound, resource_id="external-news"):
    return {
        "version": 1,
        "tools": [{
            "id": resource_id,
            "name": "External news connector",
            "description": "Bearer description-token secret=description-secret",
            "kind": "remote_api",
            "server": "news-service",
            "tool": "fetch_news",
            "endpoint": endpoint,
            "auth_env": "ENG021_NEWS_TOKEN",
            "auth_header": "Authorization",
            "auth_scheme": "Bearer",
            "enabled": True,
            "params_schema": {
                "type": "object",
                "properties": {"api_key": {"default": "schema-secret", "description": "token=annotation-secret"}},
                "headers": {"Authorization": "header-secret"},
            },
        }],
        "bindings": {"roles": {}, "tools": {"dev.eng021-resource-contract": [resource_id] if bound else []}},
    }


class ResourceCatalogEng021Tests(unittest.TestCase):
    def test_external_connector_projection_redacts_private_values_and_unbound_check_fails(self):
        endpoint = "https://private-user:private-password@news.example.test/v1/fetch?token=private-token"
        report = build_flow_resource_catalog(ROOT, _manifest(), _flow(), resources=_resources(endpoint, bound=False))
        item = next(candidate for candidate in report["tools"] if candidate["resource_id"] == "external-news")

        self.assertEqual("external_connector", item["presentation_mode"])
        self.assertEqual("not_bound", item["flow_binding"]["status"])
        self.assertEqual("local-resource:external-news", item["connector"]["identity"])
        self.assertEqual("local-resource:external-news#endpoint", item["connector"]["endpoint"]["reference"])
        self.assertEqual("missing", item["connector"]["authentication"]["status"])
        self.assertEqual("news-service", item["contract"]["server"])
        self.assertEqual("fetch_news", item["contract"]["tool"])
        self.assertEqual(4_000, item["contract"]["timeout_ms"])
        self.assertEqual(2, item["contract"]["retry"]["max_retries"])
        self.assertEqual("idempotent", item["contract"]["idempotency"]["status"])
        self.assertEqual("not_checked", item["health"]["connection"]["status"])
        self.assertEqual("not_observed", item["health"]["run"]["status"])

        serialized = json.dumps(report, ensure_ascii=False)
        for private_value in (
            endpoint,
            "private-password",
            "private-token",
            "description-token",
            "description-secret",
            "schema-secret",
            "annotation-secret",
            "header-secret",
            "Authorization",
        ):
            self.assertNotIn(private_value, serialized)

        with self.assertRaises(ResourceCatalogError) as raised:
            check_flow_resource_connectivity(ROOT, _manifest(), _flow(), "external-news", resources=_resources(endpoint, bound=False))
        self.assertEqual("EXTERNAL_CONNECTOR_UNBOUND", raised.exception.code)
        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual("failed", raised.exception.health["status"])

    def test_local_parsable_and_unauditable_modes_are_distinct(self):
        portable_manifest = {
            "id": "dev.eng021-local",
            "portable_dlc": {"descriptor": "dlc/descriptor.json"},
            "mcp_tools": [{"id": "local_tool", "server": "local", "tool": "parse", "contract": {"side_effect": "read_only"}}],
        }
        descriptor = {
            "id": "local.descriptor",
            "tools": [{
                "server": "local",
                "tool": "parse",
                "implementation": {"entry": "dlc/local.py"},
                "_source_model": {"ok": True, "operations": [{"id": "parse"}], "capabilities": ["read"]},
            }],
        }
        with patch("core.studio.resource_catalog.load_portable_dlc_descriptor", return_value=descriptor):
            local_report = build_flow_resource_catalog(ROOT, portable_manifest, {"states": {}}, package_path=ROOT, resources={"tools": [], "bindings": {"roles": {}, "tools": {}}})
        local_item = next(candidate for candidate in local_report["tools"] if candidate["id"] == "local_tool")
        self.assertEqual("local_parsable", local_item["presentation_mode"])
        self.assertEqual("readable", local_item["readability"]["state"])
        self.assertEqual("parsed", local_item["parse_status"])

        opaque_manifest = _manifest()
        opaque_manifest["mcp_tools"][0]["contract"] = {}
        opaque_report = build_flow_resource_catalog(
            ROOT,
            opaque_manifest,
            _flow(),
            resources=_resources("https://opaque.example.test/connector", bound=True),
        )
        opaque_item = next(candidate for candidate in opaque_report["tools"] if candidate["resource_id"] == "external-news")
        self.assertEqual("unauditable", opaque_item["presentation_mode"])
        self.assertIn("verifiable call contract", opaque_item["readability"]["reason"])

    def test_bound_http_connector_performs_real_probe_and_persists_health_summary(self):
        with patch.dict(os.environ, {"ENG021_NEWS_TOKEN": "real-local-test-token"}):
            with _healthy_connector() as endpoint:
                resources = _resources(endpoint, bound=True, resource_id="healthy-news")
                result = check_flow_resource_connectivity(ROOT, _manifest(), _flow(), "healthy-news", resources=resources)
                detail = get_flow_resource_detail(ROOT, _manifest(), _flow(), "healthy-news", resources=resources)

        self.assertTrue(result["ok"])
        self.assertEqual("remote_http", result["connection_health"]["adapter"])
        self.assertEqual("healthy", detail["resource"]["health"]["connection"]["status"])
        self.assertEqual("CONNECTIVITY_OK", detail["resource"]["health"]["connection"]["code"])


if __name__ == "__main__":
    unittest.main()
