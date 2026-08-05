"""Fetch and normalize Creator-reviewed RSS or Atom feeds."""

from xml.etree import ElementTree as ET

from cartridgeflow_dlc import McpContext, mcp_operation


MCP_NODE = {
    "schema": "cartridgeflow.mcp_python.v1",
    "node_id": "rss_reader",
    "server": "rss_reader",
    "tool": "fetch",
    "effect": "read_only",
    "inputs": {"urls": {"type": "array"}, "max_items": {"type": "integer"}},
    "outputs": {"items": {"type": "array"}},
    "operations": [
        {"id": "validate_sources", "kind": "transform"},
        {"id": "download_feeds", "kind": "network", "capability": "network.fetch"},
        {"id": "normalize_items", "kind": "transform"},
    ],
    "edges": [
        {"from": "validate_sources", "to": "download_feeds", "kind": "control"},
        {"from": "download_feeds", "to": "normalize_items", "kind": "control"},
    ],
    "fallbacks": [],
}


def _text(element, names):
    for child in element:
        if child.tag.rsplit("}", 1)[-1].lower() in names:
            return " ".join("".join(child.itertext()).split())
    return ""


@mcp_operation("validate_sources")
def op_validate_sources(ctx: McpContext, data: dict) -> dict:
    urls = data.get("urls") or []
    if not isinstance(urls, list) or not 1 <= len(urls) <= 8:
        raise ValueError("urls must contain one to eight reviewed HTTPS feeds")
    normalized = [str(url).strip() for url in urls]
    if any(not url.startswith("https://") for url in normalized):
        raise ValueError("all feed URLs must use HTTPS")
    return {"urls": normalized, "max_items": max(1, min(50, int(data.get("max_items") or 20)))}


@mcp_operation("download_feeds")
def op_download_feeds(ctx: McpContext, data: dict) -> dict:
    return {**data, "responses": ctx.network.fetch_many(data["urls"])}


@mcp_operation("normalize_items")
def op_normalize_items(ctx: McpContext, data: dict) -> dict:
    items = []
    for index, response in enumerate(data.get("responses") or []):
        if isinstance(response, dict):
            document = str(response.get("content") or response.get("body") or response.get("text") or "")
        else:
            document = str(response)
        if len(document.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("feed document exceeds the 2 MiB parsing limit")
        if "<!DOCTYPE" in document.upper() or "<!ENTITY" in document.upper():
            raise ValueError("entity declarations are not allowed")
        root = ET.fromstring(document)
        for entry in root.iter():
            if entry.tag.rsplit("}", 1)[-1].lower() not in {"item", "entry"}:
                continue
            title = _text(entry, {"title"})
            link = _text(entry, {"link"})
            if not link:
                link_node = next((child for child in entry if child.tag.rsplit("}", 1)[-1].lower() == "link"), None)
                link = str((link_node.attrib if link_node is not None else {}).get("href") or "")
            if title and link:
                items.append({
                    "source_url": data["urls"][index],
                    "title": title[:300],
                    "url": link,
                    "published_at": _text(entry, {"pubdate", "published", "updated"})[:160],
                    "summary": _text(entry, {"description", "summary", "content"})[:2000],
                })
            if len(items) >= data["max_items"]:
                return {"items": items}
    return {"items": items}


OPERATIONS = {
    "validate_sources": op_validate_sources,
    "download_feeds": op_download_feeds,
    "normalize_items": op_normalize_items,
}


def run(ctx: McpContext, inputs: dict) -> dict:
    return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)
