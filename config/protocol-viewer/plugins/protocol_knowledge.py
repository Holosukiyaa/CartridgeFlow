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
        "label": "L0 · 基础底座",
        "description": "跨卡带的宿主安全、执行服务、存储边界与兼容性底线。",
        "order": 0,
    },
    "flow-authoring": {
        "key": "flow",
        "label": "L1 · 可执行 Flow 与数据合同",
        "description": "Flow 的结构、节点、端口、输入输出、Store、工具与运行时执行契约。",
        "order": 1,
    },
    "tuning": {
        "key": "tuning",
        "label": "L1.1 · 受信语义配方",
        "description": "由 Flow 层承载的语义配方、能力匹配、调优版本与作者侧物化输入。",
        "order": 2,
    },
    "release-envelope": {
        "key": "release",
        "label": "L2 · 发行与信任封装",
        "description": "发行布局、哈希、签名、安装、激活与运行时交接。",
        "order": 3,
    },
    "runtime-profiles": {
        "key": "runtime",
        "label": "L2.1 · 运行时能力画像",
        "description": "宿主能力声明、目标协商与 fail-closed 支持检查。",
        "order": 4,
    },
}
DEFAULT_LAYER = {
    "key": "other",
    "label": "其他治理材料",
    "description": "暂未归入标准协议层的治理材料。",
    "order": 99,
}
RELATION_LABELS = {
    "requires": "依赖",
    "trusts": "信任 / 承载",
    "hosted_by": "承载于",
    "supersedes": "替代",
    "migrates_to": "迁移至",
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


def _detail_url(source_id: str, protocol_id: str, version: str | None = None) -> str:
    path = f"/protocol/{quote(source_id, safe='')}/{quote(protocol_id, safe='')}"
    return f"{path}?version={quote(version, safe='')}" if version else path


def _is_contract_artifact(artifact: dict, sections: list[dict] | None = None) -> bool:
    path = str(artifact.get("artifact_path") or "").lower()
    if artifact.get("artifact_kind") == "schema":
        return True
    if any(token in path for token in CONTRACT_TOKENS):
        return True
    return any(
        any(token in str(section.get("heading") or "").lower() for token in CONTRACT_TOKENS)
        for section in sections or []
    )


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
        "selected": selected,
        "is_json": is_json,
        "raw_content": raw,
        "rendered_content": (
            None
            if is_json
            else render_markdown(raw, extensions=["tables", "fenced_code"])
        ),
    }


async def _contract_history(database, source_id: str, protocol_id: str) -> dict:
    artifacts = await _rows(
        database,
        "SELECT release.version, artifact.artifact_id, artifact.artifact_path, "
        "artifact.artifact_kind, artifact.media_type, artifact.byte_size, artifact.content_digest "
        "FROM artifact JOIN protocol_release AS release "
        "ON release.release_key = artifact.release_key "
        "WHERE release.source_id = :source_id AND release.protocol_id = :protocol_id "
        "ORDER BY release.version, artifact.artifact_path",
        {"source_id": source_id, "protocol_id": protocol_id},
    )
    sections = await _rows(
        database,
        "SELECT release.version, section.artifact_id, artifact.artifact_path, "
        "section.heading, section.line_start "
        "FROM document_section AS section "
        "JOIN protocol_release AS release ON release.release_key = section.release_key "
        "JOIN artifact ON artifact.artifact_id = section.artifact_id "
        "WHERE release.source_id = :source_id AND release.protocol_id = :protocol_id "
        "ORDER BY release.version, artifact.artifact_path, section.line_start",
        {"source_id": source_id, "protocol_id": protocol_id},
    )
    sections_by_artifact: dict[str, list[dict]] = defaultdict(list)
    for section in sections:
        sections_by_artifact[section["artifact_id"]].append(section)
    contract_artifacts = [
        artifact
        for artifact in artifacts
        if _is_contract_artifact(
            artifact,
            sections_by_artifact.get(artifact["artifact_id"], []),
        )
    ]
    contract_sections = [
        section
        for section in sections
        if any(token in str(section.get("heading") or "").lower() for token in CONTRACT_TOKENS)
    ]
    versions: dict[str, dict] = {}
    for artifact in contract_artifacts:
        versions.setdefault(
            artifact["version"],
            {"version": artifact["version"], "artifact_count": 0, "section_count": 0},
        )["artifact_count"] += 1
    for section in contract_sections:
        versions.setdefault(
            section["version"],
            {"version": section["version"], "artifact_count": 0, "section_count": 0},
        )["section_count"] += 1
    return {
        "artifact_count": len(contract_artifacts),
        "section_count": len(contract_sections),
        "versions": sorted(
            versions.values(),
            key=lambda value: _version_key(value["version"]),
            reverse=True,
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
        contract_history = await _contract_history(
            database,
            source_id,
            family["protocol_id"],
        )
        cards.append(
            {
                **family,
                "layer": layer,
                "latest": latest,
                "versions": [item["version"] for item in reversed(protocol_releases)],
                "detail_url": _detail_url(source_id, family["protocol_id"], latest["version"]),
                "contract_count": contract_history["artifact_count"],
                "contract_section_count": contract_history["section_count"],
                "contract_version_count": len(contract_history["versions"]),
            }
        )
    return sorted(cards, key=lambda value: (value["layer"]["order"], value["protocol_id"]))


async def protocol_index(request, datasette):
    database = datasette.get_database("protocol-source")
    line_context = []
    for source_id, title, description in (
        (
            "current",
            "current · 正式协议线",
            "已提交并供产品消费的协议层级。协议详情默认进入当前最新版本。",
        ),
        (
            "temp-runtime",
            "temp-runtime · 演进协议线",
            "临时运行时协议线，单独展示，用于比较与治理，不与正式线混合。",
        ),
    ):
        cards = await _release_cards(database, source_id)
        layers: dict[str, dict] = {}
        for card in cards:
            layer = card["layer"]
            layers.setdefault(
                layer["key"],
                {"layer": layer, "protocols": []},
            )["protocols"].append(card)
        line_context.append(
            {
                "source_id": source_id,
                "title": title,
                "description": description,
                "layers": sorted(layers.values(), key=lambda value: value["layer"]["order"]),
            }
        )
    body = await datasette.render_template(
        "protocol_home.html",
        {"lines": line_context},
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
    sections_by_artifact: dict[str, list[dict]] = defaultdict(list)
    for section in sections:
        sections_by_artifact[section["artifact_id"]].append(section)
    contract_artifacts = [
        artifact
        for artifact in artifacts
        if _is_contract_artifact(artifact, sections_by_artifact.get(artifact["artifact_id"], []))
    ]
    contract_sections = [
        section
        for section in sections
        if any(token in str(section.get("heading") or "").lower() for token in CONTRACT_TOKENS)
    ]
    contract_history = await _contract_history(database, source_id, protocol_id)
    documents = []
    for artifact in artifacts:
        if artifact.get("text_content") is None:
            continue
        documents.append(_document_context(artifact))
    requested_document = request.args.get("document")
    preferred = next(
        (
            document
            for priority in DOCUMENT_PRIORITY
            for document in documents
            if str(document["artifact_path"]).lower().endswith(priority)
        ),
        documents[0] if documents else None,
    )
    selected_path = requested_document or (preferred["artifact_path"] if preferred else None)
    selected_document = next(
        (document for document in documents if document["artifact_path"] == selected_path),
        preferred,
    )
    documents = [
        {**document, "selected": document is selected_document}
        for document in documents
    ]
    target_releases = {
        (item["source_id"], item["protocol_id"], item["version"]): item
        for item in await _rows(
            database,
            "SELECT source_id, protocol_id, version, name FROM protocol_release",
        )
    }
    relation_rows = await _rows(
        database,
        "SELECT relation_type, target_source_id, target_protocol_id, target_version, metadata_json "
        "FROM release_relation WHERE source_release_key = :release_key ORDER BY relation_type, target_protocol_id",
        {"release_key": release["release_key"]},
    )
    relations = []
    for relation in relation_rows:
        target_source = relation["target_source_id"] or source_id
        target = target_releases.get(
            (target_source, relation["target_protocol_id"], relation["target_version"]),
            {},
        )
        relations.append(
            {
                **relation,
                "label": RELATION_LABELS.get(relation["relation_type"], relation["relation_type"]),
                "target_name": target.get("name") or relation["target_protocol_id"],
                "target_url": _detail_url(
                    target_source,
                    relation["target_protocol_id"],
                    relation["target_version"],
                ),
            }
        )
    context = {
        "family": family,
        "layer": _layer(release["category"]),
        "source_id": source_id,
        "release": release,
        "releases": releases,
        "relations": relations,
        "documents": documents,
        "selected_document": selected_document,
        "contract_artifacts": contract_artifacts,
        "contract_sections": [
            {**section, "rendered_content": render_markdown(section["content"], extensions=["tables", "fenced_code"])}
            for section in contract_sections
        ],
        "contract_history": contract_history,
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
