# 协议机器工件目录

`protocol/` 只存放机器读取的协议工件。发布生命周期、默认新建版本、迁移目标和工件定位以
`catalog/release_manifest.json` 为唯一权威。

```text
protocol/
  base/          Base Contract 机器快照
  catalog/       发布清单
  governance/    可变治理镜像与目录说明
  releases/      CF-FARP 发布快照
  tooling/       工具包注册表
  vocabulary/    capability 与 profile 词表快照
  README.md      本导航
```

协议正文在 `docs/protocol/` 中按 Base Contract、Flow Authoring 和治理规则分类。
修改协议前先读取 `catalog/release_manifest.json`；新增版本时新增完整快照，不能覆盖历史版本。
修改后运行：

```powershell
python scripts/audit_protocol_governance.py
python scripts/run_conformance.py --quiet
```
