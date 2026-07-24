const flowItems = [
  ['user-onboarding-flow', '新用户注册、验证、资料完善与欢迎流程。', 'cartridge_dev_0f3a1c', 'v1.4.2', 'CF-PROTO 2.1', 'sandbox', '开发运行', 'green'],
  ['billing-retry-flow', '账单支付失败重试与通知流程。', 'cartridge_dev_1a9b7e', 'v2.0.0', 'OpenFlow 1.8', 'staging', '调试运行', 'blue'],
  ['order-fulfillment-flow', '订单接收、库存校验、发货与客服通知流程。', 'cartridge_dev_2b8d4f', 'v1.3.1', 'CF-PROTO 2.1', 'sandbox', '开发运行', 'green'],
  ['document-parse-flow', '文档上传、解析、结构化与存储流程。', 'cartridge_dev_3c7e9a', 'v1.1.5', 'OpenFlow 1.8', 'sandbox', '批处理', 'amber'],
  ['notification-delivery-flow', '通知内容生成、渠道分发与状态回执流程。', 'cartridge_dev_4d2f6b', 'v1.2.0', 'CF-PROTO 2.1', 'staging', '开发运行', 'green'],
  ['image-inspect-flow', '图像质量检测、标注生成与结果归档流程。', 'cartridge_dev_5e9a2d', 'v1.0.3', 'OpenFlow 1.8', 'sandbox', '批处理', 'green'],
  ['vector-index-build', '文本分块、向量化与索引构建流程。', 'cartridge_dev_6f1d8c', 'v2.1.0', 'CF-PROTO 2.1', 'staging', '批处理', 'blue'],
  ['cache-warmup-flow', '系统缓存预热与关键数据加载流程。', 'cartridge_dev_7a3b9f', 'v1.0.1', 'OpenFlow 1.8', 'sandbox', '批处理', 'amber'],
]

const runItems = [
  ['dev.user-profile-sync', 'run_7a91c2b9d8f1', '完成', '05-15 14:35:22', 'green'],
  ['dev.data-cleanup-job', 'run_9b12d4c7e3a2', '执行中', '05-15 14:32:10', 'blue'],
  ['dev.report-gen-flow', 'run_e3c4f7a9b1d2', '完成', '05-15 14:28:44', 'green'],
  ['dev.image-ai-decision-test', 'run_4fc35524faec', '失败节点', '05-15 14:22:31', 'red'],
  ['dev.order-fulfillment-flow', 'run_a1b2c3d4e5f6', '完成', '05-15 14:18:09', 'green'],
  ['dev.doc-parse-flow', 'run_5d6e7f8a9b0c', '失败节点', '05-15 14:12:03', 'red'],
  ['dev.notification-send', 'run_c9d0e1f2a3b4', '完成', '05-15 14:05:47', 'green'],
  ['dev.vector-index-build', 'run_b7a6c5d4e3f2', '执行中', '05-15 13:58:21', 'blue'],
  ['dev.cache-warmup', 'run_d1e2f3a4b5c6', '完成', '05-15 13:52:18', 'green'],
]

const icon = (name, className = '') => `<i class="line-icon ${className}" data-lucide="${name}" aria-hidden="true"></i>`
const brandIcon = (name, className = '') => `<i class="brand-icon brand-${name} ${className}" aria-hidden="true"></i>`

function pageHeader(title, subtitle, actions = '', metrics = '') {
  return `<header class="subpage-header">
    <div><h1>${title}</h1><p>${subtitle}</p></div>
    <div class="subpage-header-right">${metrics}${actions}</div>
  </header>`
}

function flowCard(item) {
  const [name, description, id, version, protocol, environment, runtime, tone] = item
  return `<article class="flow-card">
    <button class="flow-card-open" data-action="open-flow"><span class="tone-dot ${tone}"></span><strong>${name}</strong><span class="editable-dot"></span><em>开发中可修改</em><span class="flow-enter">进入工作台 ${icon('arrow-right')}</span></button>
    <p>${description}</p>
    <div class="flow-meta">
      <span><small>卡带 ID</small><b>${id} ${icon('copy')}</b></span><span><small>版本</small><b>${version}</b></span><span><small>协议</small><b>${protocol}</b></span><span><small>环境</small><b>${environment}</b></span><span><small>运行类型</small><b>${runtime}</b></span>
    </div>
    <div class="flow-card-actions"><button data-action="flow-action">${icon('square-pen')}编辑信息</button><button data-action="flow-action">${icon('link')}绑定资源</button><button data-action="flow-action">${icon('folder')}打开目录</button><button class="danger-text" data-action="flow-action">${icon('trash-2')}删除卡带</button></div>
  </article>`
}

function flowsPage(empty = false) {
  const actions = `<button class="page-button">${icon('upload')}导入卡带文件</button><button class="page-button">${icon('refresh-cw')}刷新</button><button class="page-button primary">${icon('square-plus')}新建开发卡带</button>`
  const metrics = empty ? `<div class="header-mini-stats"><span>全部卡带<b>0</b></span><span>本机卡带<b class="green-text">0</b></span><span>团队卡带<b class="blue-text">0</b></span></div>` : ''
  return `<section class="workspace-page flows-page ${empty ? 'empty-mode' : ''}">
    ${pageHeader('卡带管理', empty ? '管理可迁移的 Flow、模型配方、工具与交付卡带。' : '设计、验证和打包专属服务卡带', actions)}
    ${empty ? `<div class="flow-empty-panel">
      <div class="empty-metrics">${metrics}</div>
      <div class="empty-blueprint"><div class="blueprint-cube">${icon('package-open')}</div><div class="blueprint-workflow">${icon('workflow')}</div></div>
      <h2>从第一张卡带开始</h2><p>把一个专属服务的流程、模型配方和交付方式整理成可运行、可迁移的卡带。</p>
      <div class="empty-actions"><button class="page-button primary">创建开发卡带</button><button class="page-button">导入已有卡带</button></div>
      <div class="empty-benefits"><span>${icon('hard-drive')}先保存在本机</span><i></i><span>${icon('workflow')}流程与配方随卡带迁移</span></div>
    </div>` : `<div class="flows-scroll"><div class="section-row"><h2>开发 Flow <span>${flowItems.length}</span></h2></div><div class="flow-card-grid">${flowItems.map(flowCard).join('')}</div></div>`}
  </section>`
}

function diagnosticsPage() {
  const metrics = `<div class="header-run-metrics"><span>全部运行<b>16</b></span><span>失败<b class="red-text">1</b></span><span>进行中<b class="blue-text">0</b></span><span>已完成<b class="green-text">14</b></span></div>`
  return `<section class="workspace-page diagnostics-page">
    ${pageHeader('运行诊断', '集中查看所有 Flow 的运行证据、失败原因和可安全执行的恢复动作', `<button class="page-button">${icon('refresh-cw')}刷新记录</button>`, metrics)}
    <div class="diagnostics-layout">
      <aside class="run-browser panel-frame">
        <div class="run-search">${icon('search')}搜索卡带名称或 run_id</div>
        <div class="run-tabs"><button class="active">全部</button><button>异常</button><button>进行中</button><button>已完成</button></div>
        <button class="time-filter">${icon('clock-3')}最近 24 小时 ${icon('chevron-down')}</button>
        <div class="run-list-head"><span>卡带名称 / run_id</span><span>状态 / 节点</span><span>时间</span></div>
        <div class="run-list">${runItems.map((run, index) => `<button class="run-row ${index === 3 ? 'selected' : ''}"><i class="tone-dot ${run[4]}"></i><span><strong>${run[0]}</strong><small>${run[1]}</small></span><em class="${run[4]}-text">${run[2]}${index === 3 ? '<small>decide_image_plan</small>' : ''}</em><time>${run[3]}</time></button>`).join('')}</div>
      </aside>
      <section class="diagnostic-detail">
        <div class="selected-run panel-frame">
          <div class="selected-run-main"><span class="failure-badge">失败</span><strong>dev.image-ai-decision-test</strong><small>run_id:　run_4fc35524faec ${icon('copy')}</small></div>
          <div><small>失败节点</small><b>decide_image_plan</b></div><div><small>时间</small><b>2025-05-15 14:22:31</b><small>耗时 18.42s</small></div>
          <div class="selected-actions"><button class="page-button primary">${icon('play')}打开测试台</button><button class="page-button" data-action="copy-diagnostic">${icon('copy')}复制最近诊断</button><button class="page-button" data-action="export-diagnostic">${icon('upload')}导出 JSON</button><button class="page-button danger-text" data-action="delete-run">${icon('trash-2')}删除记录</button></div>
        </div>
        <div class="cause-recovery panel-frame">
          <div class="root-cause"><h2>根因</h2><dl><dt>错误码</dt><dd class="red-text">PROVIDER_CONFIGURATION_MISSING</dd><dt>说明</dt><dd>当前模型配方还没有连接可用的本地模型配置。</dd><dt>分类</dt><dd>provider</dd><dt>节点</dt><dd>decide_image_plan</dd><dt>可重试</dt><dd class="red-text">否</dd></dl></div>
          <div class="recovery-actions"><h2>恢复动作</h2><button disabled>${icon('refresh-cw')}重试当前节点（不可用）<small>不可重试：根因不满足可重试条件</small></button><button disabled>${icon('play')}从检查点继续（不可用）<small>无可用于继续的检查点</small></button><button>${icon('rotate-ccw')}使用原始输入重开<small>基于本次运行的原始输入，重新开始执行 Flow</small></button></div>
        </div>
        <div class="evidence-grid">
          <div class="event-panel panel-frame"><div class="panel-title"><h2>事件时间线</h2><span>19 项</span></div><div class="timeline">${['Flow 开始','节点开始 initialize_context','节点完成 initialize_context','节点开始 fetch_user_input','节点完成 fetch_user_input','节点开始 decide_image_plan','节点失败 decide_image_plan'].map((label, i) => `<div class="timeline-row ${i > 4 ? 'error' : ''}"><time>14:22:${13 + i}.10${i}</time><i></i><span>${label}<small>${i === 6 ? 'PROVIDER_CONFIGURATION_MISSING' : '运行事件已记录'}</small></span><b>${icon('chevron-down')}</b></div>`).join('')}</div></div>
          <div class="checkpoint-panel panel-frame"><div class="panel-title"><h2>检查点</h2><span>8 项</span></div><div class="checkpoint-table"><div class="table-head"><span>检查点名称</span><span>时间</span><span>状态</span><span>可用性</span></div>${['initialize_context','fetch_user_input','validate_input','build_prompt','decide_image_plan','post_validate_plan','execute_tools','finalize_output'].map((name, i) => `<div><span>${name}</span><span>${i < 5 ? `14:22:${13 + i}` : '-'}</span><span class="checkpoint-state ${i < 4 ? 'green-text' : i === 4 ? 'red-text' : ''}">${i < 4 ? `${icon('circle-check')}成功` : i === 4 ? `${icon('circle-x')}失败` : `${icon('circle')}未执行`}</span><span class="${i < 4 ? 'green-text' : i === 4 ? 'red-text' : ''}">${i < 4 ? '可用于恢复' : '不可用'}</span></div>`).join('')}</div></div>
        </div>
        <div class="artifact-strip panel-frame"><div data-action="toggle-disclosure" role="button" tabindex="0" aria-expanded="true"><h2>产物与交付 <span>（0 项）</span></h2><b>${icon('chevron-up')}</b></div><p><strong>暂无产物</strong><small>当前运行未生成任何产物或交付物。</small></p></div>
      </section>
    </div>
  </section>`
}

function resourcesPage() {
  const actions = `<button class="page-button">${icon('refresh-cw')}刷新状态</button><button class="page-button primary" data-action="open-resource-modal">配置资源</button>`
  return `<section class="workspace-page resources-page">
    ${pageHeader('资源中心', '集中查看底座可调用的模型、工具、本机环境与待分配需求。', actions)}
    <div class="resources-content">
      <div class="resource-summary panel-frame"><span>${icon('box')}<em>模型连接<b class="green-text">1/1</b></em></span><span>${icon('wrench')}<em>工具资源<b class="blue-text">0/0</b></em></span><span>${icon('clipboard-list')}<em>待分配需求<b class="blue-text">0</b></em></span><span>${icon('code-xml')}<em>本机变量<b class="blue-text">0/11</b></em></span></div>
      <div class="resource-main-grid">
        <article class="resource-table-card panel-frame"><h2>模型连接</h2><div class="resource-table"><div class="table-head"><span>资源名称</span><span>模型名</span><span>协议</span><span>状态</span><span>使用情况</span><span>操作</span></div><div><span class="resource-brand-name">${brandIcon('deepseek')}Default DeepSeek</span><span>deepseek-v4-flash</span><span>chat_completions</span><span class="status-pill green">${icon('circle-check')}连接正常</span><span class="blue-text">5 处使用</span><span><button>查看详情</button> <button>新增模型</button></span></div></div></article>
        <article class="tool-empty-card panel-frame"><h2>工具连接</h2><div class="compact-empty"><div>${icon('briefcase-business')}</div><strong>暂无可用工具</strong><p>支持远程 API、OpenAPI、MCP 和本机插件。</p><span><button class="page-button">查看详情</button><button class="page-button orange-text">新增工具</button></span></div></article>
      </div>
      <div class="resource-bottom-grid">
        <article class="environment-card panel-frame"><h2>底座环境</h2><div class="environment-list">${[['Python','3.13.14','正常','green','python','brand'],['Node.js','v24.18.0','正常','green','nodedotjs','brand'],['Git','2.45.2','正常','green','git','brand'],['FFmpeg','6.1.1','需要关注','amber','ffmpeg','brand'],['工作区写入','/workspace','正常','green','folder','lucide']].map(item => `<div>${item[5] === 'brand' ? brandIcon(item[4], 'environment-icon') : icon(item[4], 'environment-icon')}<b>${item[0]}</b><span>${item[1]}</span><em class="status-pill ${item[3]}">${item[3] === 'amber' ? icon('circle-alert') : icon('circle-check')}${item[2]}</em><button>查看详情 ${icon('chevron-right')}</button></div>`).join('')}</div><footer>共 5 项检查，<b class="orange-text">1 项需要关注</b><button>重新检查 ${icon('refresh-cw')}</button></footer></article>
        <div class="resource-side-stack"><article class="requirements-card panel-frame"><h2>待处理需求</h2><div><i>${icon('circle-check')}</i><span><strong>当前资源角色已满足</strong><p>已满足所有待分配的资源需求，可继续开发与运行。</p></span><button class="page-button orange-text" data-action="open-resource-modal">进入配置</button></div></article><article class="local-vars-card panel-frame"><h2>本机变量</h2><div><span>${icon('shield-check')}敏感状态 <b class="status-pill green">未暴露</b></span><button class="page-button">查看敏感状态</button></div><div><span>${icon('code-xml')}引用位置 <b class="status-pill">已引用 0</b></span><button class="page-button">查看引用位置</button></div></article></div>
      </div>
    </div>
    ${resourceModal()}
  </section>`
}

function resourceModal() {
  return `<div class="resource-modal-backdrop" hidden><section class="resource-modal"><header><h2>资源配置</h2><button data-action="close-resource-modal" aria-label="关闭">${icon('x')}</button></header><div class="modal-summary"><span>${icon('panels-top-left')}<em>当前工作区<b>默认工作区 ${icon('chevron-down')}</b></em></span><span>${icon('box')}<em>已连接模型<b>2 个</b></em></span><span>${icon('briefcase-business')}<em>工具连接<b>0 个</b></em></span><span>${icon('clock-3')}<em>最近同步时间<b>2025-05-15 14:22:31 ${icon('refresh-cw')}</b></em></span></div><div class="modal-scroll"><div class="modal-section-title"><h2>模型 API</h2><span><button class="page-button">${icon('upload')}导出</button><button class="page-button primary">${icon('plus')}新增</button></span></div><div class="modal-table"><div class="table-head"><span>模型名称</span><span>模型 ID</span><span>模型类型</span><span>连接状态</span><span>默认</span><span>角色分配</span><span>最近同步时间</span><span>操作</span></div><div><span>${brandIcon('deepseek')}Default DeepSeek</span><span>deepseek-v4-flash</span><span>普通文本模型</span><span class="green-text modal-state">${icon('circle-check')}连接正常</span><span class="default-pill">默认</span><span>5 个角色已分配</span><span>2025-05-15 14:22:26</span><span class="blue-text">编辑 ${icon('chevron-down')}</span></div><div><span>${brandIcon('deepseek')}DeepSeek Reasoner</span><span>deepseek-chat</span><span>推理模型</span><span class="green-text modal-state">${icon('circle-check')}可用</span><span>—</span><span>3 个角色已分配</span><span>2025-05-15 14:22:18</span><span class="blue-text">编辑 ${icon('chevron-down')}</span></div><footer>共 2 条 <span>${icon('chevron-left')}<b>1</b>${icon('chevron-right')}10 条/页 ${icon('chevron-down')}</span></footer></div><div class="modal-section-title"><h2>工具连接</h2><button class="page-button primary">${icon('plus')}新增</button></div><div class="modal-tool-empty"><div>${icon('plug-zap')}</div><strong>当前为空</strong><p>官方生图/生视频 API、OpenAPI、MCP、用户自部署服务均从这里接入</p><button class="page-button primary">${icon('plus')}新增工具连接</button></div><p class="modal-footnote">支持连接类型：官方 API（生图 / 生视频）、OpenAPI、MCP 服务、自部署服务（HTTP / gRPC）等</p></div></section></div>`
}

function releasePage() {
  const metrics = `<div class="header-run-metrics release-metrics"><span>全部产物<b>12</b></span><span>开发包<b class="blue-text">7</b></span><span>生产包<b>5</b></span><span>同步状态<b class="green-text synced-state">${icon('circle-check')}已同步</b></span></div>`
  return `<section class="workspace-page release-page">
    ${pageHeader('打包发布', '完成交付预检、迁移检查并生成可下载的卡带包', `<button class="page-button">${icon('refresh-cw')}刷新状态</button>`, metrics)}
    <div class="release-layout">
      <aside class="release-sidebar"><section class="panel-frame target-flow"><h2>选择目标 Flow</h2><div class="run-search">${icon('search')}搜索 Flow 名称或 run_id</div>${['dev.1','dev.user-profile-sync','dev.order-fulfillment-flow','dev.image-ai-decision-test','dev.report-gen-flow','dev.data-cleanup-job'].map((name,i)=>`<button class="${i===0?'selected':''}"><i class="tone-dot ${i>2?'green':'blue'}"></i><span><strong>${name}</strong><small>run_${['9b12d4c7e3a2','7a91c2b9d8f1','a1b2c3d4e5f6','4fc35524faec','e3c4f7a9b1d2','9b12d4c7e3a2'][i]}</small></span><b>v0.0.${i+1}</b></button>`).join('')}</section><section class="panel-frame release-history"><div class="panel-title"><h2>历史产物</h2><span>最近 20 条 ${icon('chevron-down')}</span></div>${['dev.1@v0.0.1 (开发包)','dev.1@v0.0.1 (预检)','dev.1@v0.0.0 (开发包)','dev.image-ai-decision-test@v0.0.1','dev.order-fulfillment-flow@v0.0.2','dev.user-profile-sync@v0.0.2'].map((name,i)=>`<div><i class="tone-dot ${i===3?'red':'green'}"></i><span>${name}<small>run_9b12d4c7e3a2</small></span><em class="${i===3?'red-text':'green-text'}">${i===3?'失败':'成功'}</em><time>2025-05-${15-i} 16:08:12</time></div>`).join('')}</section></aside>
      <main class="release-main"><div class="release-steps panel-frame"><span class="active" aria-current="step"><b>1</b><strong>预检</strong></span><i class="release-connector" aria-hidden="true"></i><span><b>2</b><strong>迁移检查</strong></span><i class="release-connector" aria-hidden="true"></i><span><b>3</b><strong>包策略</strong></span><i class="release-connector" aria-hidden="true"></i><span><b>4</b><strong>生成结果</strong></span></div><section class="preflight panel-frame"><h2>预检</h2><div class="preflight-summary"><span>${icon('circle-check')}预检通过　<b class="green-text">6/6</b></span><span>${icon('circle-x')}<b class="red-text">阻塞问题　1</b></span><span>${icon('info')}迁移内容　<b class="blue-text">5</b></span><span>${icon('circle-check')}当前包可生成</span></div><div class="preflight-body"><div><div class="table-head"><span>检查项</span><span>结果</span><span>说明</span></div>${['协议兼容','运行环境','卡带依赖','模型配方','本地工具','发布包卫生'].map(label=>`<p><span class="preflight-item">${icon('circle-check')}${label}</span><b class="green-text">通过</b><em>检查项满足当前发布要求。</em></p>`).join('')}</div><aside><h3>待处理项（阻塞）<span>1 项</span></h3><div>${icon('circle-alert')}<b>delivery_readiness.level 必须为 production</b><p>这是唯一阻塞项，修复后可生成发布包。</p><em>阻塞</em></div></aside></div></section><section class="migration panel-frame"><h2>迁移检查 <small>（已完成）</small></h2><div><span>随包携带<b class="green-text">5</b></span><span>本机重绑<b>0</b></span><span>缺失阻断<b>0</b></span><span>禁止打包<b>0</b></span></div><p>${icon('info')}迁移检查已通过：所有携带项完整，未发现阻断项，满足包策略要求。</p></section><div class="release-bottom"><section class="package-strategy panel-frame"><div class="panel-title"><h2>包策略</h2><button class="page-button">${icon('refresh-cw')}刷新预检</button></div><p>包策略：开发包</p><div class="segmented" data-choice-group><button class="active">开发包</button><button>生产包</button></div><dl><dt>协议认证</dt><dd>cf-farp-0-7-certified</dd><dt>当前版本</dt><dd>v0.0.1</dd></dl></section><section class="package-preview panel-frame"><h2>产物生成预览</h2><dl><dt>包名</dt><dd>dev.1-v0.0.1-dev.cft</dd><dt>版本</dt><dd>v0.0.1</dd><dt>协议认证</dt><dd>cf-farp-0-7-certified</dd><dt>目标 Flow</dt><dd>dev.1</dd><dt>生成类型</dt><dd>开发包</dd><dt>预计大小</dt><dd>128.7 MB（压缩后）</dd></dl><div class="package-cube">${icon('package-open')}</div></section></div></main>
    </div><footer class="release-footer"><span>${icon('circle-check')}<strong>开发包已就绪</strong><small>修复阻塞问题后即可生成可下载的开发包</small></span><div><button class="page-button">${icon('file-down')}导出预检报告</button><button class="page-button">${icon('save')}保存为草稿</button><button class="page-button primary">${icon('package-check')}生成开发包</button></div></footer>
  </section>`
}

function settingsPage() {
  return `<section class="workspace-page settings-page">
    ${pageHeader('系统设置', '界面偏好与工作台可读性，不参与模型、工具或运行环境配置', `<button class="page-button orange-text" data-action="reset-settings">${icon('refresh-cw')}恢复默认</button>`)}
    <div class="settings-layout"><section class="settings-controls panel-frame"><h2>显示偏好</h2><div class="setting-block"><h3>全局字体大小</h3><div class="range-row"><span>90%</span><input type="range" min="90" max="115" value="110" data-setting="font"><span>115%</span><b class="setting-font-value">110%</b></div></div><div class="setting-block"><h3>字体风格</h3><div class="segmented" data-setting-group="style"><button>系统默认</button><button>经典</button><button class="active">现代精密</button></div></div><div class="setting-block"><h3>界面字重</h3><div class="segmented" data-setting-group="weight"><button>标准</button><button class="active">加粗</button></div></div><div class="setting-block"><h3>界面密度</h3><div class="segmented" data-setting-group="density"><button class="active">舒展</button><button>紧凑</button></div></div><div class="setting-section"><h2>滚动与动效</h2><div class="setting-line"><strong>滚动条显示</strong><div class="segmented small" data-setting-group="scroll"><button class="active">悬停显示</button><button>始终显示</button></div></div><div class="setting-line"><strong>减少动效</strong><wa-switch class="settings-motion-switch" size="small" aria-label="减少动效"></wa-switch><span>关闭</span></div></div><div class="setting-section"><h2>保存范围</h2><div class="setting-line"><strong>保存范围</strong><div class="segmented small" data-setting-group="scope"><button class="active">当前工作区</button><button>全部工作台</button></div></div><p>变更会实时应用到右侧预览，保存后写入当前工作区配置。</p></div></section><section class="settings-preview"><div class="settings-summary panel-frame"><h2>当前值摘要</h2><div><span>保存范围<b>current_workspace</b></span><span>字体比例<b class="summary-font">110%</b></span><span>界面字重<b>bold</b></span><span>密度<b>spacious</b></span><span>滚动条<b>hover</b></span><span>动效<b class="summary-motion">normal</b></span></div></div><div class="preview-panel panel-frame"><h2>实时预览</h2><article><header><strong>运行诊断　/　预览片段</strong><span><b class="status-pill green">${icon('circle-check')}成功</b><b class="status-pill blue">${icon('info')}信息</b></span></header><div class="preview-scroll"><h3>运行诊断预览</h3><p>预览当前字体、字重与密度在真实工作台中的可读性。</p><dl><dt>run_id</dt><dd>run_4fc35524faec</dd><dt>Flow ID</dt><dd>decide_image_plan</dd><dt>版本号</dt><dd>v2.3.1</dd><dt>节点名</dt><dd>decide_image_plan</dd><dt>开始时间</dt><dd>2025-05-15 14:22:31</dd><dt>耗时</dt><dd>18.42s</dd></dl><div><button class="page-button primary">${icon('play')}打开预览</button><button class="page-button">${icon('copy')}复制路径</button></div></div></article></div></section></div>
  </section>`
}

export const pageTemplates = {
  flows: () => flowsPage(false),
  'flows-empty': () => flowsPage(true),
  diagnostics: diagnosticsPage,
  resources: resourcesPage,
  release: releasePage,
  settings: settingsPage,
}
