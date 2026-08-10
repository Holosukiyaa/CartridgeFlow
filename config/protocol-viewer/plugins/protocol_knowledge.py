"""Progressive protocol catalog and detail pages for the local viewer."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from urllib.parse import quote

from datasette import hookimpl
from datasette.utils.asgi import Response
from datasette_render_markdown import render_markdown


CATEGORY_LAYERS = {
    "base": {
        "key": "foundation",
        "label": "基础合同",
        "description": "跨卡带的宿主安全、执行服务、存储边界与兼容性底线。",
        "order": 0,
    },
    "flow-authoring": {
        "key": "flow",
        "label": "Flow 与数据合同",
        "description": "Flow 的结构、节点、端口、输入输出、Store、工具与运行时执行契约。",
        "order": 1,
    },
    "tuning": {
        "key": "tuning",
        "label": "受信语义配方",
        "description": "由 Flow 层承载的语义配方、能力匹配、调优版本与作者侧物化输入。",
        "order": 2,
    },
    "release-envelope": {
        "key": "release",
        "label": "发行封装",
        "description": "发行布局、哈希、签名、安装、激活与运行时交接。",
        "order": 3,
    },
    "runtime-profiles": {
        "key": "runtime",
        "label": "运行时画像",
        "description": "宿主能力声明、目标协商与 fail-closed 支持检查。",
        "order": 4,
    },
}
FOUR_MAJOR_LAYERS = (
    {
        "key": "foundation",
        "number": "01",
        "label": "基础与边界",
        "description": "定义所有卡带共同遵守的宿主底线。",
        "categories": ("base",),
    },
    {
        "key": "authoring",
        "number": "02",
        "label": "创作与数据",
        "description": "定义 Flow、数据合同与受信语义配方。",
        "categories": ("flow-authoring", "tuning"),
    },
    {
        "key": "release",
        "number": "03",
        "label": "发行与信任",
        "description": "定义协议如何封装、验证、安装和激活。",
        "categories": ("release-envelope",),
    },
    {
        "key": "runtime",
        "number": "04",
        "label": "运行时适配",
        "description": "定义宿主能力画像与运行前支持检查。",
        "categories": ("runtime-profiles",),
    },
)
DEFAULT_LAYER = {
    "key": "other",
    "label": "待归类材料",
    "description": "暂未归入标准协议层的治理材料。",
    "order": 99,
}
VERSION_RE = re.compile(r"\d+")
CONTRACT_TOKENS = (
    "schema",
    "contract",
    "data",
    "port",
    "input",
    "output",
    "binding",
    "store",
    "edge",
    "resource",
    "合同",
    "数据",
    "端口",
    "输入",
    "输出",
    "绑定",
)
DOCUMENT_PRIORITY = ("readme.md", "overview.md", "specification.md")


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(value) for value in VERSION_RE.findall(str(version))) or (0,)


async def _rows(database, sql: str, params: dict | None = None) -> list[dict]:
    result = await database.execute(sql, params or {})
    return [dict(zip(result.columns, row)) for row in result.rows]


def _layer(category: str | None) -> dict:
    return CATEGORY_LAYERS.get(category or "", DEFAULT_LAYER)


def _major_layer(category: str | None) -> dict:
    for major in FOUR_MAJOR_LAYERS:
        if category in major["categories"]:
            return major
    return FOUR_MAJOR_LAYERS[0]


def _detail_url(source_id: str, protocol_id: str, version: str | None = None) -> str:
    path = f"/protocol/{quote(source_id, safe='')}/{quote(protocol_id, safe='')}"
    return f"{path}?version={quote(version, safe='')}" if version else path


def _document_url(
    source_id: str,
    protocol_id: str,
    version: str,
    artifact_path: str,
    *,
    kind: str | None = None,
    section_key: str | None = None,
) -> str:
    url = (
        f"{_detail_url(source_id, protocol_id, version)}"
        f"&document={quote(artifact_path, safe='')}"
    )
    if kind:
        url += f"&kind={quote(kind, safe='')}"
    if section_key:
        url += f"&section={quote(section_key, safe='')}"
    return url


def _is_contract_artifact(artifact: dict) -> bool:
    path = str(artifact.get("artifact_path") or "").lower()
    if artifact.get("artifact_kind") == "schema":
        return True
    return any(token in path for token in CONTRACT_TOKENS)


def _is_contract_section(section: dict) -> bool:
    heading = str(section.get("heading") or "").lower()
    return any(token in heading for token in CONTRACT_TOKENS)


def _pretty_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except (TypeError, json.JSONDecodeError):
        return text


def _document_context(artifact: dict, selected: bool = False) -> dict:
    text = artifact.get("text_content") or ""
    is_json = str(artifact.get("media_type") or "").startswith("application/json")
    raw = _pretty_json(text) if is_json else text
    return {
        **artifact,
        "file_name": str(artifact.get("artifact_path") or "").rsplit("/", 1)[-1],
        "selected": selected,
        "is_json": is_json,
        "raw_content": raw,
        "rendered_content": (
            None
            if is_json
            else render_markdown(raw, extensions=["tables", "fenced_code"])
        ),
    }


async def _release_cards(database, source_id: str) -> list[dict]:
    families = await _rows(
        database,
        "SELECT source_id, protocol_id, name, owner, responsibility_boundary, exclusions_json "
        "FROM protocol_family WHERE source_id = :source_id ORDER BY protocol_id",
        {"source_id": source_id},
    )
    releases = await _rows(
        database,
        "SELECT release_key, source_id, protocol_id, version, name, category, lifecycle, "
        "specification_status, implementation_status, runtime_adapter "
        "FROM protocol_release WHERE source_id = :source_id",
        {"source_id": source_id},
    )
    by_protocol: dict[str, list[dict]] = defaultdict(list)
    for release in releases:
        by_protocol[release["protocol_id"]].append(release)
    reader_artifacts = await _rows(
        database,
        "SELECT release.protocol_id, release.version, artifact.artifact_id, artifact.artifact_path, "
        "artifact.artifact_kind, artifact.media_type "
        "FROM artifact JOIN protocol_release AS release "
        "ON release.release_key = artifact.release_key "
        "WHERE release.source_id = :source_id AND artifact.text_content IS NOT NULL "
        "ORDER BY release.protocol_id, release.version, artifact.artifact_path",
        {"source_id": source_id},
    )
    artifacts_by_release: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for artifact in reader_artifacts:
        artifact["file_name"] = artifact["artifact_path"].rsplit("/", 1)[-1]
        artifact["detail_url"] = _document_url(
            source_id,
            artifact["protocol_id"],
            artifact["version"],
            artifact["artifact_path"],
        )
        artifacts_by_release[(artifact["protocol_id"], artifact["version"])].append(artifact)
    reader_sections = await _rows(
        database,
        "SELECT release.protocol_id, release.version, section.section_key, "
        "artifact.artifact_path, section.heading, section.line_start "
        "FROM document_section AS section "
        "JOIN protocol_release AS release ON release.release_key = section.release_key "
        "JOIN artifact ON artifact.artifact_id = section.artifact_id "
        "WHERE release.source_id = :source_id AND artifact.text_content IS NOT NULL "
        "ORDER BY release.protocol_id, release.version, artifact.artifact_path, section.line_start",
        {"source_id": source_id},
    )
    sections_by_release: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for section in reader_sections:
        sections_by_release[(section["protocol_id"], section["version"])].append(section)
    cards: list[dict] = []
    for family in families:
        protocol_releases = sorted(
            by_protocol.get(family["protocol_id"], []),
            key=lambda value: _version_key(value["version"]),
        )
        if not protocol_releases:
            continue
        latest = protocol_releases[-1]
        layer = _layer(latest["category"])
        release_nodes = []
        for item in reversed(protocol_releases):
            release_documents = artifacts_by_release.get(
                (family["protocol_id"], item["version"]),
                [],
            )
            explicit_contract_paths = {
                document["artifact_path"]
                for document in release_documents
                if _is_contract_artifact(document)
            }
            contract_documents = []
            for document in release_documents:
                artifact_path = document["artifact_path"]
                if artifact_path in explicit_contract_paths:
                    contract_documents.append(
                        {
                            "artifact_path": artifact_path,
                            "file_name": document["file_name"],
                            "direct_url": _document_url(
                                source_id,
                                family["protocol_id"],
                                item["version"],
                                artifact_path,
                                kind="contract",
                            ),
                            "entries": [],
                        }
                    )
                    continue
                contract_sections = [
                    section
                    for section in sections_by_release.get(
                        (family["protocol_id"], item["version"]),
                        [],
                    )
                    if section["artifact_path"] == artifact_path
                    and _is_contract_section(section)
                ]
                if contract_sections:
                    contract_documents.append(
                        {
                            "artifact_path": artifact_path,
                            "file_name": document["file_name"],
                            "direct_url": None,
                            "entries": [
                                {
                                    **section,
                                    "detail_url": _document_url(
                                        source_id,
                                        family["protocol_id"],
                                        item["version"],
                                        artifact_path,
                                        kind="contract",
                                        section_key=section["section_key"],
                                    ),
                                }
                                for section in contract_sections
                            ],
                        }
                    )
            release_nodes.append(
                {
                    **item,
                    "detail_url": _detail_url(source_id, family["protocol_id"], item["version"]),
                    "documents": release_documents,
                    "contract_documents": contract_documents,
                    "contract_count": sum(
                        1 if document["direct_url"] else len(document["entries"])
                        for document in contract_documents
                    ),
                }
            )
        cards.append(
            {
                **family,
                "layer": layer,
                "major_layer": _major_layer(latest["category"]),
                "latest": latest,
                "versions": [item["version"] for item in reversed(protocol_releases)],
                "release_nodes": release_nodes,
                "detail_url": _detail_url(source_id, family["protocol_id"], latest["version"]),
            }
        )
    return sorted(cards, key=lambda value: (value["layer"]["order"], value["protocol_id"]))


def _catalog_groups(
    cards: list[dict],
    active_protocol_id: str | None = None,
    active_version: str | None = None,
    active_document: str | None = None,
    active_kind: str | None = None,
    active_section: str | None = None,
) -> list[dict]:
    groups = []
    known_categories = {
        category
        for major in FOUR_MAJOR_LAYERS
        for category in major["categories"]
    }
    catalog_cards = []
    for card in cards:
        protocol_active = card["protocol_id"] == active_protocol_id
        release_nodes = []
        for release in card["release_nodes"]:
            release_active = protocol_active and release["version"] == active_version
            contract_documents = []
            for contract_document in release["contract_documents"]:
                direct_active = (
                    release_active
                    and active_kind == "contract"
                    and not active_section
                    and contract_document["artifact_path"] == active_document
                )
                entries = [
                    {
                        **entry,
                        "active": release_active
                        and entry["section_key"] == active_section,
                    }
                    for entry in contract_document["entries"]
                ]
                contract_documents.append(
                    {
                        **contract_document,
                        "active": direct_active or any(entry["active"] for entry in entries),
                        "direct_active": direct_active,
                        "entries": entries,
                    }
                )
            contract_active = any(document["active"] for document in contract_documents)
            release_nodes.append(
                {
                    **release,
                    "active": release_active,
                    "contract_active": contract_active,
                    "document_active": release_active and not contract_active,
                    "contract_documents": contract_documents,
                    "documents": [
                        {
                            **document,
                            "active": release_active
                            and active_kind != "contract"
                            and not active_section
                            and document["artifact_path"] == active_document,
                        }
                        for document in release["documents"]
                    ],
                }
            )
        catalog_cards.append(
            {
                **card,
                "active": protocol_active,
                "contract_active": any(node["contract_active"] for node in release_nodes),
                "document_active": any(node["document_active"] for node in release_nodes),
                "release_nodes": release_nodes,
            }
        )
    for major in FOUR_MAJOR_LAYERS:
        sublayers = []
        for category in major["categories"]:
            protocols = [
                card
                for card in catalog_cards
                if card["latest"]["category"] == category
            ]
            sublayers.append(
                {
                    "layer": _layer(category),
                    "protocols": protocols,
                    "contract_protocols": [
                        protocol
                        for protocol in protocols
                        if any(node["contract_count"] for node in protocol["release_nodes"])
                    ],
                    "active": any(protocol["active"] for protocol in protocols),
                    "contract_active": any(protocol["contract_active"] for protocol in protocols),
                    "document_active": any(protocol["document_active"] for protocol in protocols),
                }
            )
        if major["key"] == "foundation":
            uncategorized = [
                card
                for card in catalog_cards
                if card["latest"]["category"] not in known_categories
            ]
            if uncategorized:
                contract_protocols = [
                    protocol
                    for protocol in uncategorized
                    if any(node["contract_count"] for node in protocol["release_nodes"])
                ]
                sublayers.append(
                    {
                        "layer": DEFAULT_LAYER,
                        "protocols": uncategorized,
                        "contract_protocols": contract_protocols,
                        "active": any(card["active"] for card in uncategorized),
                        "contract_active": any(card["contract_active"] for card in uncategorized),
                        "document_active": any(card["document_active"] for card in uncategorized),
                    }
                )
        groups.append(
            {
                "major": major,
                "sublayers": sublayers,
                "protocol_count": sum(len(item["protocols"]) for item in sublayers),
                "active": any(item.get("active") for item in sublayers),
            }
        )
    return groups


async def _catalog_context(
    database,
    source_id: str,
    active_protocol_id: str | None = None,
    active_version: str | None = None,
    active_document: str | None = None,
    active_kind: str | None = None,
    active_section: str | None = None,
) -> dict:
    cards = await _release_cards(database, source_id)
    return {
        "source_id": source_id,
        "active_protocol_id": active_protocol_id,
        "groups": _catalog_groups(
            cards,
            active_protocol_id,
            active_version,
            active_document,
            active_kind,
            active_section,
        ),
        "sources": (
            {
                "source_id": "current",
                "label": "正式线",
                "url": "/?source=current",
                "active": source_id == "current",
            },
            {
                "source_id": "temp-runtime",
                "label": "演进线",
                "url": "/?source=temp-runtime",
                "active": source_id == "temp-runtime",
            },
        ),
    }


async def protocol_index(request, datasette):
    database = datasette.get_database("protocol-source")
    requested_source = request.args.get("source")
    source_id = requested_source if requested_source in {"current", "temp-runtime"} else "current"
    cards = await _release_cards(database, source_id)
    preferred = next(
        (card for card in cards if card["protocol_id"] == "CF-FARP"),
        cards[0] if cards else None,
    )
    if preferred:
        return Response.redirect(
            preferred["detail_url"],
            headers={"X-CartridgeFlow-Protocol-Viewer": "1"},
        )
    catalog = await _catalog_context(database, source_id)
    body = await datasette.render_template(
        "protocol_home.html",
        {"catalog": catalog, "major_layers": FOUR_MAJOR_LAYERS},
        request=request,
        view_name="protocol-knowledge-home",
    )
    return Response.html(body, headers={"X-CartridgeFlow-Protocol-Viewer": "1"})


async def protocol_detail(request, datasette):
    source_id = request.url_vars["source_id"]
    protocol_id = request.url_vars["protocol_id"]
    database = datasette.get_database("protocol-source")
    family_rows = await _rows(
        database,
        "SELECT source_id, protocol_id, name, owner, responsibility_boundary, exclusions_json "
        "FROM protocol_family WHERE source_id = :source_id AND protocol_id = :protocol_id",
        {"source_id": source_id, "protocol_id": protocol_id},
    )
    if not family_rows:
        return Response.html("<h1>找不到该协议</h1><p><a href='/'>返回知识库</a></p>", status=404)
    family = family_rows[0]
    releases = await _rows(
        database,
        "SELECT release_key, source_id, protocol_id, version, name, category, lifecycle, "
        "specification_status, implementation_status, runtime_adapter, release_path "
        "FROM protocol_release WHERE source_id = :source_id AND protocol_id = :protocol_id",
        {"source_id": source_id, "protocol_id": protocol_id},
    )
    releases.sort(key=lambda value: _version_key(value["version"]), reverse=True)
    requested_version = request.args.get("version")
    release = next(
        (item for item in releases if item["version"] == requested_version),
        releases[0],
    )
    artifacts = await _rows(
        database,
        "SELECT artifact_id, artifact_path, artifact_kind, media_type, byte_size, content_digest, text_content "
        "FROM artifact WHERE release_key = :release_key ORDER BY artifact_path",
        {"release_key": release["release_key"]},
    )
    sections = await _rows(
        database,
        "SELECT section.section_key, section.artifact_id, artifact.artifact_path, "
        "section.heading, section.anchor, section.heading_level, section.line_start, "
        "section.line_end, section.content FROM document_section AS section "
        "JOIN artifact ON artifact.artifact_id = section.artifact_id "
        "WHERE section.release_key = :release_key ORDER BY artifact.artifact_path, section.line_start",
        {"release_key": release["release_key"]},
    )
    documents = []
    for artifact in artifacts:
        if artifact.get("text_content") is None:
            continue
        documents.append(_document_context(artifact))
    requested_document = request.args.get("document")
    requested_section = request.args.get("section")
    selected_section = next(
        (section for section in sections if section["section_key"] == requested_section),
        None,
    )
    preferred = next(
        (
            document
            for priority in DOCUMENT_PRIORITY
            for document in documents
            if str(document["artifact_path"]).lower().endswith(priority)
        ),
        documents[0] if documents else None,
    )
    selected_path = (
        selected_section["artifact_path"]
        if selected_section
        else requested_document or (preferred["artifact_path"] if preferred else None)
    )
    selected_document = next(
        (document for document in documents if document["artifact_path"] == selected_path),
        preferred,
    )
    documents = [
        {**document, "selected": document is selected_document}
        for document in documents
    ]
    selected_section_context = (
        {
            **selected_section,
            "rendered_content": render_markdown(
                selected_section["content"],
                extensions=["tables", "fenced_code"],
            ),
        }
        if selected_section
        else None
    )
    context = {
        "family": family,
        "layer": _layer(release["category"]),
        "major_layer": _major_layer(release["category"]),
        "catalog": await _catalog_context(
            database,
            source_id,
            protocol_id,
            release["version"],
            selected_document["artifact_path"] if selected_document else None,
            "contract" if request.args.get("kind") == "contract" or selected_section else None,
            selected_section["section_key"] if selected_section else None,
        ),
        "source_id": source_id,
        "release": release,
        "releases": releases,
        "documents": documents,
        "selected_document": selected_document,
        "selected_section": selected_section_context,
        "detail_url": _detail_url(source_id, protocol_id),
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
        (r"/protocol/(?P<source_id>[a-z0-9_-]+)/(?P<protocol_id>[A-Za-z0-9_-]+)/?$", protocol_detail),
    ]
