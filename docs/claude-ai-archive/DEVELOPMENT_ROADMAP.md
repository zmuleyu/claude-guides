# Prompt Vault+ 全平台 AI 提示词 & 任务管理 Chrome 扩展

## 完整开发路线图

---

## 一、产品定位与核心理念

### 1.1 定位

Prompt Vault+ 是一款面向 AI 重度用户的 Chrome 扩展，将 **提示词管理** 和 **AI 工作流任务调度** 融合在一起。它不是通用的 To-Do 应用——每一个功能都围绕"让用户更高效地使用 AI"来设计。

### 1.2 核心使用场景

| 场景 | 示例 |
|-----|------|
| 提示词复用 | 保存一个"代码审查"提示词模板，在 ChatGPT/Claude/Gemini 上一键插入 |
| 定时 AI 任务 | 每天早上 9 点提醒"用日报生成模板在 ChatGPT 跑一次" |
| 上下文触发 | 打开 Claude 时自动提醒"继续昨天的翻译项目" |
| 工作流编排 | 先用"需求分析"模板在 ChatGPT 跑一遍，完成后自动提醒在 Claude 用"代码实现"模板跟进 |
| 使用追踪 | 统计每个提示词的使用频率，发现低效模板并优化 |

### 1.3 支持平台

- ChatGPT (chatgpt.com, chat.openai.com)
- Claude (claude.ai)
- Gemini (gemini.google.com, aistudio.google.com)
- DeepSeek (chat.deepseek.com)
- Kimi (kimi.moonshot.cn)
- Poe (poe.com)
- 任意自定义网站（通过扩展选项手动添加 URL 匹配规则）

---

## 二、系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Chrome Extension (MV3)                    │
├──────────────┬──────────────┬────────────────┬──────────────────┤
│  Background  │ Content      │  Popup /       │  Options         │
│  Service     │ Scripts      │  Side Panel    │  Page            │
│  Worker      │ (每个AI页面) │  (仪表盘)       │  (设置中心)       │
├──────────────┼──────────────┼────────────────┼──────────────────┤
│              │              │                │                  │
│ ┌──────────┐ │ ┌──────────┐ │ ┌────────────┐ │ ┌──────────────┐ │
│ │ Alarm    │ │ │ Platform │ │ │ 提示词概览  │ │ │ 平台适配管理  │ │
│ │ Scheduler│ │ │ Adapter  │ │ │            │ │ │              │ │
│ ├──────────┤ │ ├──────────┤ │ ├────────────┤ │ ├──────────────┤ │
│ │ Notifi-  │ │ │ Prompt   │ │ │ 今日任务   │ │ │ 存储策略配置  │ │
│ │ cation   │ │ │ Injector │ │ │            │ │ │              │ │
│ │ Engine   │ │ ├──────────┤ │ ├────────────┤ │ ├──────────────┤ │
│ │          │ │ │ Task     │ │ │ 使用统计   │ │ │ 数据导入导出  │ │
│ ├──────────┤ │ │ Reminder │ │ │            │ │ │              │ │
│ │ Storage  │ │ │ Bar      │ │ ├────────────┤ │ ├──────────────┤ │
│ │ Manager  │ │ ├──────────┤ │ │ 快速创建   │ │ │ 快捷键配置   │ │
│ │          │ │ │ Floating │ │ │            │ │ │              │ │
│ ├──────────┤ │ │ Panel    │ │ └────────────┘ │ └──────────────┘ │
│ │ Message  │ │ └──────────┘ │                │                  │
│ │ Router   │ │              │                │                  │
│ └──────────┘ │              │                │                  │
├──────────────┴──────────────┴────────────────┴──────────────────┤
│                     chrome.storage.local                         │
│              (prompts, tasks, settings, statistics)              │
├─────────────────────────────────────────────────────────────────┤
│                     chrome.storage.sync                          │
│              (settings, lightweight index only)                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 四个执行上下文的职责划分

**Background Service Worker** — 扩展的"大脑"
- 全局唯一，浏览器级生命周期
- 管理 `chrome.alarms` 定时任务调度
- 发送 `chrome.notifications` 系统通知
- 路由跨标签页消息（通过 `chrome.runtime.onMessage`）
- 处理通知点击事件（打开目标 AI 页面 + 传递提示词）
- 存储数据的中心化读写协调

**Content Scripts** — 每个 AI 标签页内的"代理"
- 检测当前 AI 平台，加载对应适配器
- 注入浮动面板 UI（提示词列表 + 任务提醒条）
- 执行文本插入（处理各平台不同的输入框实现）
- URL 触发检测（页面加载时查询是否有待办任务）
- 监听 DOM 变化，应对 SPA 路由切换

**Popup / Side Panel** — 用户的"控制台"
- 展示今日待办任务和即将到期的提醒
- 快速创建提示词或任务
- 使用频率统计图表
- 一键导出/导入

**Options Page** — "设置中心"
- 平台适配器管理（添加/编辑自定义网站的 CSS 选择器）
- 存储策略配置（本地 vs 云同步）
- 快捷键自定义
- 数据批量管理

### 2.3 消息通信协议

各上下文之间通过 `chrome.runtime.sendMessage` 和 `chrome.tabs.sendMessage` 通信，统一消息格式：

```typescript
interface PVMessage {
  type: string;          // 消息类型标识
  payload?: any;         // 数据负载
  source?: 'bg' | 'cs' | 'popup' | 'options';  // 来源标记
}
```

核心消息类型：

| 消息类型 | 方向 | 描述 |
|---------|------|------|
| `PROMPT_INSERT` | Background → Content | 通知某标签页插入指定提示词 |
| `TASK_REMINDER` | Background → Content | 通知页面显示任务提醒条 |
| `TASK_COMPLETE` | Content → Background | 用户在页面上标记任务完成 |
| `STORAGE_UPDATED` | Background → All | 数据变更广播 |
| `GET_CURRENT_PLATFORM` | Popup → Content | 查询当前标签页的平台信息 |
| `OPEN_AND_INSERT` | Background → (new tab) | 打开新标签页并插入提示词 |
| `ALARM_FIRED` | Internal (Background) | 定时器触发内部事件 |

---

## 三、数据模型

### 3.1 提示词 (Prompt)

```typescript
interface Prompt {
  id: string;               // 唯一标识 (nanoid 或 timestamp+random)
  title: string;            // 标题
  content: string;          // 内容（支持 {{变量名}} 模板语法）
  description?: string;     // 简短描述
  tags: string[];           // 标签
  category?: string;        // 分类文件夹路径（如 "工作/翻译"）
  
  // 使用追踪
  usageCount: number;       // 总使用次数
  lastUsedAt?: number;      // 最后使用时间戳
  usageHistory: UsageRecord[];  // 最近 100 条使用记录
  
  // 元数据
  createdAt: number;
  updatedAt: number;
  pinned: boolean;          // 是否置顶
  archived: boolean;        // 是否归档
  
  // 关联
  linkedTaskIds?: string[]; // 关联的任务 ID
}

interface UsageRecord {
  timestamp: number;
  platform: string;         // 使用时所在的 AI 平台
  variables?: Record<string, string>;  // 本次填充的变量值
}
```

### 3.2 任务 (Task)

```typescript
interface Task {
  id: string;
  title: string;
  description?: string;
  
  // 触发方式
  trigger: TaskTrigger;
  
  // 状态
  status: 'pending' | 'active' | 'done' | 'snoozed' | 'cancelled';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  
  // 时间
  dueAt?: number;           // 截止时间
  remindAt?: number;        // 提醒时间（可独立于 dueAt）
  snoozedUntil?: number;    // 暂缓到什么时候
  completedAt?: number;
  
  // 重复
  recurrence?: RecurrenceRule;
  
  // 关联
  promptId?: string;        // 关联的提示词（可选）
  targetPlatform?: string;  // 目标 AI 平台标识
  targetUrl?: string;       // 任务完成时要打开的 URL
  
  // 链式任务
  parentTaskId?: string;    // 前置任务（完成后才激活当前任务）
  childTaskIds?: string[];  // 后续任务
  
  // 元数据
  tags: string[];
  createdAt: number;
  updatedAt: number;
}

interface TaskTrigger {
  type: 'time' | 'url' | 'manual' | 'chain';
  
  // type === 'time': 到指定时间触发
  // 使用 remindAt 字段

  // type === 'url': 打开匹配的 URL 时触发
  urlPattern?: string;    // 如 "claude.ai" 或 "chatgpt.com/c/*"
  
  // type === 'chain': 前置任务完成后触发
  // 使用 parentTaskId 字段
  
  // type === 'manual': 仅手动触发
}

interface RecurrenceRule {
  frequency: 'daily' | 'weekly' | 'monthly' | 'custom';
  interval: number;         // 每隔几个周期
  daysOfWeek?: number[];    // 周几（0=日, 1=一, ..., 6=六）
  endDate?: number;         // 结束日期（可选）
  maxOccurrences?: number;  // 最大重复次数（可选）
}
```

### 3.3 设置 (Settings)

```typescript
interface Settings {
  // 通用
  theme: 'auto' | 'dark' | 'light';
  language: 'zh-CN' | 'en-US';
  
  // 快捷键
  shortcuts: {
    togglePanel: string;      // 默认 Ctrl+Shift+P
    quickAddPrompt: string;   // 默认 Ctrl+Shift+S
    quickAddTask: string;     // 默认 Ctrl+Shift+T
  };
  
  // 面板
  panel: {
    position: 'bottom-right' | 'bottom-left' | 'side-right';
    width: number;
    defaultTab: 'prompts' | 'tasks';
  };
  
  // 通知
  notifications: {
    enabled: boolean;
    sound: boolean;
    persistent: boolean;      // 通知是否持久（直到用户操作）
    reminderLeadMinutes: number;  // 提前几分钟提醒
  };
  
  // 平台适配
  platforms: PlatformConfig[];
  
  // 存储
  storage: {
    syncEnabled: boolean;
    lastSyncAt?: number;
    autoBackupEnabled: boolean;
    autoBackupIntervalDays: number;
  };
}

interface PlatformConfig {
  id: string;
  name: string;
  urlPattern: string;         // 正则字符串
  selectors: {
    inputBox: string;         // 输入框 CSS 选择器
    anchorPoint: string;      // 按钮注入锚点
    sendButton?: string;      // 发送按钮（可选，用于自动发送）
  };
  insertMethod: 'execCommand' | 'nativeSetter' | 'clipboard';
  enabled: boolean;
  isBuiltin: boolean;         // 内置平台不可删除
}
```

### 3.4 统计数据 (Statistics)

```typescript
interface Statistics {
  // 按日聚合（保留最近 90 天）
  dailyStats: Record<string, DayStat>;  // key: 'YYYY-MM-DD'
  
  // 全局累计
  totalPromptUsage: number;
  totalTasksCompleted: number;
  totalTasksSnoozed: number;
  streakDays: number;          // 连续使用天数
  longestStreak: number;
}

interface DayStat {
  promptUsage: number;
  promptBreakdown: Record<string, number>;   // promptId → count
  platformBreakdown: Record<string, number>; // platform → count
  tasksCreated: number;
  tasksCompleted: number;
  tasksSnoozed: number;
}
```

---

## 四、存储策略

### 4.1 双层存储架构

```
chrome.storage.sync (≤100KB, 跨设备)
├── settings (全局设置)
├── promptIndex (ID + title + tags 的轻量索引)
└── taskIndex (ID + title + status 的轻量索引)

chrome.storage.local (≤10MB 默认, 可更大)
├── prompts (完整提示词数据)
├── tasks (完整任务数据)
├── statistics (使用统计)
├── platformConfigs (平台适配配置)
└── backups (自动备份快照)
```

**设计原则**：sync 只放"需要跨设备"的轻量数据；local 放全量数据。两者之间通过 `StorageManager` 类做统一封装，业务层不直接调用 chrome.storage API。

### 4.2 StorageManager 核心设计

```typescript
class StorageManager {
  // 单例
  private static instance: StorageManager;
  
  // 内存缓存（避免每次都读磁盘）
  private cache: Map<string, any> = new Map();
  private dirty: Set<string> = new Set();
  
  // 读（优先缓存）
  async get<T>(key: string): Promise<T | null>;
  
  // 写（写缓存 + 标记 dirty）
  async set(key: string, value: any): Promise<void>;
  
  // 刷盘（将 dirty 数据写入 chrome.storage）
  async flush(): Promise<void>;
  
  // 自动刷盘（防抖，500ms 无新写入后执行）
  private scheduleFlush(): void;
  
  // 全量导出（用于备份）
  async exportAll(): Promise<ExportBundle>;
  
  // 全量导入（用于恢复）
  async importAll(bundle: ExportBundle): Promise<void>;
}
```

### 4.3 数据迁移策略

每次版本升级时，StorageManager 检查 `schema_version` 字段，若版本不匹配则执行迁移脚本。迁移脚本按版本号顺序执行，每个脚本对数据做向前兼容的变换。

```typescript
const migrations: Record<number, (data: any) => any> = {
  1: (data) => { /* v0.1 → v0.2: 添加 task.priority 字段 */ },
  2: (data) => { /* v0.2 → v0.3: 重构 tags 为数组 */ },
};
```

---

## 五、核心模块详细设计

### 5.1 平台适配器 (PlatformAdapter)

这是整个扩展最脆弱、也最核心的模块。AI 网站频繁更新 DOM，适配器必须足够健壮。

**防御性选择器策略**：

```typescript
// ❌ 脆弱：依赖具体 class 名（随时可能改）
document.querySelector('.css-1dbjc4n.r-1awozwy')

// ✅ 稳健：使用语义属性、ARIA 角色、结构特征
document.querySelector('[contenteditable="true"][role="textbox"]')
document.querySelector('textarea[placeholder*="Message"]')
document.querySelector('form [data-placeholder]')
```

**选择器降级链**：每个平台配置多个选择器，按优先级尝试：

```typescript
const CLAUDE_INPUT_SELECTORS = [
  'div.ProseMirror[contenteditable="true"]',          // 首选：明确的 ProseMirror
  '[contenteditable="true"][data-placeholder]',         // 备选：带 placeholder 的可编辑区
  'fieldset [contenteditable="true"]',                  // 兜底：fieldset 内的可编辑区
];

function findInput(selectors: string[]): Element | null {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}
```

**文本插入的三种策略**：

| 策略 | 适用场景 | 原理 |
|------|---------|------|
| `execCommand('insertText')` | ProseMirror / Quill 等富文本编辑器 | 模拟用户输入，触发编辑器的 inputRule 处理 |
| Native Setter + InputEvent | React 控制的 textarea | 绕过 React 的合成事件系统，直接设值后触发原生 input 事件 |
| Clipboard API | 极端兜底 | 写入剪贴板 → focus 输入框 → `document.execCommand('paste')` |

**自动修复机制**：当检测到选择器全部失败时（连续 3 次 getInput 返回 null），Content Script 向 Background 发送 `ADAPTER_BROKEN` 消息，弹出通知提示用户"ChatGPT 页面结构已更新，请检查适配器设置或等待扩展更新"。

### 5.2 任务调度引擎 (TaskScheduler)

运行在 Background Service Worker 中，是任务管理的核心。

**生命周期**：

```
Service Worker 启动
    ↓
TaskScheduler.init()
    ↓
从 chrome.storage.local 加载所有 tasks
    ↓
遍历 tasks，根据 trigger 类型注册 alarms
    ↓
进入事件监听循环 ──→ Service Worker 可能休眠
    ↓                         ↑
chrome.alarms.onAlarm ────────┘
    ↓
查找对应 task → 执行提醒逻辑 → 重新调度（如有重复规则）
```

**关键实现**：

```typescript
class TaskScheduler {
  private tasks: Map<string, Task> = new Map();

  async init() {
    // 1. 加载数据
    const allTasks = await StorageManager.get<Task[]>('tasks');
    allTasks?.forEach(t => this.tasks.set(t.id, t));

    // 2. 清理旧 alarms，重新注册
    await chrome.alarms.clearAll();
    for (const task of this.tasks.values()) {
      this.scheduleTask(task);
    }

    // 3. 监听 alarm 触发
    chrome.alarms.onAlarm.addListener((alarm) => {
      this.handleAlarm(alarm);
    });
  }

  private scheduleTask(task: Task) {
    if (task.status !== 'pending' && task.status !== 'active') return;
    if (task.trigger.type !== 'time') return;
    if (!task.remindAt) return;

    const now = Date.now();
    const remindAt = task.remindAt;

    if (remindAt > now) {
      // 未来时间：注册一次性 alarm
      chrome.alarms.create(`task_${task.id}`, {
        when: remindAt,
      });
    }

    // 重复任务：计算下一次触发时间
    if (task.recurrence) {
      const nextTime = this.calculateNextOccurrence(task);
      if (nextTime) {
        chrome.alarms.create(`task_${task.id}_recur`, {
          when: nextTime,
          // periodInMinutes 仅适合固定间隔，不适合 "每周一三五" 这类
          // 所以每次手动计算下一次并注册新 alarm
        });
      }
    }
  }

  private async handleAlarm(alarm: chrome.alarms.Alarm) {
    const taskId = alarm.name.replace(/^task_/, '').replace(/_recur$/, '');
    const task = this.tasks.get(taskId);
    if (!task) return;

    // 1. 发送系统通知
    await this.sendNotification(task);

    // 2. 如果有 URL 触发关联，检查是否有匹配的标签页已打开
    if (task.targetPlatform || task.targetUrl) {
      await this.notifyMatchingTabs(task);
    }

    // 3. 如果是重复任务，计算并注册下一次
    if (task.recurrence) {
      const nextTime = this.calculateNextOccurrence(task);
      if (nextTime) {
        task.remindAt = nextTime;
        await StorageManager.set('tasks', [...this.tasks.values()]);
        this.scheduleTask(task);
      } else {
        task.status = 'done';
        await StorageManager.set('tasks', [...this.tasks.values()]);
      }
    }
  }

  private async sendNotification(task: Task) {
    const options: chrome.notifications.NotificationOptions = {
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: `⏰ ${task.title}`,
      message: task.description || '任务提醒',
      priority: task.priority === 'urgent' ? 2 : 1,
      requireInteraction: true,  // 通知不自动消失
      buttons: [
        { title: '打开并执行' },
        { title: '暂缓 30 分钟' },
      ],
    };
    chrome.notifications.create(`pv_task_${task.id}`, options);
  }

  private calculateNextOccurrence(task: Task): number | null {
    const rule = task.recurrence;
    if (!rule) return null;

    const now = new Date();
    let next = new Date(task.remindAt || now.getTime());

    switch (rule.frequency) {
      case 'daily':
        next.setDate(next.getDate() + rule.interval);
        break;
      case 'weekly':
        // 找到本周下一个匹配的 dayOfWeek
        // 如果本周已过完，跳到下周
        next = this.findNextWeekday(next, rule.daysOfWeek || [], rule.interval);
        break;
      case 'monthly':
        next.setMonth(next.getMonth() + rule.interval);
        break;
    }

    if (rule.endDate && next.getTime() > rule.endDate) return null;
    return next.getTime();
  }
}
```

### 5.3 通知引擎 (NotificationEngine)

**通知点击处理流程**：

```
用户点击通知中的"打开并执行"
    ↓
chrome.notifications.onButtonClicked 捕获
    ↓
查找 task.targetUrl 或 task.targetPlatform
    ↓
┌─ 已有匹配标签页？─→ chrome.tabs.update(tabId, {active:true})
│                       ↓
│                    chrome.tabs.sendMessage(tabId, {
│                      type: 'PROMPT_INSERT',
│                      promptId: task.promptId
│                    })
│
└─ 没有匹配标签页？─→ chrome.tabs.create({url: targetUrl})
                       ↓
                    在 onUpdated 中等待页面加载完成
                       ↓
                    chrome.tabs.sendMessage(newTabId, {
                      type: 'PROMPT_INSERT',
                      promptId: task.promptId
                    })
```

**降级策略**（当系统通知被禁用时）：

```typescript
async function notifyWithFallback(task: Task) {
  try {
    // 先尝试系统通知
    chrome.notifications.create(`pv_task_${task.id}`, options);
  } catch {
    // 降级：在所有匹配的 AI 标签页注入提醒条
    const tabs = await chrome.tabs.query({ url: AI_PLATFORM_URLS });
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, {
        type: 'SHOW_REMINDER_BAR',
        task,
      });
    }
  }
}
```

### 5.4 URL 触发检测器 (URLTriggerDetector)

运行在 Content Script 中，页面加载后检查是否有匹配当前 URL 的待办任务。

```typescript
class URLTriggerDetector {
  async check() {
    const currentUrl = window.location.href;
    
    // 向 Background 查询匹配的任务
    const response = await chrome.runtime.sendMessage({
      type: 'GET_URL_TRIGGERED_TASKS',
      payload: { url: currentUrl },
    });

    if (response.tasks?.length > 0) {
      this.showReminderBar(response.tasks);
    }
  }

  private showReminderBar(tasks: Task[]) {
    // 在页面顶部注入一个不影响布局的固定条
    const bar = document.createElement('div');
    bar.id = 'pv-reminder-bar';
    bar.innerHTML = `
      <div class="pv-rb-content">
        <span class="pv-rb-icon">⏰</span>
        <span class="pv-rb-text">
          你有 ${tasks.length} 个待办任务与此页面相关
        </span>
        <button class="pv-rb-action" id="pv-rb-view">查看</button>
        <button class="pv-rb-dismiss" id="pv-rb-close">×</button>
      </div>
    `;
    document.body.prepend(bar);

    document.getElementById('pv-rb-view').onclick = () => {
      // 打开面板的任务 Tab
      this.openPanelToTasks();
      bar.remove();
    };
    document.getElementById('pv-rb-close').onclick = () => bar.remove();
  }
}
```

### 5.5 浮动面板 (FloatingPanel)

在现有提示词面板基础上扩展为双 Tab 结构。

```
┌─────────────────────────────────┐
│ Prompt Vault+            ＋ ╳   │
├────────────┬────────────────────┤
│  📝 提示词  │  ✅ 任务           │ ← Tab 切换
├────────────┴────────────────────┤
│ 🔍 搜索...                      │
├─────────────────────────────────┤
│ [全部] [翻译] [编程] [写作]      │ ← 标签过滤（提示词Tab）
├─────────────────────────────────┤ ← 或状态过滤（任务Tab）
│ [待办] [今日] [已完成] [暂缓]    │
├─────────────────────────────────┤
│                                 │
│  ┌─────────────────────────┐   │
│  │ 📌 翻译助手              │   │ ← 提示词卡片（可点击插入）
│  │ 你是一位专业的翻译...     │   │
│  │ [翻译] [通用]  使用 12次  │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │ ← 或任务卡片
│  │ ⏰ 每日日报生成    🔴高   │   │
│  │ 9:00 AM · 每天 · ChatGPT │   │
│  │ [完成] [暂缓] [编辑]     │   │
│  └─────────────────────────┘   │
│                                 │
└─────────────────────────────────┘
```

### 5.6 链式任务引擎 (TaskChainEngine)

支持"做完 A 再做 B"的工作流编排。

```
任务 A (需求分析 / ChatGPT)
    │ 完成
    ↓
任务 B (代码实现 / Claude)  ← 自动激活 + 提醒
    │ 完成
    ↓
任务 C (代码审查 / ChatGPT)
```

实现方式：当用户标记任务 A 为完成时，Background 遍历 A 的 `childTaskIds`，将子任务状态从 `pending` 更新为 `active`，并根据子任务的 trigger 类型执行相应的提醒逻辑。

---

## 六、文件结构

```
prompt-vault-plus/
├── manifest.json                    # MV3 配置
├── package.json                     # 依赖管理（构建用）
├── tsconfig.json                    # TypeScript 配置
├── vite.config.ts                   # Vite 构建配置
│
├── src/
│   ├── types/                       # 全局类型定义
│   │   ├── prompt.ts
│   │   ├── task.ts
│   │   ├── settings.ts
│   │   ├── messages.ts              # 消息协议类型
│   │   └── statistics.ts
│   │
│   ├── core/                        # 核心业务逻辑（上下文无关）
│   │   ├── storage/
│   │   │   ├── StorageManager.ts    # 统一存储封装
│   │   │   └── migrations.ts        # 数据迁移脚本
│   │   ├── scheduler/
│   │   │   ├── TaskScheduler.ts     # 任务调度引擎
│   │   │   ├── RecurrenceCalculator.ts
│   │   │   └── TaskChainEngine.ts   # 链式任务
│   │   ├── notifications/
│   │   │   └── NotificationEngine.ts
│   │   └── statistics/
│   │       └── StatsCollector.ts    # 使用数据采集
│   │
│   ├── platforms/                   # 平台适配器
│   │   ├── AdapterRegistry.ts       # 适配器注册中心
│   │   ├── BaseAdapter.ts           # 适配器基类
│   │   ├── ChatGPTAdapter.ts
│   │   ├── ClaudeAdapter.ts
│   │   ├── GeminiAdapter.ts
│   │   ├── DeepSeekAdapter.ts
│   │   ├── KimiAdapter.ts
│   │   └── GenericAdapter.ts        # 通用兜底
│   │
│   ├── background/                  # Service Worker
│   │   ├── index.ts                 # 入口：初始化 + 事件监听
│   │   ├── messageRouter.ts         # 消息路由
│   │   ├── alarmHandler.ts          # alarm 事件处理
│   │   └── notificationHandler.ts   # 通知点击处理
│   │
│   ├── content/                     # Content Script
│   │   ├── index.ts                 # 入口：平台检测 + 模块加载
│   │   ├── FloatingPanel.ts         # 浮动面板 UI
│   │   ├── PromptTab.ts             # 提示词 Tab
│   │   ├── TaskTab.ts               # 任务 Tab
│   │   ├── ReminderBar.ts           # 页面内提醒条
│   │   ├── VariableDialog.ts        # 模板变量填写弹窗
│   │   ├── URLTriggerDetector.ts    # URL 触发检测
│   │   └── style.css                # 注入样式
│   │
│   ├── popup/                       # Popup 弹窗
│   │   ├── index.html
│   │   ├── index.ts
│   │   ├── Dashboard.ts             # 仪表盘组件
│   │   ├── QuickActions.ts          # 快速操作
│   │   └── style.css
│   │
│   └── options/                     # 设置页
│       ├── index.html
│       ├── index.ts
│       ├── PlatformManager.ts       # 平台适配器管理
│       ├── DataManager.ts           # 数据导入导出
│       ├── ShortcutConfig.ts        # 快捷键配置
│       └── style.css
│
├── public/
│   └── icons/                       # 扩展图标
│       ├── icon16.png
│       ├── icon48.png
│       └── icon128.png
│
├── tests/                           # 测试
│   ├── unit/
│   │   ├── StorageManager.test.ts
│   │   ├── TaskScheduler.test.ts
│   │   ├── RecurrenceCalculator.test.ts
│   │   └── adapters.test.ts
│   └── e2e/
│       ├── prompt-insert.spec.ts    # Playwright 端到端测试
│       └── task-reminder.spec.ts
│
└── scripts/
    ├── build.ts                     # 构建脚本
    └── release.ts                   # 发布脚本
```

---

## 七、技术选型

| 技术 | 选择 | 理由 |
|------|------|------|
| 语言 | TypeScript | 复杂的数据模型需要类型安全 |
| 构建 | Vite + CRXJS | 社区最成熟的 MV3 扩展构建方案，支持 HMR |
| UI | 原生 DOM + CSS Variables | Content Script 不适合引入 React（包体积 + 沙箱限制） |
| 测试 | Vitest (单元) + Playwright (E2E) | 与 Vite 生态一致 |
| 状态管理 | 发布-订阅模式 | 轻量，不需要 Redux 这类重型方案 |
| ID 生成 | nanoid | 短、URL 安全、碰撞概率极低 |
| 日期处理 | date-fns | 轻量（tree-shakeable），不引入 moment |
| 图标 | Lucide Icons (SVG inline) | 一致的设计语言，按需引入 |

---

## 八、开发阶段规划

### Phase 1：提示词管理 MVP (2 周)

**目标**：核心可用——能在所有 AI 平台上保存和插入提示词。

| 子任务 | 天数 | 产出 |
|--------|------|------|
| 项目脚手架搭建 (Vite + CRXJS + TS) | 1 | 可构建的空扩展 |
| 平台适配器实现 (6 个平台) | 2 | platforms/ 全部完成 |
| StorageManager + 数据模型 | 1 | 存储层封装完成 |
| 浮动面板 UI (提示词 Tab) | 2 | 搜索、标签、列表、插入 |
| 模板变量弹窗 | 1 | {{变量}} 识别 + 填写 |
| Popup 基础版 | 1 | 统计 + 导入导出 |
| 多平台适配器测试 + 修复 | 2 | 6 个平台全部验证通过 |

**里程碑交付物**：可以在 ChatGPT / Claude / Gemini / DeepSeek / Kimi / Poe 上正常使用的提示词管理扩展。

### Phase 2：任务管理 + 提醒 (3 周)

**目标**：完整的任务 CRUD + 定时提醒 + 系统通知。

| 子任务 | 天数 | 产出 |
|--------|------|------|
| Task 数据模型 + CRUD API | 1 | 任务存储层 |
| 浮动面板增加任务 Tab | 2 | 任务列表 + 创建/编辑表单 |
| TaskScheduler (alarm 注册与触发) | 2 | 定时调度核心 |
| NotificationEngine (系统通知 + 点击处理) | 2 | 通知弹出 + 跳转 |
| 通知点击 → 打开页面 → 预填提示词 完整链路 | 2 | 端到端可用 |
| 降级提醒条 (ReminderBar) | 1 | 页面内提醒 UI |
| 任务与提示词关联 UI | 1 | 创建任务时可选择关联提示词 |
| 单元测试覆盖 | 2 | Scheduler + Notification 测试 |
| 多场景集成测试 | 2 | 各种提醒触发路径验证 |

**里程碑交付物**：可以创建定时任务，到点弹出系统通知，点击通知后自动打开 AI 页面并预填提示词。

### Phase 3：高级触发 + 工作流 (2 周)

**目标**：URL 触发、重复任务、链式任务。

| 子任务 | 天数 | 产出 |
|--------|------|------|
| URLTriggerDetector | 2 | 打开匹配页面时自动提醒 |
| RecurrenceCalculator | 2 | 每日/每周/每月/自定义重复 |
| TaskChainEngine | 2 | 链式任务（A 完成后激活 B） |
| 任务创建 UI 升级（重复规则 + 链式配置） | 2 | 完整的任务编辑表单 |
| 边界情况处理 + 回归测试 | 2 | 跨天、时区、Service Worker 重启 |

**里程碑交付物**：支持"每天早上 9 点提醒用 ChatGPT 跑日报"、"打开 Claude 自动提醒继续翻译"、"做完需求分析后自动提醒写代码"。

### Phase 4：统计 + 优化 + 发布 (2 周)

**目标**：数据洞察、性能优化、商店发布。

| 子任务 | 天数 | 产出 |
|--------|------|------|
| StatsCollector + 数据聚合 | 2 | 使用统计数据采集 |
| Popup 仪表盘（图表） | 2 | 可视化统计面板 |
| Options 设置页完整实现 | 2 | 平台管理 + 快捷键 + 数据管理 |
| 性能优化（Content Script 启动速度、内存占用） | 2 | 性能基准测试 |
| Chrome Web Store 准备（截图、描述、隐私声明） | 1 | 上架材料 |
| Chrome Web Store 提交 + 审核反馈处理 | 1 | 正式上架 |

### Phase 5：扩展功能 (持续迭代)

- 云同步（Google Drive / WebDAV）
- 提示词社区分享（匿名上传/下载热门提示词）
- 右键菜单"选中文本 → 保存为提示词"
- AI 辅助功能：自动分析用户常用提示词，建议优化
- Side Panel 模式（Chrome 116+ 原生侧边栏）
- Firefox / Edge 适配发布

---

## 九、关键技术风险与应对

### 9.1 Service Worker 休眠

**风险**：MV3 的 Service Worker 空闲 ~30s 后被杀，所有内存状态丢失。

**应对**：
- 不使用 `setTimeout` / `setInterval`，全部用 `chrome.alarms`（最小精度 1 分钟）
- 需要亚分钟精度时：提前 1 分钟用 alarm 唤醒，然后内部 `setTimeout` 微调
- Service Worker 每次启动都重新从 storage 加载状态，不依赖内存持久化
- 全局状态序列化到 `chrome.storage.session`（MV3 特有，Service Worker 生命周期内持久）

### 9.2 DOM 选择器失效

**风险**：AI 平台更新 DOM 结构，导致适配器无法定位输入框。

**应对**：
- 每个平台配置 3-5 个降级选择器
- 优先使用语义化属性（ARIA、data-*、role）而非 class 名
- Options 页面允许用户手动编辑选择器（高级功能）
- 选择器失败时发送 telemetry（可选），帮助开发者快速修复
- 通用适配器 (GenericAdapter) 作为最终兜底

### 9.3 chrome.storage.sync 容量限制

**风险**：sync 存储总量 100KB，单项 8KB，写入频率限制 ~120次/分钟。

**应对**：
- sync 只放 settings 和轻量索引
- 全量数据放 local（理论无上限，默认 10MB）
- 写操作合并防抖（500ms 窗口内的多次写合并为一次）
- 超出限制时自动降级为 local-only 模式

### 9.4 通知权限

**风险**：用户在操作系统层面关闭了 Chrome 的通知权限。

**应对**：
- 首次使用任务功能时检测通知权限状态并引导开启
- 通知失败时降级为页面内提醒条 (ReminderBar)
- 在 Popup 中显示通知权限状态指示器
- Badge 文字提示（扩展图标角标显示待办数量）

### 9.5 跨标签页状态一致性

**风险**：用户在 Tab A 添加了提示词，Tab B 的面板看不到。

**应对**：
- Background 监听 `chrome.storage.onChanged`，变更时广播 `STORAGE_UPDATED` 到所有 Content Script
- Content Script 收到广播后刷新缓存 + 重新渲染面板
- 使用乐观更新（先改 UI，再异步写 storage），避免卡顿感

### 9.6 内容安全策略 (CSP)

**风险**：某些 AI 网站的 CSP 限制了 Content Script 的行为。

**应对**：
- MV3 Content Script 运行在隔离世界（isolated world），不受页面 CSP 限制
- 但注入的样式需要用 `chrome.scripting.insertCSS` 或 `style` 标签（非 `<link>`），避免外部资源加载
- 所有 SVG 图标 inline 嵌入，不使用外部图标库 CDN

---

## 十、测试策略

### 10.1 单元测试 (Vitest)

| 模块 | 测试重点 |
|------|---------|
| StorageManager | 读写、缓存一致性、防抖刷盘、迁移脚本 |
| TaskScheduler | alarm 注册逻辑、重复任务计算、链式任务激活 |
| RecurrenceCalculator | 各种重复规则的下一次时间计算、边界（跨月/跨年/闰年） |
| PlatformAdapters | 选择器降级链、文本插入方法分支 |
| 模板变量解析 | 嵌套变量、转义字符、空变量 |

### 10.2 集成测试 (Playwright)

| 场景 | 验证点 |
|------|--------|
| 在 ChatGPT 插入提示词 | 面板弹出 → 搜索 → 点击 → 文本出现在输入框 |
| 定时任务提醒 | 创建定时任务 → 等待触发 → 通知弹出 → 点击跳转 |
| URL 触发提醒 | 创建 URL 任务 → 打开匹配页面 → 提醒条出现 |
| 跨标签页同步 | Tab A 添加提示词 → Tab B 面板自动更新 |
| 数据导入导出 | 导出 JSON → 全部删除 → 导入 → 数据恢复 |

### 10.3 手动测试矩阵

| | ChatGPT | Claude | Gemini | DeepSeek | Kimi | Poe |
|--|---------|--------|--------|----------|------|-----|
| 面板弹出 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 文本插入 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 模板变量 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 提醒条显示 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| SPA 路由切换后恢复 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |

---

## 十一、发布与运维

### 11.1 版本策略

采用语义化版本 (SemVer)：
- `MAJOR.MINOR.PATCH`
- PATCH: 适配器选择器更新、bug 修复
- MINOR: 新功能（如新平台支持、UI 改进）
- MAJOR: 数据模型不兼容变更（需迁移脚本）

### 11.2 适配器热更新机制

AI 平台 DOM 更新是最高频的维护需求。设计一个远程配置机制：

```typescript
// 每次扩展启动时从 GitHub 拉取最新选择器配置
async function fetchRemoteSelectors() {
  try {
    const resp = await fetch(
      'https://raw.githubusercontent.com/xxx/prompt-vault-plus/main/selectors.json'
    );
    const remote = await resp.json();
    await StorageManager.set('remote_selectors', remote);
  } catch {
    // 离线则使用本地内置版本
  }
}
```

这样在 AI 平台更新 DOM 后，只需更新 GitHub 上的 JSON 文件，用户无需等待 Chrome Web Store 审核。

### 11.3 隐私声明要点

- 所有数据仅存储在用户本地浏览器
- 不收集任何用户数据
- 不与任何第三方共享数据
- 远程选择器配置仅拉取公开的 JSON 文件，不发送任何用户信息
- 完全开源，可自行审计

---

## 十二、后续扩展方向

### 12.1 云同步方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| Google Drive (Voyager 方案) | 用户已有账号、容量大 | 需要 OAuth2、API 配额限制 |
| GitHub Gist | 开发者友好、版本历史 | 普通用户不理解 Gist |
| WebDAV (Nextcloud/坚果云) | 国内可用、自建可控 | 需要用户配置服务器地址 |
| chrome.storage.sync | 零配置 | 100KB 限制，数据多了不够 |

**推荐**：Phase 1-4 用 chrome.storage.sync 做轻量同步；Phase 5 增加可选的 Google Drive 全量同步。

### 12.2 AI 辅助功能

- 分析用户的提示词使用模式，推荐优化建议
- 根据当前对话上下文，智能推荐最相关的提示词
- 自动从对话中提取高质量提示词片段

### 12.3 多浏览器发布

| 浏览器 | 改动 | 分发渠道 |
|--------|------|---------|
| Chrome | 基准版本 | Chrome Web Store |
| Edge | 删除 manifest.key | Microsoft Edge Add-ons |
| Firefox | MV2 兼容层 + browser.* API polyfill | Firefox AMO |
| Safari | Xcode Web Extension 转换 | App Store |

---

*文档版本：v1.0 · 最后更新：2026-03-05*
