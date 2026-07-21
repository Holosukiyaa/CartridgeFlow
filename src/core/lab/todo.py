import re


CHECKBOX_PATTERN = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.+?)\s*$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TASK_ID_PATTERN = re.compile(r"^`([^`]+)`\s*")


def parse_todo_markdown(content: str) -> dict:
    title = "TODO"
    current_section = "未分组"
    in_fence = False
    items = []

    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        heading = HEADING_PATTERN.match(stripped)
        if heading:
            heading_level = len(heading.group(1))
            heading_text = heading.group(2).strip()
            if heading_level == 1:
                title = heading_text
            else:
                current_section = heading_text
            continue

        checkbox = CHECKBOX_PATTERN.match(line)
        if not checkbox:
            continue
        checked = checkbox.group(1).lower() == "x"
        raw_text = checkbox.group(2).strip()
        task_id_match = TASK_ID_PATTERN.match(raw_text)
        task_id = task_id_match.group(1).strip() if task_id_match else ""
        text = TASK_ID_PATTERN.sub("", raw_text, count=1).strip()
        text = re.sub(r"`([^`]+)`", r"\1", text)
        priority_source = f"{current_section} {task_id} {text}".upper()
        priority_match = re.search(r"\bP([0-2])\b", priority_source)
        priority = f"P{priority_match.group(1)}" if priority_match else ""
        if not priority and any(word in priority_source for word in ["阻断", "BLOCKER", "BLOCKING"]):
            priority = "P0"

        items.append({
            "id": task_id,
            "text": text,
            "raw": raw_text,
            "checked": checked,
            "section": current_section,
            "priority": priority,
            "line": line_number,
        })

    completed = sum(1 for item in items if item["checked"])
    return {
        "title": title,
        "total": len(items),
        "open": len(items) - completed,
        "completed": completed,
        "items": items,
    }
