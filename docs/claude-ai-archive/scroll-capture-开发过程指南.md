# scroll-capture 扩展开发指南

> 版本：v0.5.2 | 最后更新：2026-03 | 技术栈：Chrome MV3, Vanilla JS, OffscreenCanvas

---

## 一、项目结构

```
scroll-capture/
├── manifest.json
├── background/
│   └── service-worker.js        # 核心消息路由 + 截图逻辑
├── content/
│   ├── content-extractor.js     # 页面内容提取（注入执行）
│   └── region-selector.js       # 框选截图 UI（注入执行）
├── offscreen/
│   ├── offscreen.html
│   └── offscreen.js             # Canvas 渲染器（卡片/HTML生成）
└── popup/
    ├── popup.html
    ├── popup.js                  # coordinator：SC命名空间 + Tab切换 + 消息分发
    ├── capture.js                # 截图Tab → SC.capture
    ├── crop.js                   # 裁剪Tab → SC.crop
    ├── share.js                  # 分享Tab → SC.share
    └── lightbox.js               # 灯箱 → SC.lightbox
```

---

## 二、架构设计

### 2.1 消息流

```
popup → chrome.runtime.sendMessage
      ↓
service-worker.js（路由）
      ↓
┌─────────────────────────────────┐
│ captureFullPage / captureVisible│  → chrome.tabs.captureVisibleTab
│ startRegionSelect               │  → 注入 region-selector.js
│ extractContent                  │  → 注入 content-extractor.js
│ generateShareCards              │  → sendMessage → offscreen.js
│ generateWechatHTML              │  → sendMessage → offscreen.js
└─────────────────────────────────┘
      ↓
chrome.runtime.sendMessage({ type: "CAPTURE_STATUS" / "SHARE_STATUS" })
      ↓
popup.js 分发 → SC.capture.handleMessage / SC.share.handleMessage
```

### 2.2 popup 模块系统

popup 使用 `window.SC` 作为共享命名空间，避免 ES Module 在 MV3 popup 中的兼容问题。

**加载顺序**（popup.html 内 script 标签顺序）：
```
popup.js → capture.js → crop.js → share.js → lightbox.js
```

**共享状态**：
```javascript
window.SC = {
  generatedCards: null,     // share.js 写入，lightbox.js 读取
  lastCaptureDataUrl: null  // capture.js 写入，crop.js 读取
}
```

**模块注册约定**：每个模块在 IIFE 末尾将自身挂载到 SC：
```javascript
SC.capture = { handleMessage: function(msg) { ... } };
SC.crop    = { loadDataUrl: fn, showImportBtn: fn };
SC.share   = { handleMessage: fn, downloadAll: fn };
SC.lightbox = { open: fn };
```

### 2.3 offscreen 渲染器

- 使用 `sendMessage → sendResponse` 模式（非广播），service-worker `await` 响应
- `renderCoverCard` 为 `async`（需等待 heroImage fetch）
- `renderDetailCards` 为同步（纯 Canvas 绘制）
- service-worker 通过 `ensureOffscreen()` 管理文档生命周期，创建后 sleep 500ms 等待就绪

### 2.4 region-selector 与 ratio config 传递

service-worker 无法直接向注入脚本传参，改用 `chrome.storage.local`：
```javascript
// service-worker.js
await chrome.storage.local.set({ __sc_ratio: ratioArg });
// region-selector.js
chrome.storage.local.get("__sc_ratio", function(data) { ... });
```

---

## 三、关键实现细节

### 3.1 全页截图拼接（captureFullPage）

- 逐帧滚动 + `captureVisibleTab` 逐帧截图
- 最后一帧特殊处理 overlap（避免底部重叠）
- Canvas 最大尺寸限制 16384px，超出自动降分辨率（scaleFactor）
- DPR 通过 `bitmap.width / viewportWidth` 自动检测

### 3.2 截图完成通知（notifyDone）

```javascript
async function notifyDone(captureDataUrl) {
  var payload = { done: true };
  if (captureDataUrl) payload.captureDataUrl = captureDataUrl;
  notify(payload);
  // #12: badge
  await chrome.action.setBadgeText({ text: "✓" });
  await chrome.action.setBadgeBackgroundColor({ color: "#22c55e" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 3000);
}
```

**dataUrl 附带条件**：blob < 8MB 才传回（大图跳过，避免消息超限）。

### 3.3 内容不足时的 pseudo-sections（offscreen.js #15）

```javascript
// sections < 3 时，将 keyPoints 展开为伪 sections
if (sections.length < 3 && content.keyPoints && content.keyPoints.length > 0) {
  var pseudoSections = [];
  content.keyPoints.forEach((pt, i) => {
    pseudoSections.push({ type: "heading",   content: "要点 " + (i + 1) });
    pseudoSections.push({ type: "paragraph", content: pt });
  });
  workContent = Object.assign({}, content, {
    sections: pseudoSections.concat(sections)
  });
}
```

使用 `workContent` 副本，不修改原始 `content` 对象。

### 3.4 裁剪Tab自动导入（#14）

```
截图完成
  → service-worker notifyDone(captureDataUrl)
  → capture.js handleMessage({ done, captureDataUrl })
  → SC.lastCaptureDataUrl = dataUrl
  → SC.crop.showImportBtn(true)
  → SC.switchTab("crop")
  → SC.crop.loadDataUrl(dataUrl)
```

裁剪Tab顶部的"📸 从截图导入"按钮默认 `display:none`，仅在截图完成后显示。

---

## 四、卡片渲染规范

### 4.1 尺寸与布局

| 参数 | 值 |
|------|-----|
| 卡片尺寸 | 1080 × 1440 px（3:4） |
| 内边距 PAD | 64px |
| 最大卡片数 | 9 张（封面1 + 详情8） |

### 4.2 渲染管线

```
renderCards(content, themeName)
  ├── buildTheme(pageColors, themeName)     // minimal / tech / warm
  ├── [#15 pseudo-sections 注入]
  ├── renderCoverCard(workContent, theme)   // async
  ├── renderDetailCards(workContent, theme) // sync，sections > 2 才执行
  ├── drawFooter(ctx, content, theme, pageNum, total)  // 每张卡片
  └── convertToBlob → FileReader → dataUrl[]
```

### 4.3 section 类型

| type | 渲染方式 |
|------|---------|
| `heading` | 左侧 accent 竖条 + 粗体 36px |
| `paragraph` | 普通文本 28px，自动换行 |
| `list` | bullet 圆点 + 缩进 26px |
| `quote` | 圆角卡片背景 + 左侧 accent 条 |
| `code` | 深色背景 #1E293B，等宽字体 22px |
| `image` | 封面卡处理，详情卡跳过 |

---

## 五、开发规范

### 5.1 消息类型一览

| 方向 | type | payload |
|------|------|---------|
| popup → SW | `START_CAPTURE` | `{ scrollDelay }` |
| popup → SW | `CAPTURE_VISIBLE` | — |
| popup → SW | `START_REGION_SELECT` | `{ cropToRatio? }` |
| content → SW | `REGION_SELECTED` | region 对象 |
| popup → SW | `EXTRACT_CONTENT` | — |
| popup → SW | `GENERATE_CARDS` | `{ content, theme }` |
| popup → SW | `GENERATE_WECHAT` | `{ content, theme }` |
| popup → SW | `DOWNLOAD_CARDS` | `{ cards }` |
| popup → SW | `COPY_HTML_TO_CLIPBOARD` | `{ html }` |
| SW → popup | `CAPTURE_STATUS` | `{ status?, current?, total?, done?, error?, captureDataUrl? }` |
| SW → popup | `SHARE_STATUS` | `{ step, content?, cards?, html?, error? }` |
| SW → offscreen | `RENDER_CARDS` | `{ content, theme }` |
| SW → offscreen | `RENDER_WECHAT_HTML` | `{ content, theme }` |

### 5.2 新增功能 checklist

1. **新消息类型**：在 service-worker.js message router 末尾追加 `if (msg.type === "...")` 分支
2. **新 popup 状态**：挂载到 `window.SC`，在 popup.js 初始化
3. **新 Tab 逻辑**：新建 `xxx.js` 模块，IIFE + `SC.xxx = {}` 注册，popup.html 末尾追加 `<script>`
4. **offscreen 新渲染器**：在 offscreen.js 添加处理函数，在 `onMessage` listener 中路由

### 5.3 已知限制与坑

| 问题 | 原因 | 处理方式 |
|------|------|---------|
| offscreen sendMessage 无响应 | 文档未就绪 | `ensureOffscreen()` 后 sleep 500ms |
| Canvas 超限黑屏 | GPU 16384px 限制 | 自动 scaleFactor 缩放 |
| badge text 不支持 emoji（部分平台）| Chrome 限制 | "✓" 为 ASCII，可正常显示 |
| dataUrl 超过消息大小限制 | MV3 消息上限 ~64MB | blob > 8MB 跳过 captureDataUrl |
| content-extractor 注入幂等 | 重复注入不报错但会重复执行 | 脚本内自行检查 `window.__sc_extracted` |

---

## 六、版本历史

| 版本 | 主要变更 |
|------|---------|
| v0.5.0 | 基础架构：截图/裁剪/分享三Tab，offscreen 卡片渲染 |
| v0.5.1 | offscreen `renderCoverCard` 改 async 支持 heroImage；删除 lib/card-paginator.js 死代码 |
| v0.5.2 | #12 badge ✓；#14 裁剪Tab自动导入截图；#15 keyPoints → pseudo-sections；#16 popup.js 拆分为4模块 |

---

## 七、待办

| ID | 优先级 | 描述 |
|----|--------|------|
| #17 | P3 | content-extractor.js 提取质量优化（结构化识别改进） |
