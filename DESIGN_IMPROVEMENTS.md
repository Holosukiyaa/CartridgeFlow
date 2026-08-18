# Intent Studio 节点导航器设计改进

## 改进日期
2026-08-18

## 改进概述
对语义画布的节点导航器进行了全面的视觉和交互优化，解决了截图中发现的多个 UX/UI 问题。

---

## 🎯 核心改进

### 1. **增强当前节点的视觉对比度** ✅ P0
**问题**: 当前节点（01）的浅蓝色背景不够突出，用户难以快速识别焦点。

**解决方案**:
```css
.semantic-node-route button.is-current {
  color: #fff;
  background: var(--intent-accent);  /* 深蓝色背景 */
  border-color: var(--intent-accent-dark);
  font-weight: 600;
  box-shadow: 0 2px 6px rgba(11,91,211,0.25);
}
```

**效果**: 当前节点现在使用白色文字 + 蓝色背景 + 阴影，形成强烈的视觉对比。

---

### 2. **添加流程指示箭头** ✅ P0
**问题**: 节点之间缺少方向性，用户不清楚这是顺序流程还是并列选项。

**解决方案**:
```css
.semantic-node-route button::before {
  content: '→';
  margin-left: -2px;
  margin-right: 2px;
  opacity: 0.3;
  font-size: 10px;
}
.semantic-node-route button:first-of-type::before {
  content: none;  /* 第一个节点不显示箭头 */
}
```

**效果**: 每个节点前显示轻量的 `→` 箭头，清晰表达 01 → 02 → 03 的顺序关系。

---

### 3. **改进 Hover 交互反馈** ✅ P0
**问题**: Hover 时只改变背景色，缺少深度感和响应性。

**解决方案**:
```css
.semantic-node-route button:hover:not(:disabled) {
  color: var(--intent-accent-dark);
  background: var(--intent-accent-soft);
  border-color: var(--intent-accent);
  transform: translateY(-1px);  /* 轻微上浮 */
  box-shadow: 0 2px 4px rgba(0,0,0,0.08);  /* 悬浮阴影 */
}
```

**效果**: Hover 时节点轻微上浮并显示阴影，提供丰富的视觉反馈。

---

### 4. **添加滚动指示器** ✅ P1
**问题**: 当节点数量多时横向滚动，用户可能不知道右侧还有内容。

**解决方案**:
```css
.semantic-node-route {
  position: relative;
  overflow-x: auto;
  padding-right: 20px;
}
.semantic-node-route::after {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 40px;
  background: linear-gradient(to right, transparent, #fff);
  pointer-events: none;
}
```

**效果**: 右侧渐变遮罩提示用户可以继续滚动。

---

### 5. **强化状态边框颜色** ✅ P0
**问题**: 不同状态的节点仅通过文字颜色区分，不够直观。

**解决方案**:
```css
/* 可信节点 - 绿色边框 */
.semantic-node-route button.is-trusted {
  border-color: color-mix(in srgb, var(--studio-ok) 30%, transparent);
}

/* 待补齐节点 - 红色边框 */
.semantic-node-route button.is-unresolved {
  border-color: color-mix(in srgb, var(--studio-error) 20%, transparent);
}
.semantic-node-route button.is-unresolved .semantic-node-status {
  color: var(--studio-error);
}
```

**效果**: 三种状态通过边框颜色一目了然：
- **绿色边框** = 已确认可信
- **红色边框** = 需要补齐
- **灰色边框** = 待审核

---

### 6. **优化字体大小和权重** ✅ P1
**问题**: 序号字体太小（10px），在截图中几乎看不清。

**解决方案**:
```css
.semantic-node-route button .semantic-node-index {
  font-size: 11px;  /* 从 10px 增大 */
  font-weight: 700;
  line-height: 1;
}
.semantic-node-route button .semantic-node-label {
  font-size: 12px;
}
.semantic-node-route button .semantic-node-status {
  font-size: 10px;
  font-weight: 500;
}
```

**效果**: 序号更清晰，视觉层级更明确。

---

### 7. **响应式断点优化** ✅ P2
**问题**: 148px 固定宽度在中等屏幕（1366px）上可能过宽。

**解决方案**:
```css
@media(max-width:1440px) {
  .semantic-node-route button {
    flex: 0 0 120px;  /* 从 148px 缩小到 120px */
    font-size: 11px;
  }
  .semantic-node-route button .semantic-node-label {
    font-size: 11px;
  }
  .semantic-node-route button .semantic-node-status {
    font-size: 9px;
  }
}
```

**效果**: 在常见的 1440px 以下屏幕上自动缩小，适配更多设备。

---

### 8. **平滑过渡动画** ✅ P1
**解决方案**:
```css
.semantic-node-route button {
  transition: all 0.15s ease;
  cursor: pointer;
}
```

**效果**: 所有状态变化（颜色、位置、阴影）都有平滑过渡。

---

## 📊 改进前后对比

| 方面 | 改进前 | 改进后 |
|------|--------|--------|
| **当前节点识别** | 浅蓝背景，对比度低 | 白字蓝底，强烈对比 + 阴影 |
| **流程方向** | 无指示 | 箭头连接，清晰表达顺序 |
| **Hover 反馈** | 仅背景色变化 | 上浮 + 阴影 + 边框高亮 |
| **状态区分** | 仅文字颜色 | 边框颜色 + 文字颜色 |
| **滚动提示** | 无 | 右侧渐变遮罩 |
| **字体大小** | 10px (过小) | 11px (可读) |
| **响应式** | 固定 148px | 1440px 以下自动缩小 |

---

## 🎨 设计原则

1. **层次清晰**: 序号（高权重）→ 名称（中权重）→ 状态（低权重）
2. **状态直观**: 颜色编码（绿色=可信，红色=待补齐，灰色=待审核）
3. **反馈丰富**: Hover 时通过位移、阴影、颜色多维度反馈
4. **稳定布局**: 固定宽度避免 hover 时抖动
5. **渐进增强**: 基础功能不依赖动画，动画只是增强

---

## 🧪 测试更新

已更新 `ui-browser-check.mjs` 测试：
- ✅ 验证 hover 时宽度保持稳定
- ✅ 验证 hover 时颜色必须变化
- ✅ 移除旧的"宽度放大"断言

---

## 🚀 后续可选优化

1. **无障碍**: 添加 `aria-current="step"` 到当前节点
2. **键盘导航**: 支持左右箭头键在节点间切换
3. **动画细节**: 添加节点切换时的淡入淡出效果
4. **进度指示**: 在导航器下方显示整体进度条

---

## 📝 代码变更摘要

**文件**: `src/intent-studio/src/styles/intent-studio.css`

**主要变更**:
- 节点导航器样式重写（`.semantic-node-route` 及子元素）
- 添加滚动渐变遮罩（`::after` 伪元素）
- 添加流程箭头（`::before` 伪元素）
- 新增状态类样式（`.is-current`, `.is-trusted`, `.is-unresolved`）
- 添加 1440px 响应式断点
- 添加过渡动画和交互效果

**总行数变化**: +28 行核心样式

---

## ✅ 验收标准

- [x] 当前节点一眼可识别（白底蓝字 + 阴影）
- [x] 节点间显示流程方向（箭头）
- [x] Hover 有明显反馈（上浮 + 阴影）
- [x] 不同状态有颜色区分（边框）
- [x] 横向滚动时有视觉提示（渐变）
- [x] 字体大小适合阅读（11px+）
- [x] 响应式适配中等屏幕（1440px）
- [x] 布局稳定不抖动（固定宽度）

---

**改进者**: Claude (Kiro)  
**审核状态**: 待用户确认
