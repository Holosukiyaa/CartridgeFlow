# CartridgeFlow 独立 HTML 前端

这个目录是重新搭建的独立前端，不依赖 `src/frontend` 的 React 组件、路由或样式。

当前使用原始 HTML、CSS 和 JavaScript 承载概览、Flow 管理、运行诊断、资源中心、打包发布和系统设置；资源配置以弹窗形式存在。

视觉资产按职责拆分：Lucide 提供功能图标，Simple Icons 提供技术品牌标识，Web Awesome 按需提供复杂交互组件，Motion 提供克制的页面动效。依赖都从本地加载，不使用 CDN；具体边界见 [前端图标、素材与动效规范](../../docs/design/FRONTEND_ASSET_SYSTEM.md)。

首次运行先安装锁定依赖：

```powershell
$env:PATH = "..\..\.tools\runtimes\node;$env:PATH"
npm.cmd install
```

启动方式：

```powershell
..\..\.tools\runtimes\python\python.exe server.py
```

然后访问 `http://127.0.0.1:5174`。专用静态服务器会为 HTML、CSS 和 JavaScript 发送 `no-store`，避免开发期间继续读取旧样式。页面通过 `http://127.0.0.1:8765` 读取底座 API。

当前一级页面已经使用真实 API：全局概览、卡带管理、运行诊断、资源中心、打包发布和系统设置不再展示稿件数组。Flow 画布、测试台和完整资源编辑器仍由现有 React 工作台承载，新前端会打开 `http://127.0.0.1:5173` 的对应深层路由；这是迁移边界，不是新前端内部的假页面。
