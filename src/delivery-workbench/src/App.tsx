import {
  ArrowLeft,
  ArrowRight,
  Bell,
  Boxes,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  CircleHelp,
  Clock3,
  Database,
  Eye,
  FileCheck2,
  FileInput,
  FileOutput,
  FolderKanban,
  History,
  Layers3,
  Link2,
  MoreHorizontal,
  PackageCheck,
  Play,
  Plus,
  Rocket,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  TerminalSquare,
  UserRound,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import {
  ActionIcon,
  AppShell,
  Badge,
  Button,
  Divider,
  Group,
  Menu,
  Modal,
  Paper,
  Progress,
  ScrollArea,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  ThemeIcon,
  Tooltip,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMemo, useState } from 'react';

type Page = 'projects' | 'capabilities' | 'releases' | 'runs' | 'settings';
type StageKey = 'define' | 'design' | 'assemble' | 'verify' | 'release';
type ChecklistState = 'done' | 'blocked' | 'idle';

type Project = {
  id: string;
  name: string;
  customer: string;
  summary: string;
  status: string;
  statusColor: string;
  version: string;
  updated: string;
  stage: StageKey;
  nextAction: string;
  risk: string;
};

type ChecklistItem = {
  id: string;
  title: string;
  state: ChecklistState;
  cause: string;
  impact: string;
  requirement: string;
};

type FlowNode = {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  tone: 'blue' | 'green' | 'orange' | 'gray';
};

type StageBlueprint = {
  checklistTitle: string;
  checklist: ChecklistItem[];
  workspaceTitle: string;
  workspaceDescription: string;
  nodes: FlowNode[];
  inspectorTitle: string;
  gateLabel: string;
  gateValue: string;
  gateProgress: number;
};

const projectsSeed: Project[] = [
  {
    id: 'proj-01',
    name: '客户资料审核助手',
    customer: '远航供应链',
    summary: '将上传资料整理为可审核的风险摘要和交付清单。',
    status: '验证中',
    statusColor: 'blue',
    version: '0.8.0-rc.2',
    updated: '今天 10:24',
    stage: 'verify',
    nextAction: '关联组件证据',
    risk: '1 个阻塞项',
  },
  {
    id: 'proj-02',
    name: '行业简报交付',
    customer: '华星咨询',
    summary: '采集指定来源，生成经过人工审核的周度行业简报。',
    status: '已发布',
    statusColor: 'green',
    version: '1.2.0',
    updated: '昨天 16:40',
    stage: 'release',
    nextAction: '查看运行记录',
    risk: '无阻塞',
  },
  {
    id: 'proj-03',
    name: '售后质检报告',
    customer: '安平设备',
    summary: '从服务记录提取问题、归因并输出管理层报告。',
    status: '设计中',
    statusColor: 'cyan',
    version: '草稿',
    updated: '8 月 16 日',
    stage: 'design',
    nextAction: '确认输出合同',
    risk: '2 项待确认',
  },
];

const stages: { key: StageKey; number: string; label: string }[] = [
  { key: 'define', number: '01', label: '定义' },
  { key: 'design', number: '02', label: '设计' },
  { key: 'assemble', number: '03', label: '组装' },
  { key: 'verify', number: '04', label: '验证' },
  { key: 'release', number: '05', label: '发布' },
];

const doneItem = (id: string, title: string): ChecklistItem => ({
  id,
  title,
  state: 'done',
  cause: `${title}已经完成配置并通过当前阶段检查。`,
  impact: '该项不会阻塞后续阶段。',
  requirement: '如业务范围发生变化，需要重新确认并运行检查。',
});

const stageBlueprints: Record<StageKey, StageBlueprint> = {
  define: {
    checklistTitle: '定义清单',
    checklist: [
      doneItem('business-outcome', '交付目标'),
      doneItem('customer-owner', '客户与负责人'),
      { id: 'input-contract', title: '输入合同', state: 'blocked', cause: '输入资料的必填范围尚未获得客户确认。', impact: '无法稳定判断一次运行是否具备开始条件。', requirement: '确认文件、图片和项目编号三个公开输入及其约束。' },
      { id: 'output-contract', title: '输出合同', state: 'idle', cause: '输出合同等待输入范围确认。', impact: '报告交付格式暂时不能锁定。', requirement: '明确审核摘要、风险清单及 PDF / JSON 交付格式。' },
    ],
    workspaceTitle: '交付合同',
    workspaceDescription: '先定义客户提供什么、系统交付什么，再进入方案设计。',
    nodes: [
      { title: '客户资料', subtitle: '文件 · 图片 · 项目编号', icon: FileInput, tone: 'blue' },
      { title: '审核结果', subtitle: '摘要 · 风险 · 引用', icon: FileOutput, tone: 'orange' },
    ],
    inspectorTitle: '合同检查器',
    gateLabel: '定义门禁',
    gateValue: '2/4 通过',
    gateProgress: 50,
  },
  design: {
    checklistTitle: '设计清单',
    checklist: [
      doneItem('design-input', '输入合同'),
      doneItem('design-output', '输出合同'),
      { id: 'solution-path', title: '方案路径', state: 'blocked', cause: '“结构化分析”节点的失败处理尚未定义。', impact: '异常资料可能直接进入人工审核，增加交付风险。', requirement: '补充失败分支和人工接管条件。' },
      { id: 'human-point', title: '人工确认点', state: 'idle', cause: '确认点等待方案路径完成。', impact: '业务人员的最终责任边界尚未锁定。', requirement: '明确确认人、超时行为和驳回后的返回节点。' },
      { id: 'delivery-view', title: '交付呈现', state: 'idle', cause: '呈现方式尚未选择。', impact: '最终结果还不能在 Runtime 中预览。', requirement: '从能力库选择经过验证的报告组件。' },
    ],
    workspaceTitle: '方案结构',
    workspaceDescription: '将交付合同转换为业务可审核的处理路径。',
    nodes: [
      { title: '收集资料', subtitle: '3 个公开输入', icon: FileInput, tone: 'green' },
      { title: '结构化分析', subtitle: '待补充失败处理', icon: Database, tone: 'orange' },
      { title: '人工确认', subtitle: '业务责任节点', icon: UserRound, tone: 'gray' },
      { title: '生成交付', subtitle: '2 个公开输出', icon: FileOutput, tone: 'gray' },
    ],
    inspectorTitle: '设计检查器',
    gateLabel: '设计门禁',
    gateValue: '2/5 通过',
    gateProgress: 40,
  },
  assemble: {
    checklistTitle: '组装清单',
    checklist: [
      doneItem('node-types', '节点类型'),
      doneItem('capability-source', '能力来源'),
      doneItem('model-binding', '模型绑定'),
      { id: 'runtime-binding', title: '运行时绑定', state: 'blocked', cause: '报告输出节点尚未绑定 Runtime 可用组件。', impact: '流程可以编译，但最终结果无法在运行端呈现。', requirement: '选择受信报告组件并完成业务字段映射。' },
      { id: 'permission-scope', title: '权限范围', state: 'idle', cause: '等待运行时绑定完成。', impact: '工具和模型权限还不能形成最终清单。', requirement: '确认每个节点的最小权限范围。' },
    ],
    workspaceTitle: '执行结构',
    workspaceDescription: '装配经过验证的能力、模型和 Runtime 交互组件。',
    nodes: [
      { title: '输入资料', subtitle: 'collect_inputs', icon: FileInput, tone: 'green' },
      { title: '文档结构化分析', subtitle: 'llm_prompt', icon: Database, tone: 'green' },
      { title: '人工审核确认', subtitle: 'confirm_checkpoint', icon: UserRound, tone: 'green' },
      { title: '输出审核报告', subtitle: 'render_interaction', icon: FileOutput, tone: 'orange' },
    ],
    inspectorTitle: '组装检查器',
    gateLabel: '组装门禁',
    gateValue: '3/5 通过',
    gateProgress: 60,
  },
  verify: {
    checklistTitle: '当前交付清单',
    checklist: [
      doneItem('input-contract', '输入合同'),
      doneItem('output-contract', '输出合同'),
      doneItem('human-checkpoint', '人工确认点'),
      doneItem('runtime-binding', '运行时绑定'),
      doneItem('publisher-identity', '发布身份'),
      { id: 'interaction-evidence', title: '交互组件证据', state: 'blocked', cause: '交互组件选择未关联目标运行环境中的受信行为与预期一致性。', impact: '输出审核报告的交互组件无法完成验证，导致发布门禁未通过。', requirement: '提供交互组件在目标运行环境中的执行记录、请求响应样例或回放证据。' },
    ],
    workspaceTitle: '执行结构',
    workspaceDescription: '检查完整执行路径及每个交付节点的证据。',
    nodes: [
      { title: '输入资料', subtitle: '输入合同已验证', icon: FileInput, tone: 'blue' },
      { title: '文档结构化分析', subtitle: '模型绑定已验证', icon: Database, tone: 'blue' },
      { title: '人工审核确认', subtitle: '确认点已验证', icon: UserRound, tone: 'blue' },
      { title: '输出审核报告', subtitle: '缺少组件证据', icon: FileOutput, tone: 'orange' },
    ],
    inspectorTitle: '验证检查器',
    gateLabel: '发布门禁',
    gateValue: '3/4 通过',
    gateProgress: 75,
  },
  release: {
    checklistTitle: '发布清单',
    checklist: [
      doneItem('release-checks', '发布前检查'),
      doneItem('manifest', '内容清单'),
      doneItem('digest', '内容摘要'),
      { id: 'signature', title: '发布签名', state: 'blocked', cause: '当前候选版本尚未完成发布者签名。', impact: '安装端无法建立发布者身份和内容完整性信任。', requirement: '使用已配置的发布身份签署候选包。' },
      { id: 'runtime-profile', title: '运行端兼容性', state: 'idle', cause: '等待签名完成后执行最终兼容检查。', impact: '暂时不能向目标 Runtime Shell 交付。', requirement: '验证目标 Profile、协议版本和组件注册表。' },
    ],
    workspaceTitle: '候选版本',
    workspaceDescription: '冻结内容、建立信任并生成可移动的 CF-CRE 包。',
    nodes: [
      { title: '验证结果', subtitle: '3/4 通过', icon: FileCheck2, tone: 'green' },
      { title: '内容清单', subtitle: 'sha256 已生成', icon: PackageCheck, tone: 'green' },
      { title: '发布签名', subtitle: '等待签名', icon: ShieldCheck, tone: 'orange' },
      { title: '交付包', subtitle: '尚未生成', icon: Rocket, tone: 'gray' },
    ],
    inspectorTitle: '发布检查器',
    gateLabel: '交付门禁',
    gateValue: '2/4 通过',
    gateProgress: 50,
  },
};

const navItems: { page: Page; label: string; icon: LucideIcon }[] = [
  { page: 'projects', label: '项目', icon: FolderKanban },
  { page: 'capabilities', label: '能力库', icon: Boxes },
  { page: 'releases', label: '发布队列', icon: Rocket },
  { page: 'runs', label: '运行记录', icon: History },
];

function showNotice(title: string, message: string, color = 'blue') {
  notifications.show({ title, message, color });
}

function StatusBadge({ color, children }: { color: string; children: React.ReactNode }) {
  return <Badge className="status-badge" color={color} variant="light" radius="sm">{children}</Badge>;
}

function Brand() {
  return (
    <div className="topbar-brand">
      <ThemeIcon size={28} radius="sm" variant="light" color="blue"><Layers3 size={18} strokeWidth={2.2} /></ThemeIcon>
      <Text className="brand-name">CartridgeFlow</Text>
      <Divider orientation="vertical" />
      <Text className="brand-product">交付工作台</Text>
    </div>
  );
}

function Topbar({ project, page, onCreate, onRun }: { project: Project | null; page: Page; onCreate: () => void; onRun: () => void }) {
  return (
    <AppShell.Header className="app-header">
      <Brand />
      <TextInput
        className="command-search"
        leftSection={<Search size={15} />}
        rightSection={<span className="keyboard-hint">Ctrl K</span>}
        placeholder="搜索项目、组件、合同或输入命令…"
        aria-label="搜索工作台"
      />
      <Group className="topbar-actions" gap={6} wrap="nowrap">
        <Text className="save-state"><span className="save-dot" />本地已保存</Text>
        <Tooltip label="通知"><ActionIcon variant="subtle" color="gray" aria-label="通知"><Bell size={18} /></ActionIcon></Tooltip>
        <Tooltip label="帮助"><ActionIcon variant="subtle" color="gray" aria-label="帮助"><CircleHelp size={18} /></ActionIcon></Tooltip>
        <Tooltip label="设置"><ActionIcon variant="subtle" color="gray" aria-label="设置"><Settings2 size={18} /></ActionIcon></Tooltip>
        {project ? (
          <Button className="global-primary" leftSection={<Play size={15} />} onClick={onRun}>运行验证</Button>
        ) : page === 'projects' ? (
          <Button className="global-primary" leftSection={<Plus size={15} />} onClick={onCreate}>新建项目</Button>
        ) : null}
      </Group>
    </AppShell.Header>
  );
}

function Sidebar({ page, projectCount, onNavigate }: { page: Page; projectCount: number; onNavigate: (page: Page) => void }) {
  return (
    <AppShell.Navbar className="app-navbar">
      <ScrollArea className="nav-scroll">
        <Stack gap={4}>
          {navItems.map(({ page: itemPage, label, icon: Icon }) => (
            <button className={`nav-item ${page === itemPage ? 'is-active' : ''}`} key={itemPage} onClick={() => onNavigate(itemPage)} type="button">
              <Icon size={17} strokeWidth={1.9} />
              <span>{label}</span>
              {itemPage === 'projects' && <span className="nav-count">{projectCount}</span>}
            </button>
          ))}
        </Stack>
      </ScrollArea>
      <div className="navbar-footer">
        <button className={`nav-item ${page === 'settings' ? 'is-active' : ''}`} onClick={() => onNavigate('settings')} type="button">
          <Settings2 size={17} /><span>工作区设置</span>
        </button>
        <div className="local-mode"><TerminalSquare size={16} /><span className="status-dot" /><Text size="xs">本地模式</Text></div>
      </div>
    </AppShell.Navbar>
  );
}

function ProjectHeader({ project, onBack }: { project: Project; onBack: () => void }) {
  return (
    <div className="project-header">
      <Button className="project-back" variant="subtle" color="gray" onClick={onBack} aria-label="返回项目列表"><ArrowLeft size={17} /></Button>
      <ThemeIcon className="project-mark" size={48} radius="sm" variant="light" color="blue"><FolderKanban size={23} /></ThemeIcon>
      <div className="project-identity">
        <Group gap="sm"><Text className="project-title">{project.name}</Text><StatusBadge color={project.statusColor}>{project.status}</StatusBadge></Group>
        <Group gap="lg"><Text size="xs" c="dimmed">客户：{project.customer}</Text><Text size="xs" c="dimmed">版本：{project.version}</Text></Group>
      </div>
      <Group className="project-actions" gap="sm">
        <Button variant="default" leftSection={<Eye size={15} />} onClick={() => showNotice('静态预览', '运行端预览将在连接 Runtime 后启用。')}>预览</Button>
        <Tooltip label="通过全部发布门禁后可创建">
          <Button variant="default" leftSection={<Plus size={15} />} disabled={project.stage === 'verify'}>创建候选版本</Button>
        </Tooltip>
        <Menu position="bottom-end" shadow="md">
          <Menu.Target><ActionIcon variant="default" color="gray" aria-label="项目更多操作"><MoreHorizontal size={18} /></ActionIcon></Menu.Target>
          <Menu.Dropdown><Menu.Item>复制项目</Menu.Item><Menu.Item>导出项目摘要</Menu.Item><Menu.Item color="red">归档项目</Menu.Item></Menu.Dropdown>
        </Menu>
      </Group>
    </div>
  );
}

function StageRail({ currentStage, viewStage, onChange }: { currentStage: StageKey; viewStage: StageKey; onChange: (stage: StageKey) => void }) {
  const activeIndex = stages.findIndex((item) => item.key === currentStage);
  return (
    <div className="stage-rail" aria-label="交付阶段">
      {stages.map((item, index) => {
        const passed = index < activeIndex;
        const active = index === activeIndex;
        const viewing = item.key === viewStage;
        return (
          <div className="stage-segment" key={item.key}>
            <button className={`stage-step ${passed ? 'is-passed' : ''} ${active ? 'is-active' : ''} ${viewing ? 'is-viewing' : ''}`} onClick={() => onChange(item.key)} type="button">
              <span className="stage-circle">{passed ? <Check size={18} /> : item.number}</span>
              <span className="stage-copy"><strong>{item.number} {item.label}</strong><small>{passed ? '已通过' : active ? '进行中' : '未开始'}</small></span>
            </button>
            {index < stages.length - 1 && <span className={`stage-connector ${passed ? 'is-passed' : ''}`} />}
          </div>
        );
      })}
    </div>
  );
}

function ChecklistIcon({ state }: { state: ChecklistState }) {
  if (state === 'done') return <CheckCircle2 size={18} />;
  if (state === 'blocked') return <CircleAlert size={18} />;
  return <Clock3 size={18} />;
}

function DeliveryChecklist({ blueprint, selectedId, onSelect }: { blueprint: StageBlueprint; selectedId: string; onSelect: (id: string) => void }) {
  return (
    <Paper className="workspace-panel checklist-panel" withBorder radius="sm">
      <div className="workspace-panel-header"><Text fw={700} size="sm">{blueprint.checklistTitle}</Text></div>
      <div className="checklist-items">
        {blueprint.checklist.map((item) => (
          <button className={`checklist-item state-${item.state} ${selectedId === item.id ? 'is-selected' : ''}`} key={item.id} onClick={() => onSelect(item.id)} type="button">
            <ChecklistIcon state={item.state} />
            <span>{item.title}</span>
            <ChevronRight size={15} />
          </button>
        ))}
      </div>
    </Paper>
  );
}

function ExecutionCanvas({ blueprint }: { blueprint: StageBlueprint }) {
  return (
    <Paper className="workspace-panel execution-panel" withBorder radius="sm">
      <div className="workspace-panel-header execution-header">
        <div><Text fw={700} size="sm">{blueprint.workspaceTitle}</Text><Text size="xs" c="dimmed">{blueprint.workspaceDescription}</Text></div>
        <Group gap={6}>
          <SegmentedControl className="canvas-mode" size="xs" value="structure" data={[{ label: '结构', value: 'structure' }, { label: '合同', value: 'contract' }, { label: '预览', value: 'preview' }]} />
          <Tooltip label="画布设置"><ActionIcon variant="subtle" color="gray" aria-label="画布设置"><SlidersHorizontal size={16} /></ActionIcon></Tooltip>
        </Group>
      </div>
      <div className="execution-canvas">
        <div className="flow-chain">
          {blueprint.nodes.map((node, index) => {
            const Icon = node.icon;
            return (
              <div className="flow-fragment" key={`${node.title}-${index}`}>
                <button className={`flow-node tone-${node.tone}`} type="button" onClick={() => showNotice(node.title, node.subtitle, node.tone === 'orange' ? 'orange' : 'blue')}>
                  <ThemeIcon size={42} radius="sm" variant="light" color={node.tone}><Icon size={21} /></ThemeIcon>
                  <Text fw={650} size="sm">{node.title}</Text>
                  <Text size="xs" c="dimmed">{node.subtitle}</Text>
                </button>
                {index < blueprint.nodes.length - 1 && <div className="flow-connector"><span /><ArrowRight size={16} /></div>}
              </div>
            );
          })}
        </div>
      </div>
      <div className="canvas-footer"><Text size="xs" c="dimmed">{blueprint.nodes.length} 个节点</Text><Text size="xs" c="dimmed">自动保存</Text></div>
    </Paper>
  );
}

function VerificationInspector({ blueprint, item }: { blueprint: StageBlueprint; item: ChecklistItem }) {
  const blocked = item.state === 'blocked';
  return (
    <Paper className="workspace-panel inspector-panel" withBorder radius="sm">
      <div className="workspace-panel-header"><Text fw={700} size="sm">{blueprint.inspectorTitle}</Text><ActionIcon variant="subtle" color="gray" aria-label="检查器更多操作"><MoreHorizontal size={17} /></ActionIcon></div>
      <ScrollArea className="inspector-scroll">
        <div className={`inspector-selection ${blocked ? 'is-blocked' : 'is-clear'}`}>
          <ChecklistIcon state={item.state} />
          <Text fw={650} size="sm">{item.title}</Text>
          <StatusBadge color={blocked ? 'orange' : item.state === 'done' ? 'green' : 'gray'}>{blocked ? '阻塞' : item.state === 'done' ? '通过' : '待处理'}</StatusBadge>
        </div>
        <div className="inspector-content">
          <section><Text fw={700} size="xs">问题原因</Text><Text size="xs" c="dimmed">{item.cause}</Text></section>
          <section><Text fw={700} size="xs">影响范围</Text><Text size="xs" c="dimmed">{item.impact}</Text></section>
          <section><Text fw={700} size="xs">所需证据</Text><Text size="xs" c="dimmed">{item.requirement}</Text></section>
          <Button fullWidth leftSection={<Link2 size={15} />} disabled={!blocked} onClick={() => showNotice('关联证据', '静态模式下不会写入真实验证记录。')}>{blocked ? '关联组件证据' : '当前项无需处理'}</Button>
        </div>
      </ScrollArea>
      <div className="gate-summary">
        <Group justify="space-between"><Text fw={700} size="xs">{blueprint.gateLabel}</Text><Text size="xs"><strong>{blueprint.gateValue.split(' ')[0]}</strong> {blueprint.gateValue.split(' ').slice(1).join(' ')}</Text></Group>
        <Progress value={blueprint.gateProgress} size={4} color={blueprint.gateProgress === 100 ? 'green' : 'orange'} mt="xs" />
      </div>
    </Paper>
  );
}

function ProjectWorkspace({ project, stage, onStageChange, onBack }: { project: Project; stage: StageKey; onStageChange: (stage: StageKey) => void; onBack: () => void }) {
  const blueprint = stageBlueprints[stage];
  const defaultItem = blueprint.checklist.find((item) => item.state === 'blocked') ?? blueprint.checklist[0];
  const [selectedChecklistId, setSelectedChecklistId] = useState(defaultItem.id);
  const selectedItem = blueprint.checklist.find((item) => item.id === selectedChecklistId) ?? defaultItem;

  const changeStage = (nextStage: StageKey) => {
    const nextBlueprint = stageBlueprints[nextStage];
    const nextDefault = nextBlueprint.checklist.find((item) => item.state === 'blocked') ?? nextBlueprint.checklist[0];
    setSelectedChecklistId(nextDefault.id);
    onStageChange(nextStage);
  };

  return (
    <div className="project-workspace">
      <ProjectHeader project={project} onBack={onBack} />
      <StageRail currentStage={project.stage} viewStage={stage} onChange={changeStage} />
      <div className="delivery-workspace">
        <DeliveryChecklist blueprint={blueprint} selectedId={selectedItem.id} onSelect={setSelectedChecklistId} />
        <ExecutionCanvas blueprint={blueprint} />
        <VerificationInspector blueprint={blueprint} item={selectedItem} />
      </div>
    </div>
  );
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="page-header"><div><Text className="eyebrow">{eyebrow}</Text><Text className="page-title">{title}</Text><Text size="sm" c="dimmed">{description}</Text></div>{action}</div>;
}

function ProjectList({ projects, onOpen }: { projects: Project[]; onOpen: (id: string) => void }) {
  return (
    <div className="page-content">
      <PageHeader eyebrow="DELIVERY PROJECTS" title="项目" description="围绕当前阶段、阻塞项和下一步管理交付。" />
      <Paper className="data-panel" withBorder radius="sm">
        <div className="filter-row"><TextInput placeholder="搜索项目或客户" leftSection={<Search size={15} />} /><Select value="all" data={[{ value: 'all', label: '全部阶段' }, { value: 'verify', label: '验证' }, { value: 'release', label: '发布' }]} w={150} readOnly /><Text size="xs" c="dimmed" ml="auto">{projects.length} 个项目</Text></div>
        <Table className="data-table" verticalSpacing="md" highlightOnHover>
          <Table.Thead><Table.Tr><Table.Th>项目</Table.Th><Table.Th>客户</Table.Th><Table.Th>当前阶段</Table.Th><Table.Th>下一步</Table.Th><Table.Th>风险</Table.Th><Table.Th>最近修改</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>{projects.map((project) => <Table.Tr className="clickable-row" key={project.id} onClick={() => onOpen(project.id)}><Table.Td><Group gap="sm" wrap="nowrap"><ThemeIcon size={34} radius="sm" variant="light" color="blue"><FolderKanban size={17} /></ThemeIcon><div><Text fw={650} size="sm">{project.name}</Text><Text size="xs" c="dimmed" lineClamp={1}>{project.summary}</Text></div></Group></Table.Td><Table.Td><Text size="sm">{project.customer}</Text></Table.Td><Table.Td><StatusBadge color={project.statusColor}>{project.status}</StatusBadge></Table.Td><Table.Td><Text size="sm">{project.nextAction}</Text></Table.Td><Table.Td><Text size="sm" c={project.risk === '无阻塞' ? 'green' : 'orange'}>{project.risk}</Text></Table.Td><Table.Td><Text size="sm" c="dimmed">{project.updated}</Text></Table.Td><Table.Td><ActionIcon variant="subtle" color="gray" aria-label={`打开${project.name}`}><ChevronRight size={17} /></ActionIcon></Table.Td></Table.Tr>)}</Table.Tbody>
        </Table>
      </Paper>
    </div>
  );
}

function CapabilitiesPage() {
  const rows = [
    ['文档结构化分析', '分析能力', '组织可信', '3 个项目', '0.4.2'],
    ['来源采集与引用', '采集能力', '工作区可信', '1 个项目', '0.3.1'],
    ['审核结果交付', '呈现组件', '组织可信', '3 个项目', '1.1.0'],
    ['客户资料清洗', '转换能力', '待验证', '未使用', '草稿'],
  ];
  return <div className="page-content"><PageHeader eyebrow="CAPABILITY LIBRARY" title="能力库" description="查找、验证并装配可复用的能力与交互组件。" action={<Button leftSection={<Plus size={15} />} onClick={() => showNotice('新建能力', '能力将在独立创作流程中建立。')}>新建能力</Button>} /><Paper className="data-panel" withBorder radius="sm"><div className="filter-row"><TextInput placeholder="搜索能力、组件或版本" leftSection={<Search size={15} />} /><Select value="all" data={[{ value: 'all', label: '全部信任范围' }]} w={170} readOnly /><Text size="xs" c="dimmed" ml="auto">12 项能力</Text></div><Table className="data-table" verticalSpacing="md" highlightOnHover><Table.Thead><Table.Tr><Table.Th>能力</Table.Th><Table.Th>类型</Table.Th><Table.Th>信任范围</Table.Th><Table.Th>使用情况</Table.Th><Table.Th>版本</Table.Th><Table.Th /></Table.Tr></Table.Thead><Table.Tbody>{rows.map(([name, type, trust, usage, version]) => <Table.Tr key={name}><Table.Td><Group gap="sm"><ThemeIcon size={32} radius="sm" variant="light" color="blue"><Boxes size={16} /></ThemeIcon><Text fw={650} size="sm">{name}</Text></Group></Table.Td><Table.Td><Text size="sm" c="dimmed">{type}</Text></Table.Td><Table.Td><StatusBadge color={trust === '待验证' ? 'orange' : trust === '组织可信' ? 'green' : 'blue'}>{trust}</StatusBadge></Table.Td><Table.Td><Text size="sm">{usage}</Text></Table.Td><Table.Td><Text size="sm" ff="monospace">{version}</Text></Table.Td><Table.Td><ActionIcon variant="subtle" color="gray" aria-label={`${name}更多操作`}><MoreHorizontal size={17} /></ActionIcon></Table.Td></Table.Tr>)}</Table.Tbody></Table></Paper></div>;
}

function ReleasesPage() {
  const rows = [
    ['0.8.0-rc.2', '客户资料审核助手', '等待门禁', '交互组件证据', '今天 10:24', 'orange'],
    ['1.2.0', '行业简报交付', '已发布', '无', '昨天 16:40', 'green'],
    ['0.6.2', '售后质检报告', '已回滚', '运行异常', '7 月 28 日', 'gray'],
  ];
  return <div className="page-content"><PageHeader eyebrow="RELEASE QUEUE" title="发布队列" description="只处理已经进入候选状态的版本和发布门禁。" action={<Button variant="default" leftSection={<FileCheck2 size={15} />} onClick={() => showNotice('队列检查', '静态发布队列没有新的状态变化。')}>检查队列</Button>} /><Paper className="data-panel" withBorder radius="sm"><Table className="data-table" verticalSpacing="md" highlightOnHover><Table.Thead><Table.Tr><Table.Th>版本</Table.Th><Table.Th>项目</Table.Th><Table.Th>状态</Table.Th><Table.Th>阻塞原因</Table.Th><Table.Th>更新时间</Table.Th><Table.Th /></Table.Tr></Table.Thead><Table.Tbody>{rows.map(([version, project, status, reason, updated, color]) => <Table.Tr key={`${project}-${version}`}><Table.Td><Text fw={650} size="sm" ff="monospace">{version}</Text></Table.Td><Table.Td><Text size="sm">{project}</Text></Table.Td><Table.Td><StatusBadge color={color}>{status}</StatusBadge></Table.Td><Table.Td><Text size="sm" c={reason === '无' ? 'dimmed' : 'orange'}>{reason}</Text></Table.Td><Table.Td><Text size="sm" c="dimmed">{updated}</Text></Table.Td><Table.Td><ActionIcon variant="subtle" color="gray" aria-label={`${version}更多操作`}><MoreHorizontal size={17} /></ActionIcon></Table.Td></Table.Tr>)}</Table.Tbody></Table></Paper></div>;
}

function RunsPage() {
  const rows = [
    ['run-1842', '行业简报交付', '1.2.0', '完成', '2 分 18 秒', '今天 09:32', 'green'],
    ['run-1841', '客户资料审核助手', '0.8.0-rc.2', '需要处理', '48 秒', '昨天 17:08', 'orange'],
    ['run-1840', '行业简报交付', '1.2.0', '完成', '2 分 04 秒', '昨天 16:42', 'green'],
  ];
  return <div className="page-content"><PageHeader eyebrow="RUN HISTORY" title="运行记录" description="查看本地验证运行、失败原因和可恢复状态。" /><Paper className="data-panel" withBorder radius="sm"><div className="filter-row"><TextInput placeholder="搜索运行 ID 或项目" leftSection={<Search size={15} />} /><Text size="xs" c="dimmed" ml="auto">最近 30 天</Text></div><Table className="data-table" verticalSpacing="md" highlightOnHover><Table.Thead><Table.Tr><Table.Th>运行</Table.Th><Table.Th>项目</Table.Th><Table.Th>版本</Table.Th><Table.Th>状态</Table.Th><Table.Th>耗时</Table.Th><Table.Th>开始时间</Table.Th><Table.Th /></Table.Tr></Table.Thead><Table.Tbody>{rows.map(([id, project, version, status, duration, started, color]) => <Table.Tr key={id}><Table.Td><Text size="sm" ff="monospace">{id}</Text></Table.Td><Table.Td><Text size="sm" fw={600}>{project}</Text></Table.Td><Table.Td><Text size="sm" ff="monospace">{version}</Text></Table.Td><Table.Td><StatusBadge color={color}>{status}</StatusBadge></Table.Td><Table.Td><Text size="sm">{duration}</Text></Table.Td><Table.Td><Text size="sm" c="dimmed">{started}</Text></Table.Td><Table.Td><ActionIcon variant="subtle" color="gray" aria-label={`查看${id}`}><ChevronRight size={17} /></ActionIcon></Table.Td></Table.Tr>)}</Table.Tbody></Table></Paper></div>;
}

function SettingsPage() {
  return <div className="page-content"><PageHeader eyebrow="WORKSPACE SETTINGS" title="工作区设置" description="配置本地工作区、发布身份和默认运行目标。" /><div className="settings-layout"><section className="settings-section"><div><Text fw={700}>基本信息</Text><Text size="xs" c="dimmed">本地开发与交付环境</Text></div><Stack gap="md"><TextInput label="工作区名称" value="华东交付工作区" readOnly /><TextInput label="发布者标识" value="workspace.publisher" readOnly /><Select label="默认运行协议" value="CF-FARP@1.1" data={['CF-FARP@1.1']} readOnly /></Stack></section><section className="settings-section"><div><Text fw={700}>连接与信任</Text><Text size="xs" c="dimmed">当前只展示静态状态</Text></div><Stack gap="md"><Group justify="space-between"><Text size="sm">发布身份</Text><StatusBadge color="green">已配置</StatusBadge></Group><Group justify="space-between"><Text size="sm">本地签名密钥</Text><StatusBadge color="green">可用</StatusBadge></Group><Group justify="space-between"><Text size="sm">Runtime Shell</Text><StatusBadge color="gray">未连接</StatusBadge></Group><Button variant="default" leftSection={<ShieldCheck size={15} />} onClick={() => showNotice('发布身份', '静态模式不修改本地密钥。')}>管理发布身份</Button></Stack></section></div></div>;
}

function RuntimeStatusBar({ project }: { project: Project | null }) {
  return <div className="runtime-status"><div><Layers3 size={14} /><span>CF-CRE@2</span></div><Divider orientation="vertical" /><div><Boxes size={14} /><span>CF-FARP@1.1</span></div><Divider orientation="vertical" /><div><TerminalSquare size={14} /><span>Runtime Shell 0.6.0-SP</span></div><div className="runtime-connection"><span className="connection-dot" /><span>{project ? project.version : '工作区'} · 未连接后端</span></div></div>;
}

function NewProjectModal({ opened, onClose, onCreate }: { opened: boolean; onClose: () => void; onCreate: (project: Project) => void }) {
  const [name, setName] = useState('');
  const [customer, setCustomer] = useState('');
  const [summary, setSummary] = useState('');
  const [startingPoint, setStartingPoint] = useState<string | null>('空白项目');

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const id = `proj-${Date.now()}`;
    onCreate({ id, name: name.trim(), customer: customer.trim(), summary: summary.trim() || '尚未填写交付目标。', status: '定义中', statusColor: 'blue', version: '草稿', updated: '刚刚', stage: 'define', nextAction: '确认输入合同', risk: '2 项待确认' });
    setName(''); setCustomer(''); setSummary(''); setStartingPoint('空白项目');
  };

  return <Modal opened={opened} onClose={onClose} title="新建交付项目" centered size="lg" radius="sm"><form className="create-project-form" onSubmit={submit}><Text size="sm" c="dimmed">先定义客户和交付结果，技术实现可以在项目创建后继续补充。</Text><TextInput label="项目名称" placeholder="例如：供应商准入审核" value={name} onChange={(event) => setName(event.currentTarget.value)} required autoFocus /><TextInput label="客户或业务方" placeholder="例如：华东采购中心" value={customer} onChange={(event) => setCustomer(event.currentTarget.value)} required /><Textarea label="交付目标" placeholder="描述客户最终要拿到的结果" value={summary} onChange={(event) => setSummary(event.currentTarget.value)} minRows={3} autosize /><Select label="起步方式" description="当前仅建立静态项目结构" value={startingPoint} onChange={setStartingPoint} data={['空白项目', '资料审核模板', '周期简报模板']} allowDeselect={false} /><Group justify="flex-end" mt="xs"><Button variant="default" onClick={onClose}>取消</Button><Button type="submit" disabled={!name.trim() || !customer.trim()} leftSection={<Plus size={15} />}>创建项目</Button></Group></form></Modal>;
}

export default function App() {
  const [page, setPage] = useState<Page>('projects');
  const [projects, setProjects] = useState<Project[]>(projectsSeed);
  const [selectedId, setSelectedId] = useState<string | null>('proj-01');
  const [stage, setStage] = useState<StageKey>('verify');
  const [createOpened, setCreateOpened] = useState(false);
  const selectedProject = useMemo(() => projects.find((project) => project.id === selectedId) ?? null, [projects, selectedId]);

  const openProject = (id: string) => {
    const project = projects.find((item) => item.id === id);
    setSelectedId(id);
    setStage(project?.stage ?? 'define');
    setPage('projects');
  };
  const navigate = (nextPage: Page) => { setSelectedId(null); setPage(nextPage); };
  const createProject = (project: Project) => { setProjects((current) => [project, ...current]); setCreateOpened(false); openProject(project.id); showNotice('项目已创建', '已进入定义阶段。', 'green'); };

  return (
    <>
      <AppShell header={{ height: 56 }} navbar={{ width: 184, breakpoint: 'sm' }} padding={0}>
        <Topbar project={selectedProject} page={page} onCreate={() => setCreateOpened(true)} onRun={() => showNotice('验证已开始', '静态模式不会产生真实运行记录。', 'blue')} />
        <Sidebar page={page} projectCount={projects.length} onNavigate={navigate} />
        <AppShell.Main className="app-main">
          {selectedProject && page === 'projects' ? <ProjectWorkspace project={selectedProject} stage={stage} onStageChange={setStage} onBack={() => setSelectedId(null)} /> : page === 'projects' ? <ProjectList projects={projects} onOpen={openProject} /> : page === 'capabilities' ? <CapabilitiesPage /> : page === 'releases' ? <ReleasesPage /> : page === 'runs' ? <RunsPage /> : <SettingsPage />}
        </AppShell.Main>
      </AppShell>
      <RuntimeStatusBar project={selectedProject} />
      <NewProjectModal opened={createOpened} onClose={() => setCreateOpened(false)} onCreate={createProject} />
    </>
  );
}
