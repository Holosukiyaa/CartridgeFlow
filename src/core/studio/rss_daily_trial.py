"""Trial run: fetch reviewed public RSS, then compose today's AI daily with the bound model."""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import re
from xml.etree import ElementTree as ET

from cartridgeflow_dlc import McpRuntimeError, fetch_public_https_url

DEFAULT_FEEDS = (
    {"id": "hn-ai", "name": "Hacker News · AI", "url": "https://hnrss.org/newest?q=AI"},
    {"id": "mit-tr", "name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
)
MAX_ITEMS = 12
MAX_SUMMARY = 420


class TrialRunError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 502):
        self.code = code
        self.status = status
        super().__init__(message)


def _plain(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return html.unescape(" ".join(text.split()))


def _child_text_plain(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in list(node):
        local = child.tag.split("}", 1)[-1]
        if local in names:
            return _plain("".join(child.itertext()))
    return ""


def parse_feed_xml(xml_text: str, *, source_name: str, source_url: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise TrialRunError("TRIAL_FEED_INVALID", f"{source_name} 不是可解析的 RSS/Atom：{exc}", status=502) from exc
    items: list[dict] = []
    for node in root.iter():
        local = node.tag.split("}", 1)[-1]
        if local not in {"item", "entry"}:
            continue
        title = _child_text_plain(node, ("title",))
        link = _child_text_plain(node, ("link",))
        if not link:
            for child in list(node):
                if child.tag.split("}", 1)[-1] == "link":
                    link = str(child.attrib.get("href") or "").strip()
                    if link:
                        break
        published = _child_text_plain(node, ("pubDate", "published", "updated", "date"))
        summary = _child_text_plain(node, ("description", "summary", "content"))
        if not title:
            continue
        items.append({
            "title": title[:240],
            "link": link[:500],
            "published": published[:80],
            "summary": summary[:MAX_SUMMARY],
            "source": source_name,
            "feed_url": source_url,
        })
        if len(items) >= MAX_ITEMS:
            break
    return items


def fetch_feeds(feed_url: str | None = None) -> dict:
    feeds = [{"id": "custom", "name": "指定来源", "url": feed_url}] if str(feed_url or "").strip() else list(DEFAULT_FEEDS)
    collected: list[dict] = []
    fetched: list[dict] = []
    errors: list[str] = []
    for feed in feeds:
        try:
            raw = fetch_public_https_url(feed["url"], operation_id="creator.trial.fetch")
            items = parse_feed_xml(str(raw.get("content") or ""), source_name=feed["name"], source_url=str(raw.get("url") or feed["url"]))
            fetched.append({
                "id": feed["id"],
                "name": feed["name"],
                "url": raw.get("url") or feed["url"],
                "status": raw.get("status"),
                "item_count": len(items),
            })
            collected.extend(items)
        except (McpRuntimeError, TrialRunError) as exc:
            errors.append(f"{feed['name']}：{exc}")
    unique: list[dict] = []
    seen: set[str] = set()
    for item in collected:
        key = item.get("link") or item["title"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= MAX_ITEMS:
            break
    if not unique:
        raise TrialRunError("TRIAL_FEED_EMPTY", "没有从公开来源取到可用条目。" + (" ".join(errors) if errors else ""), status=502)
    return {
        "schema": "cartridgeflow.creator_trial_fetch.v1",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "feeds": fetched,
        "warnings": errors,
        "items": unique,
    }


def extractive_digest(items: list[dict], *, date_label: str) -> str:
    lines = [f"# {date_label} AI 日报（条目摘要）", "", "共创 AI 未连接，下面按来源标题整理，没有改写事实。", ""]
    for index, item in enumerate(items[:8], start=1):
        lines.append(f"{index}. **{item['title']}**")
        if item.get("summary"):
            lines.append(f"   {item['summary'][:180]}")
        if item.get("link"):
            lines.append(f"   {item['link']}")
        lines.append("")
    return "\n".join(lines).strip()


def build_compose_messages(items: list[dict], *, date_label: str) -> list[dict]:
    payload = [{"title": item["title"], "source": item.get("source"), "published": item.get("published"), "summary": item.get("summary"), "link": item.get("link")} for item in items]
    return [
        {
            "role": "system",
            "content": (
                "你是中文 AI 日报编辑。只根据用户提供的公开条目写一份今天的新闻日报。"
                "不要编造条目里没有的事实、数字或引语。不要输出 JSON。"
                "用 Markdown，结构必须是：标题、今日要点（5到8条）、分条新闻（标题/来源/为何重要/链接）、一句话结语。"
            ),
        },
        {
            "role": "user",
            "content": f"日期：{date_label}\n条目：\n{json.dumps(payload, ensure_ascii=False)}",
        },
    ]


async def compose_digest(items: list[dict]) -> dict:
    if not items:
        raise TrialRunError("TRIAL_ITEMS_EMPTY", "没有可用于整理的来源条目。", status=400)
    date_label = datetime.now().strftime("%Y年%m月%d日")
    from core.llm import chat
    from core.llm.config_manager import resolve_model

    used_model = False
    model_name = ""
    body = ""
    try:
        model = resolve_model("mentor")
        if str(getattr(model, "api_key", "") or "").strip():
            response = await chat(
                model,
                build_compose_messages(items, date_label=date_label),
                agent_name="creator_trial_digest",
                phase="trial_run",
            )
            body = str(response.get("content") or "").strip()
            used_model = bool(body)
            model_name = str(getattr(model, "model", "") or "")
    except Exception:
        body = ""
    if not body:
        body = extractive_digest(items, date_label=date_label)
    return {
        "date": date_label,
        "headline": f"{date_label} 中文 AI 日报",
        "body": body,
        "used_model": used_model,
        "model": model_name,
        "item_count": len(items),
    }


async def run_trial(feed_url: str | None = None) -> dict:
    fetched = fetch_feeds(feed_url)
    digest = await compose_digest(fetched["items"])
    return {
        "schema": "cartridgeflow.creator_trial_run.v1",
        "steps": [
            {"id": "fetch", "label": "获取已审核来源的最新内容", "status": "ok", "detail": f"{len(fetched['items'])} 条"},
            {"id": "organize", "label": "用 AI 整理成新闻", "status": "ok" if digest["used_model"] else "fallback", "detail": digest["model"] or "条目摘要"},
            {"id": "output", "label": "输出今日新闻日报", "status": "ok", "detail": digest["headline"]},
        ],
        "fetch": {key: fetched[key] for key in ("fetched_at", "feeds", "warnings")},
        "items": fetched["items"],
        "digest": digest,
    }
