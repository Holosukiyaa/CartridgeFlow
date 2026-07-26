# CartridgeFlowLite

CartridgeFlowLite 是面向专属 AI 服务开发者的轻量卡带工作台。它把 Flow 设计、模型连接、工具启用、真实运行、失败恢复和产物查看集中在同一张画布中，不再保留完整版本的全局概览、独立资源中心和发布后台。

## 核心体验

- 在无限画布上设计和整理 Flow。
- 用协议驱动的主节点展示开发时最重要的信息。
- 按需展开可拖动、可钉住的节点详情卡片。
- 在工作台内配置本机模型连接和 Flow 工具。
- 真实运行 Flow，并在失败时查看日志和恢复入口。
- 在当前卡带菜单中创建、导入、切换和维护卡带。

模型 URL、API Key、本机凭据和工具实例保存在 `.data/user/config/`，不跟随卡带外传。卡带只保存可迁移的 Flow、配方、角色引用和专属资产。

## 快速开始

需要 Windows、Python 3、Node.js 和 npm，均由开发者自行安装并加入 PATH。Lite 不下载或携带 Python、Node 运行时。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
python scripts/launch.py
```

也可以双击 `run.bat`。浏览器会打开 `http://127.0.0.1:5173`，启动后直接进入最近使用的卡带工作台；没有卡带时可在工作台内创建或导入。

## 验证

```powershell
python scripts/run_conformance.py
npm --prefix src/frontend run build
```

## 项目边界

- `src/`：后端、核心运行能力和唯一的 React 工作台。
- `config/`：可提交的能力声明、默认策略和安全空白模板。
- `protocol/`：机器可读协议与能力注册表。
- `docs/`：架构、维护、规划和协议正文。
- `scripts/`：依赖安装、启动和自动测试。
- `.data/`：用户数据、运行记录和报告，不进入 Git。

业务能力应由卡带或其 DLC 提供，不能写进通用底座。当前实现以 `config/base/BASE_IMPLEMENTATION.json` 为准。

更多信息见 [AI 快速起点](AGENT.md) 和 [文档入口](docs/README.md)。
