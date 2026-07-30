# 协议文档

协议文档按职责分组。`protocol/catalog/release_manifest.json` 是流程协议生命周期和独立发行封装轨道的机器可读权威来源；它记录默认新流程版本、默认新发行封装版本，以及每个快照的规范文档路径。

```text
docs/protocol/
  base-contract/    基础宿主契约发行文档
  flow-authoring/   CF-FARP 流程协议发行文档
  release-envelope/ CF-CRE 卡带发行封装协议文档
  governance/       供人阅读的协议治理规则
```

进行当前工作时，应使用发布清单引用的最新文档。历史文档是不可变的发行证据；应增加新版本，而不是改写旧协议文档。
