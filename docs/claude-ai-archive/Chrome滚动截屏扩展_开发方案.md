# Chrome 滚动截屏扩展 — 开发方案

## 1. 项目概述

基于 Chrome MV3 的全页滚动截屏扩展，支持区域选择、多格式导出（PNG/JPEG/WebP/PDF）和批量 URL 截图。架构优先可扩展性，核心截图逻辑与 UI/导出解耦。

---

## 2. 目录结构

```
scroll-capture/
├── manifest.json              # MV3 配置
├── background/
│   └── service-worker.ts      # 核心调度：截图流程控制、批量任务队列
├── content/
│   ├── scroller.ts            # 滚动控制 + captureVisibleTab 协调
│   ├── region-selector.ts     # overlay 框选区域 (P1)
│   └── dom-cleaner.ts         # 隐藏 fixed/sticky 元素 (P3)
├── offscreen/
│   ├── offscreen.html         # OffscreenDocument 载体
│   └── offscreen.ts           # Canvas 拼接 + 格式转换
├── lib/
│   ├── stitcher.ts            # 分段截图 → Canvas 拼接
│   ├── exporter.ts            # 输出 PNG/JPEG/WebP/PDF
│   └── types.ts               # 共享类型定义
├── popup/
│   ├── popup.html
│   └── popup.ts               # 主界面：模式选择、参数配置
└── options/
    ├── options.html
    └── options.ts              # 批量 URL 管理、默认参数 (P2)
```

---

## 3. 核心截图流程

```
用户点击 popup 按钮
  → popup 发送消息到 service-worker
  → service-worker 注入 content script (scroller.ts)
  → scroller 计算 document.scrollHeight / window.innerHeight → 得到总帧数
  → 循环:
      1. window.scrollTo(0, offset)
      2. 等待渲染稳定 (requestAnimationFrame + 延迟)
      3. 通知 service-worker 调用 chrome.tabs.captureVisibleTab()
      4. 返回 base64 数据
  → service-worker 收集所有分段数据
  → 创建 OffscreenDocument → 传入分段数据
  → offscreen.ts 用 Canvas 拼接 → 调用 exporter 转目标格式
  → chrome.downloads.download() 保存文件
```

---

## 4. 关键技术决策

### 4.1 为什么用 OffscreenDocument

MV3 的 service-worker 无法访问 DOM/Canvas。`chrome.offscreen.createDocument()` 提供了一个隐藏的 DOM 环境，用于 Canvas 拼接和图片格式转换。

### 4.2 分段截图的滚动策略

```typescript
// scroller.ts 核心逻辑
interface ScrollPlan {
  totalHeight: number;       // document.scrollHeight
  viewportHeight: number;    // window.innerHeight
  frameCount: number;        // Math.ceil(totalHeight / viewportHeight)
  lastFrameOverlap: number;  // 最后一帧与倒数第二帧的重叠像素
}
```

- 每帧滚动一个 `viewportHeight`
- 最后一帧滚动到底部 (`scrollHeight - viewportHeight`)，拼接时裁剪重叠区域
- 首帧保留 fixed/sticky 元素，后续帧通过 `dom-cleaner` 临时隐藏（P3）

### 4.3 区域截图实现 (P1)

1. content script 注入全屏半透明 overlay
2. 鼠标拖拽绘制选区矩形，记录 `{ x, y, width, height }` 相对于页面的绝对坐标
3. 仍执行全页滚动截图流程
4. 拼接完成后，在 Canvas 上按坐标 `drawImage()` 裁剪目标区域

### 4.4 批量 URL 截图 (P2)

```
options 页面输入 URL 列表
  → service-worker 维护串行任务队列
  → 逐个: chrome.tabs.create({ url, active: false })
  → 监听 tabs.onUpdated (status === 'complete')
  → 执行截图流程
  → chrome.tabs.remove()
  → 下一个 URL
```

并发控制：默认串行，预留 `concurrency` 参数。

### 4.5 PDF 导出

使用 jsPDF（~80KB gzipped），将拼接后的长图按 A4 尺寸分页：

```typescript
// exporter.ts
function toPDF(imageData: Blob, filename: string): void {
  const pdf = new jsPDF('p', 'mm', 'a4');
  const pageHeight = 297; // A4 高度 mm
  const pageWidth = 210;
  // 按宽度缩放图片，计算需要多少页
  // 逐页 addImage() + addPage()
}
```

---

## 5. 消息协议设计

service-worker 与 content script / offscreen / popup 之间统一使用 `chrome.runtime.sendMessage`，消息格式：

```typescript
interface Message {
  type: 
    | 'START_CAPTURE'       // popup → sw: 开始截图
    | 'SCROLL_NEXT'         // sw → content: 滚动到下一帧
    | 'FRAME_READY'         // content → sw: 当前帧已就绪
    | 'STITCH_FRAMES'       // sw → offscreen: 拼接所有帧
    | 'STITCH_COMPLETE'     // offscreen → sw: 拼接完成
    | 'SELECT_REGION'       // popup → content: 进入区域选择模式
    | 'REGION_SELECTED'     // content → sw: 区域坐标确定
    | 'BATCH_START'         // options → sw: 开始批量截图
    | 'BATCH_PROGRESS';     // sw → options: 进度更新
  payload: Record<string, unknown>;
}
```

---

## 6. manifest.json 关键权限

```json
{
  "manifest_version": 3,
  "permissions": [
    "activeTab",        // captureVisibleTab
    "offscreen",        // OffscreenDocument
    "downloads",        // 保存文件
    "tabs",             // 批量截图 tab 管理
    "scripting"         // 动态注入 content script
  ],
  "host_permissions": ["<all_urls>"]
}
```

---

## 7. 开发阶段与优先级

| 阶段 | 模块 | 交付物 | 风险点 |
|------|------|--------|--------|
| **P0** | 基础全页截图 + PNG 导出 | manifest + service-worker + scroller + offscreen(stitcher) + popup | `captureVisibleTab` 与滚动时序竞争 |
| **P1** | 多格式导出 | exporter (JPEG/WebP/PDF) | jsPDF 打包体积；WebP 兼容性 |
| **P1** | 区域选择截图 | region-selector + popup UI 更新 | overlay 与页面交互事件冲突 |
| **P2** | 批量 URL 截图 | options 页 + 任务队列 | tab 生命周期管理；内存占用 |
| **P3** | fixed 元素自动隐藏 | dom-cleaner | 误隐藏关键 UI；恢复时序 |

---

## 8. 已知风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 截图与滚动不同步导致撕裂 | 拼接后出现白条或重复内容 | `requestAnimationFrame` + 可配置延迟 (默认 300ms) |
| 页面有懒加载内容 | 截图时部分区域空白 | 滚动后等待 `MutationObserver` 或固定等待时间 |
| 超长页面内存溢出 | Canvas 超过浏览器限制 (通常 ~16384px) | 检测高度，超限时分段输出多张图或直接走 PDF |
| `chrome.offscreen` 仅允许一个实例 | 并发截图冲突 | 任务队列串行化，复用单个 OffscreenDocument |

---

## 9. 技术栈与依赖

| 依赖 | 用途 | 版本 |
|------|------|------|
| TypeScript | 全项目语言 | ^5.5 |
| Vite + CRXJS | 扩展打包 (HMR 开发体验) | vite ^5.x, @crxjs/vite-plugin ^2.x |
| jsPDF | PDF 导出 | ^2.5 |

无其他运行时依赖。构建产物为纯 Chrome 扩展，不依赖外部服务。

---

## 10. 后续扩展方向（不在当前范围）

- **标注功能**：截图后在 Canvas 上画框、加文字
- **对比截图**：同一 URL 不同时间截图 diff
- **云端存储**：上传到 S3/R2，生成分享链接
- **Playwright 联动**：CLI 脚本处理无登录态的批量任务，扩展处理登录态页面
