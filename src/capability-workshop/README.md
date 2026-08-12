# CartridgeFlow 能力工作台

这里是可执行能力设计、验证和不可变发布工作区。前端只通过已记录的 HTTP API 编辑技术 Flow 事实，不直接读取后端文件。API 与前端不同源时，通过 `VITE_API_BASE_URL` 配置地址。

```powershell
npm --prefix src/capability-workshop install
npm --prefix src/capability-workshop run dev
npm --prefix src/capability-workshop run test
npm --prefix src/capability-workshop run build
```

控制台只请求已公开的投影视图，包括 Flow 详情与文件、分析、验证、调优、资源目录、发布预检和 conformance。任何 API 响应进入 React 状态或错误消息前都会脱敏：敏感字段值、敏感 URL 查询值、URL 用户信息密码和 Bearer token 会替换为 `[redacted]`；普通 URL 与引用元数据仍然可见。
