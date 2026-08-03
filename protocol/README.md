# 协议发布目录

`protocol/` 存放完整的协议发布单元：人类可读规范正文、机器快照、词表和治理记录。发布生命周期、默认新建版本、迁移目标和工件定位以 `catalog/release_manifest.json` 为唯一权威。

```text
protocol/
  base/          基础宿主契约；每个版本自含正文、快照和 Base 工具包
  catalog/       发布清单
  flow-authoring/ CF-FARP；每个版本自含正文、快照和词表
  tuning/       CF-TUNING；受宿主信任的内部调优与配方发布协议
  release-envelope/ CF-CRE；每个版本自含正文、快照和词表
  governance/    生命周期、迁移索引和治理规则
  README.md      本导航
```

协议类别先区分 Base、Flow Authoring、Tuning 与 Release Envelope，再在类别下按版本定位。例如 `flow-authoring/1.1/` 是 CF-FARP@1.1 的完整发布单元，`tuning/1.0/` 是它显式信任的独立子协议发布。新增协议或版本时必须新增独立目录；迁移资料放在版本目录的非规范迁移模块或治理目录，不能成为当前运行语义的一部分。

修改协议前先读取 `catalog/release_manifest.json`；新增版本时新增完整快照，不能覆盖历史版本。
修改后运行：

```powershell
python scripts/audit_protocol_governance.py
python scripts/run_conformance.py --quiet
```
