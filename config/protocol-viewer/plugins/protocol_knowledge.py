"""Simple tree and reader pages for the protocol knowledge database."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from urllib.parse import quote

from datasette import hookimpl
from datasette.utils.asgi import Response
from datasette_render_markdown import render_markdown


FOUR_MAJOR_LAYERS = (
    {"number": "01", "label": "基础与边界"},
    {"number": "02", "label": "创作与数据"},
    {"number": "03", "label": "发行与信任"},
    {"number": "04", "label": "运行与证明"},
)
SOURCE_LABELS = {"current": "正式线", "temp-runtime": "演进线"}
VERSION_RE = re.compile(r"\d+")
DOCUMENT_PRIORITY = ("readme.md", "overview.md", "specification.md")


async def _rows(database, sql: str, params: dict | None = None) -> list[dict]:
    result = await database.execute(sql, params or {})
    return [dict(zip(result.columns, row)) for row in result.rows]


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(value) for value in VERSION_RE.findall(str(version))) or (0,)


def _contract_url(contract_id: str, version: str | None = None) -> str:
    path = f"/contract/{quote(contract_id, safe='')}"
    return f"{path}?version={quote(version, safe='')}" if version else path


def _protocol_url(
    source_id: str,
    protocol_id: str,
    version: str | None = None,
    artifact_path: str | None = None,
) -> str:
    path = f"/protocol/{quote(source_id, safe='')}/{quote(protocol_id, safe='')}"
    query = []
    if version:
        query.append(f"version={quote(version, safe='')}")
    if artifact_path:
        query.append(f"document={quote(artifact_path, safe='')}")
    return f"{path}?{'&'.join(query)}" if query else path


def _pretty_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except (TypeError, json.JSONDecodeError):
        return text


def _reader_document(artifact: dict) -> dict:
    text = str(artifact.get("text_content") or "")
    is_json = str(artifact.get("media_type") or "").startswith("application/json")
    raw = _pretty_json(text) if is_json else text
    return {
        **artifact,
        "file_name": str(artifact["artifact_path"]).rsplit("/", 1)[-1],
        "is_json": is_json,
        "raw_content": raw,
        "rendered_content": None if is_json else render_markdown(raw, extensions=["tables", "fenced_code"]),
    }


async def _contract_tree(database, active_id: str | None, active_version: str | None) -> list[dict]:
    rows = await _rows(
        database,
        "SELECT family.contract_id, family.display_name, family.layer, family.domain, "
        "family.domain_order, family.sort_order, release.version "
        "FROM data_contract_family AS family "
        "JOIN data_contract_release AS release ON release.contract_id = family.contract_id "
        "ORDER BY family.layer, family.domain_order, family.domain, family.sort_order, "
        "family.contract_id, release.version",
    )
    by_layer: dict[int, dict[str, dict[str, dict]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for row in rows:
        family = by_layer[int(row["layer"])][row["domain"]].setdefault(
            row["contract_id"],
            {
                "contract_id": row["contract_id"],
                "display_name": row["display_name"],
                "sort_order": row["sort_order"],
                "versions": [],
                "active": row["contract_id"] == active_id,
            },
        )
        family["versions"].append(
            {
                "version": row["version"],
                "url": _contract_url(row["contract_id"], row["version"]),
                "active": row["contract_id"] == active_id and row["version"] == active_version,
            }
        )
    layers = []
    for layer_number, layer_meta in enumerate(FOUR_MAJOR_LAYERS, start=1):
        domains = []
        for domain, families in by_layer[layer_number].items():
            family_list = sorted(families.values(), key=lambda item: (item["sort_order"], item["contract_id"]))
            for family in family_list:
                family["versions"].sort(key=lambda item: _version_key(item["version"]), reverse=True)
            domains.append(
                {
                    "name": domain,
                    "families": family_list,
                    "active": any(item["active"] for item in family_list),
                }
            )
        layers.append(
            {
                **layer_meta,
                "domains": domains,
                "active": any(item["active"] for item in domains),
            }
        )
    return layers


async def _protocol_tree(
    database,
    active_source: str | None,
    active_protocol: str | None,
    active_version: str | None,
    active_document: str | None,
) -> list[dict]:
    releases = await _rows(
        database,
        "SELECT source_id, protocol_id, version FROM protocol_release "
        "ORDER BY source_id, protocol_id, version",
    )
    artifacts = await _rows(
        database,
        "SELECT release.source_id, release.protocol_id, release.version, "
        "artifact.artifact_path FROM artifact "
        "JOIN protocol_release AS release ON release.release_key = artifact.release_key "
        "WHERE artifact.text_content IS NOT NULL "
        "ORDER BY release.source_id, release.protocol_id, release.version, artifact.artifact_path",
    )
    documents: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for artifact in artifacts:
        documents[(artifact["source_id"], artifact["protocol_id"], artifact["version"])].append(
            artifact["artifact_path"]
        )
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for release in releases:
        source_id = release["source_id"]
        protocol_id = release["protocol_id"]
        version = release["version"]
        is_active = source_id == active_source and protocol_id == active_protocol and version == active_version
        grouped[source_id][protocol_id].append(
            {
                "version": version,
                "url": _protocol_url(source_id, protocol_id, version),
                "active": is_active,
                "documents": [
                    {
                        "path": path,
                        "name": path.rsplit("/", 1)[-1],
                        "url": _protocol_url(source_id, protocol_id, version, path),
                        "active": is_active and path == active_document,
                    }
                    for path in documents[(source_id, protocol_id, version)]
                ],
            }
        )
    sources = []
    for source_id in ("current", "temp-runtime"):
        protocols = []
        for protocol_id, versions in sorted(grouped[source_id].items()):
            versions.sort(key=lambda item: _version_key(item["version"]), reverse=True)
            protocols.append(
                {
                    "protocol_id": protocol_id,
                    "versions": versions,
                    "active": any(item["active"] for item in versions),
                }
            )
        sources.append(
            {
                "source_id": source_id,
                "label": SOURCE_LABELS[source_id],
                "protocols": protocols,
                "active": source_id == active_source,
            }
        )
    return sources


async def _catalog(
    database,
    *,
    active_contract: str | None = None,
    active_contract_version: str | None = None,
    active_source: str | None = None,
    active_protocol: str | None = None,
    active_protocol_version: str | None = None,
    active_document: str | None = None,
) -> dict:
    return {
        "contract_active": active_contract is not None,
        "protocol_active": active_protocol is not None,
        "contract_layers": await _contract_tree(database, active_contract, active_contract_version),
        "protocol_sources": await _protocol_tree(
            database,
            active_source,
            active_protocol,
            active_protocol_version,
            active_document,
        ),
    }


async def protocol_index(request, datasette):
    database = datasette.get_database("protocol-source")
    row = await _rows(
        database,
        "SELECT release.contract_id, release.version FROM data_contract_release AS release "
        "JOIN data_contract_family AS family ON family.contract_id = release.contract_id "
        "ORDER BY family.layer, family.domain_order, family.sort_order, release.version LIMIT 1",
    )
    if row:
        return Response.redirect(
            _contract_url(row[0]["contract_id"], row[0]["version"]),
            headers={"X-CartridgeFlow-Protocol-Viewer": "1"},
        )
    return Response.text("协议知识库中没有可读数据。", status=404)


async def contract_detail(request, datasette):
    database = datasette.get_database("protocol-source")
    contract_id = request.url_vars["contract_id"]
    releases = await _rows(
        database,
        "SELECT release.*, family.display_name, family.layer, family.domain, family.purpose, "
        "family.owner, family.visibility, owner.protocol_id AS owner_protocol_id, "
        "owner.version AS owner_protocol_version, artifact.artifact_path AS definition_path, "
        "artifact.media_type, artifact.text_content, section.heading AS definition_heading, "
        "section.content AS section_content "
        "FROM data_contract_release AS release "
        "JOIN data_contract_family AS family ON family.contract_id = release.contract_id "
        "JOIN protocol_release AS owner ON owner.release_key = release.owner_protocol_release_key "
        "JOIN artifact ON artifact.artifact_id = release.definition_artifact_id "
        "LEFT JOIN document_section AS section ON section.section_key = release.definition_section_key "
        "WHERE release.contract_id = :contract_id",
        {"contract_id": contract_id},
    )
    if not releases:
        return Response.text("数据合同不存在。", status=404)
    requested_version = request.args.get("version")
    selected = next((item for item in releases if item["version"] == requested_version), None)
    if selected is None:
        selected = max(releases, key=lambda item: _version_key(item["version"]))
        if requested_version:
            return Response.text("数据合同版本不存在。", status=404)
    release_key = selected["contract_release_key"]
    definition_text = str(selected["section_content"] or selected["text_content"] or "")
    is_json = str(selected["media_type"] or "").startswith("application/json") and not selected["section_content"]
    selected["definition_raw"] = _pretty_json(definition_text) if is_json else definition_text
    selected["definition_is_json"] = is_json
    selected["definition_rendered"] = (
        None if is_json else render_markdown(definition_text, extensions=["tables", "fenced_code"])
    )
    rules = await _rows(
        database,
        "SELECT rule_code, severity, rule_kind, description, validator_ref "
        "FROM data_contract_rule WHERE contract_release_key = :key ORDER BY severity, rule_code",
        {"key": release_key},
    )
    usage = await _rows(
        database,
        "SELECT stage, actor, direction, notes FROM data_contract_usage "
        "WHERE contract_release_key = :key ORDER BY direction DESC, actor",
        {"key": release_key},
    )
    bindings = await _rows(
        database,
        "SELECT binding.binding_role, binding.required, binding.notes, protocol.source_id, "
        "protocol.protocol_id, protocol.version FROM data_contract_protocol_binding AS binding "
        "JOIN protocol_release AS protocol ON protocol.release_key = binding.protocol_release_key "
        "WHERE binding.contract_release_key = :key "
        "ORDER BY binding.binding_role, protocol.protocol_id, protocol.version",
        {"key": release_key},
    )
    examples = await _rows(
        database,
        "SELECT example.example_kind, example.description, example.expected_error_code, "
        "artifact.artifact_path, protocol.source_id, protocol.protocol_id, protocol.version "
        "FROM data_contract_example AS example "
        "JOIN artifact ON artifact.artifact_id = example.artifact_id "
        "LEFT JOIN protocol_release AS protocol ON protocol.release_key = artifact.release_key "
        "WHERE example.contract_release_key = :key ORDER BY example.example_kind, artifact.artifact_path",
        {"key": release_key},
    )
    for item in examples:
        item["url"] = _protocol_url(
            item["source_id"], item["protocol_id"], item["version"], item["artifact_path"]
        )
    version_links = [
        {
            "version": item["version"],
            "url": _contract_url(contract_id, item["version"]),
            "active": item["version"] == selected["version"],
        }
        for item in sorted(releases, key=lambda value: _version_key(value["version"]), reverse=True)
    ]
    context = {
        "contract": selected,
        "layer": FOUR_MAJOR_LAYERS[int(selected["layer"]) - 1],
        "rules": rules,
        "usage": usage,
        "bindings": bindings,
        "examples": examples,
        "versions": version_links,
        "catalog": await _catalog(
            database,
            active_contract=contract_id,
            active_contract_version=selected["version"],
        ),
    }
    body = await datasette.render_template(
        "contract_detail.html",
        context,
        request=request,
        view_name="data-contract-detail",
    )
    return Response.html(body, headers={"X-CartridgeFlow-Protocol-Viewer": "1"})


async def protocol_detail(request, datasette):
    database = datasette.get_database("protocol-source")
    source_id = request.url_vars["source_id"]
    protocol_id = request.url_vars["protocol_id"]
    releases = await _rows(
        database,
        "SELECT * FROM protocol_release WHERE source_id = :source_id AND protocol_id = :protocol_id",
        {"source_id": source_id, "protocol_id": protocol_id},
    )
    if not releases:
        return Response.text("协议不存在。", status=404)
    requested_version = request.args.get("version")
    release = next((item for item in releases if item["version"] == requested_version), None)
    if release is None:
        release = max(releases, key=lambda item: _version_key(item["version"]))
        if requested_version:
            return Response.text("协议版本不存在。", status=404)
    artifacts = await _rows(
        database,
        "SELECT artifact_path, artifact_kind, media_type, text_content FROM artifact "
        "WHERE release_key = :release_key AND text_content IS NOT NULL ORDER BY artifact_path",
        {"release_key": release["release_key"]},
    )
    requested_document = request.args.get("document")
    selected = next((item for item in artifacts if item["artifact_path"] == requested_document), None)
    if selected is None and artifacts:
        def priority(item: dict) -> tuple[int, str]:
            name = item["artifact_path"].rsplit("/", 1)[-1].lower()
            return (DOCUMENT_PRIORITY.index(name) if name in DOCUMENT_PRIORITY else len(DOCUMENT_PRIORITY), name)
        selected = min(artifacts, key=priority)
    selected_document = _reader_document(selected) if selected else None
    context = {
        "source_label": SOURCE_LABELS.get(source_id, source_id),
        "source_id": source_id,
        "protocol_id": protocol_id,
        "release": release,
        "selected_document": selected_document,
        "catalog": await _catalog(
            database,
            active_source=source_id,
            active_protocol=protocol_id,
            active_protocol_version=release["version"],
            active_document=selected["artifact_path"] if selected else None,
        ),
    }
    body = await datasette.render_template(
        "protocol_detail.html",
        context,
        request=request,
        view_name="protocol-knowledge-detail",
    )
    return Response.html(body, headers={"X-CartridgeFlow-Protocol-Viewer": "1"})


@hookimpl
def register_routes(datasette):
    return [
        (r"/$", protocol_index),
        (r"/contract/(?P<contract_id>[A-Za-z0-9_.-]+)/?$", contract_detail),
        (r"/protocol/(?P<source_id>[a-z0-9_-]+)/(?P<protocol_id>[A-Za-z0-9_-]+)/?$", protocol_detail),
    ]
