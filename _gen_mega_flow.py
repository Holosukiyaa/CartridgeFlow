"""
生成 dev.mega_flow 卡带 — 204 节点 / 8 集群
"""
import json, os, random, math
from pathlib import Path

random.seed(42)

CARTRIDGE_ID = "dev.mega_flow"
BASE_DIR = Path(r"c:\_Hololab\C0\CartridgeFlow-v0.0.4-pre\cartridges\dev") / CARTRIDGE_ID
BASE_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "assets").mkdir(exist_ok=True)

CLUSTERS = [
    {"id": 0, "name": "核心架构",   "count": 30, "color": "#6c47ff",
     "actions": ["start","pass_result","save_context"]},
    {"id": 1, "name": "数据管道",   "count": 28, "color": "#2563eb",
     "actions": ["collect_inputs","save_context","pass_result"]},
    {"id": 2, "name": "用户服务",   "count": 26, "color": "#059669",
     "actions": ["collect_inputs","save_context","llm_prompt"]},
    {"id": 3, "name": "推荐引擎",   "count": 25, "color": "#d97706",
     "actions": ["llm_prompt","pass_result","save_context"]},
    {"id": 4, "name": "安全鉴权",   "count": 22, "color": "#dc2626",
     "actions": ["save_context","pass_result","collect_inputs"]},
    {"id": 5, "name": "消息队列",   "count": 24, "color": "#7c3aed",
     "actions": ["pass_result","save_context","tool_call"]},
    {"id": 6, "name": "AI 模型层", "count": 27, "color": "#0891b2",
     "actions": ["llm_prompt","pass_result","save_context"]},
    {"id": 7, "name": "监控告警",   "count": 22, "color": "#be185d",
     "actions": ["save_context","pass_result","tool_call"]},
]

TYPE_MAP = {
    "start":          "system",
    "collect_inputs": "ui",
    "llm_prompt":     "runtime",
    "save_context":   "data",
    "pass_result":    "data",
    "tool_call":      "runtime",
}

CAT_MAP = {
    "start":          "input",
    "collect_inputs": "input",
    "llm_prompt":     "process",
    "save_context":   "store",
    "pass_result":    "store",
    "tool_call":      "tool",
}

CANVAS_W = 4200
CANVAS_H = 3000
CX = CANVAS_W / 2
CY = CANVAS_H / 2
CLUSTER_R = 1200
INNER_R   = 340

nodes_meta = []
idx = 0
for cl in CLUSTERS:
    angle0 = (cl["id"] / len(CLUSTERS)) * math.pi * 2
    cx = CX + math.cos(angle0) * CLUSTER_R
    cy = CY + math.sin(angle0) * CLUSTER_R
    for i in range(cl["count"]):
        is_hub = (i == 0)
        if is_hub:
            x, y = cx, cy
        else:
            a = (i / (cl["count"]-1)) * math.pi * 2
            r = INNER_R * (0.6 + random.random() * 0.4)
            x = cx + math.cos(a) * r
            y = cy + math.sin(a) * r
        action = cl["actions"][0] if is_hub else random.choice(cl["actions"])
        if idx == 0:
            action = "start"
        nodes_meta.append({
            "idx": idx,
            "cluster": cl["id"],
            "cluster_name": cl["name"],
            "color": cl["color"],
            "hub": is_hub,
            "action": action,
            "x": round(x),
            "y": round(y),
        })
        idx += 1

TOTAL = len(nodes_meta)

edges_set = set()
edges = []

def add_edge(a, b):
    if a == b: return
    k = (min(a,b), max(a,b))
    if k in edges_set: return
    edges_set.add(k)
    edges.append({"from": str(a), "to": str(b)})

# 集群 hub 偏移计算
cl_start = []
s = 0
for cl in CLUSTERS:
    cl_start.append(s)
    s += cl["count"]

# 集群内：hub → 所有成员
for ci, cl in enumerate(CLUSTERS):
    hub = cl_start[ci]
    for j in range(cl_start[ci]+1, cl_start[ci]+cl["count"]):
        add_edge(hub, j)

# 集群内：随机内部边
for ci, cl in enumerate(CLUSTERS):
    start = cl_start[ci]
    members = list(range(start+1, start+cl["count"]))
    for m in members:
        target = random.choice(members)
        add_edge(m, target)

# 集群间：hub-hub 全连接
for i in range(len(CLUSTERS)):
    for j in range(i+1, len(CLUSTERS)):
        add_edge(cl_start[i], cl_start[j])

# 集群间：随机跨集群边
for _ in range(120):
    a = random.randint(0, TOTAL-1)
    b = random.randint(0, TOTAL-1)
    if nodes_meta[a]["cluster"] != nodes_meta[b]["cluster"]:
        add_edge(a, b)

# 构造 states
states = {}
for nm in nodes_meta:
    sid = str(nm["idx"])
    action = nm["action"]
    state_type = TYPE_MAP.get(action, "data")
    category = CAT_MAP.get(action, "store")
    hub_suffix = " Hub" if nm["hub"] else ""
    title = f"{nm['cluster_name']}{hub_suffix} {nm['idx']}"[:32]
    input_key  = f"data_{nm['idx']}"
    output_key = f"result_{nm['idx']}"

    state = {
        "type": state_type,
        "title": title,
        "action": action,
        "params": {
            "node_category": category,
            "input": input_key,
            "output": output_key,
            "description": f"{nm['cluster_name']} — 节点 {nm['idx']}",
        },
    }

    if action == "start":
        state["type"] = "system"
        state["params"] = {"node_category": "input", "description": "流程入口"}

    elif action == "llm_prompt":
        state["params"]["system_prompt"] = f"你是{nm['cluster_name']}的专家，请根据输入完成分析任务。"
        state["params"]["prompt"] = "请分析以下数据并给出结构化结论："
        state["model_role"] = "runtime"
        state["params"]["preset"] = "analyze"
        state["params"]["preset_config"] = {
            "goal": f"{nm['cluster_name']} 数据分析",
            "output_name": output_key,
        }

    elif action == "save_context":
        state["params"]["save_to"] = f"context.{output_key}"
        state["params"]["preset"] = "context"
        state["params"]["preset_config"] = {
            "key": f"context.{output_key}",
            "source": input_key,
        }

    elif action == "collect_inputs":
        state["params"]["fields"] = "user_input"
        state["params"]["preset"] = "user_form"
        state["params"]["preset_config"] = {
            "fields": "user_input",
            "output_name": output_key,
        }

    elif action == "pass_result":
        state["params"]["preset"] = "broadcast"
        state["params"]["preset_config"] = {
            "mapping": f"{input_key} -> {output_key}",
        }

    elif action == "tool_call":
        fname = f"mega_output/node_{nm['idx']}.txt"
        state["params"]["preset"] = "filesystem_write"
        state["params"]["preset_config"] = {
            "path": fname,
            "source": input_key,
            "output_name": output_key,
        }
        state["params"]["tools"] = [{
            "type": "builtin",
            "server": "filesystem",
            "tool": "write_file",
            "params": {"path": fname, "content": f"store:{input_key}"},
            "enabled": True,
            "output": output_key,
        }]

    # layout
    state["x"] = nm["x"]
    state["y"] = nm["y"]

    # next: 顺序连下一个节点（仅为让引擎有 next 推进）
    if nm["idx"] < TOTAL - 1:
        state["next"] = str(nm["idx"] + 1)

    states[sid] = state

# 最后一个节点是 terminal
last_id = str(TOTAL - 1)
states[last_id]["type"] = "terminal"
states[last_id]["title"] = "完成"
states[last_id].pop("next", None)

root_flow = {
    "schema_version": "1.0",
    "id": f"{CARTRIDGE_ID}.root",
    "name": "超复杂网络图谱流程",
    "mode": "lifecycle",
    "cartridge_id": CARTRIDGE_ID,
    "start": "0",
    "states": states,
    "edges": edges,
}

manifest = {
    "schema_version": "1.0",
    "id": CARTRIDGE_ID,
    "name": "超复杂网络图谱",
    "version": "0.1.0",
    "kind": "runtime_cartridge",
    "category": "dev",
    "description": f"204 节点 / 8 集群 / {len(edges)} 条边的超复杂网络流程，用于测试可视化与执行引擎极限",
    "publisher": {"id": "local", "name": "Local Developer", "type": "local", "verified": False},
    "branding": {"tags": ["test", "mega", "complex", "lab"]},
    "welcome": {"type": "markdown", "entry": "assets/welcome.md"},
    "root_flow": {"entry": "root.flow.json", "mode": "lifecycle", "required": True},
    "runtime": {"type": "lab", "adapter": "builtin:lab"},
    "workspace": {"type": "none", "required": False, "open_policy": "manual"},
    "environment": {"os": ["windows", "macos", "linux"], "requires": []},
    "permissions": [],
    "dependencies": [],
    "inputs": [],
    "outputs": [],
    "artifacts": {"store_policy": "run_scoped", "visibility_default": "user", "allowed_types": ["text"]},
    "delivery": {"type": "summary_with_artifacts", "show_artifacts": True},
}

welcome_md = f"""# 超复杂网络图谱

**{TOTAL} 节点 · 8 集群 · {len(edges)} 条边**

这是一个专为测试 Flow 工作台可视化极限而生成的超复杂流程。

## 集群构成

| 集群 | 节点数 | 主要动作 |
|------|--------|---------|
{"".join(f"| {cl['name']} | {cl['count']} | {', '.join(set(cl['actions']))} |\\n" for cl in CLUSTERS)}

## 使用方式

在设计台中打开可观察到完整的 8 集群布局，每个集群拥有一个 Hub 节点向外辐射连接。
"""

with open(BASE_DIR / "root.flow.json", "w", encoding="utf-8") as f:
    json.dump(root_flow, f, ensure_ascii=False, indent=2)
with open(BASE_DIR / "manifest.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
with open(BASE_DIR / "assets" / "welcome.md", "w", encoding="utf-8") as f:
    f.write(welcome_md)

print(f"完成：{TOTAL} 节点 / {len(edges)} 条边")
print(f"输出目录：{BASE_DIR}")
