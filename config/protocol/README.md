# 产品协议快照

`protocol-registry.sqlite` 是产品锁定的只读协议快照，不是协议编辑源。当前快照采用 `clean-v1` 代际，只包含四个正式协议层及其模块、数据合同和产品采用信息。

`protocol-registry.lock.json` 同时锁定：

- 权威协议仓库地址与完整 Git commit；
- `protocol-source.sqlite` 的文件摘要和逻辑摘要；
- 编译后产品快照的摘要；
- 运行兼容目录与 Base 实现声明。

协议原本只存在于独立的 [cartridgeflow-protocols](https://github.com/Holosukiyaa/cartridgeflow-protocols) 仓库。本产品不得嵌入、挂载或直接修改协议源，也不得手工编辑本目录中的 SQLite 快照。

协议发布完成并提交到独立仓后，在 CartridgeFlow 中显式传入协议仓工作副本，原子更新产品快照、Base 声明和协议锁：

```powershell
python scripts/update_protocol_registry.py --protocol-repository C:\path\to\cartridgeflow-protocols
python scripts/audit_protocol_registry.py
python scripts/run_conformance.py --quiet
```
