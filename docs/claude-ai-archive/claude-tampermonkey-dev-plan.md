# Claude.ai 篡改猴（Tampermonkey）脚本开发方案

> 基于《Claude.ai 网页端高效使用完全指南》十大维度痛点，设计一套可在 Tampermonkey / Violentmonkey / Greasemonkey 等用户脚本管理器中加载的浏览器增强脚本体系。与 Artifact 方案不同，用户脚本可以**直接注入 claude.ai 页面 DOM、拦截网络请求、持久化本地数据**，实现真正的"原生增强"体验。

---

## 一、技术架构总览

### 1.1 用户脚本 vs Artifact 方案对比

| 维度 | Tampermonkey 用户脚本 | Artifact 方案 |
|------|---------------------|---------------|
| 运行环境 | 浏览器页面级注入，完全访问 DOM | 沙箱 iframe，与主页面隔离 |
| 网络拦截 | 可 hook `fetch`/`XMLHttpRequest` | 不可 |
| 数据持久化 | `GM_setValue` / `localStorage` / `IndexedDB` | `window.storage`（受限） |
| UI 注入 | 直接修改 claude.ai 界面 | 独立渲染区 |
| 自动化能力 | 可监听事件、自动触发操作 | 被动响应 |
| 跨页面 | 可在所有 claude.ai 页面运行 | 仅当前对话 |
| 分发方式 | `.user.js` 文件 / GreasyFork | 对话内生成 |

### 1.2 脚本元数据模板

```javascript
// ==UserScript==
// @name         Claude.ai Enhancer - [模块名]
// @namespace    https://claude.ai/
// @version      1.0.0
// @description  [模块描述]
// @author       [作者]
// @match        https://claude.ai/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_addStyle
// @grant        GM_registerMenuCommand
// @grant        GM_notification
// @grant        GM_xmlhttpRequest
// @run-at       document-idle
// @noframes
// ==/UserScript==
```

### 1.3 核心技术能力

```
┌─────────────────────────────────────────────────┐
│              Tampermonkey 脚本层                  │
├──────────┬──────────┬──────────┬────────────────┤
│ DOM 注入  │ 网络拦截  │ 数据存储  │ 事件监听       │
│ 侧边栏   │ fetch    │ GM_*     │ MutationObs    │
│ 浮窗     │ hook     │ IndexedDB│ 键盘快捷键      │
│ Toast    │ 请求/响应 │ 导入导出  │ 页面路由变化    │
├──────────┴──────────┴──────────┴────────────────┤
│              claude.ai 页面                      │
└─────────────────────────────────────────────────┘
```

---

## 二、脚本模块清单与优先级

| 优先级 | 模块名称 | 核心能力 | 对应指南章节 | 复杂度 |
|--------|---------|---------|-------------|--------|
| **P0** | Token 实时计数器 | hook fetch 拦截请求/响应，实时统计 token | 第一/七章 | ★★★ |
| **P0** | 对话轮次警告器 | 监控对话长度，自动提示开新对话 | 第一章 | ★★☆ |
| **P0** | 上下文接力助手 | 一键生成摘要 Prompt 并复制 | 第一章 | ★★☆ |
| **P1** | Prompt 模板快捷面板 | 侧边栏模板库 + 一键插入输入框 | 第二章 | ★★★ |
| **P1** | 模型 & 功能状态栏 | 顶部显示当前模型/功能开关/预估成本 | 第四/六章 | ★★☆ |
| **P1** | 额度监控面板 | 5h 窗口倒计时 + 使用量追踪 | 第九章 | ★★★ |
| **P2** | 对话导出器 | 导出为 Markdown/JSON，支持批量 | 第一章 | ★★☆ |
| **P2** | 快捷键增强 | 全局快捷键（新对话/切模型/发送等） | 全局效率 | ★☆☆ |
| **P3** | 文件 Token 预估器 | 上传前预估文件 token 消耗 | 第七章 | ★★☆ |

---

## 三、各模块详细设计

---

### 3.1 [P0] Token 实时计数器

**这是整套方案中最核心、最有技术深度的模块。** 指南反复强调"Claude.ai 不显示上下文窗口填充百分比"——本模块通过拦截网络请求直接解决。

#### 3.1.1 技术原理

Claude.ai 前端通过 `fetch` 向 `/api/organizations/{org_id}/chat_conversations/{conv_id}/completion` 发送 POST 请求（SSE 流式响应）。我们可以 hook 全局 `fetch` 函数，捕获：

- **请求体**：包含 `prompt`（当前用户输入）和对话历史
- **响应流**：SSE 格式的模型输出

通过分析请求/响应的文本长度，结合 token 估算算法，实现实时统计。

#### 3.1.2 核心代码框架

```javascript
(function() {
  'use strict';

  // ========== Token 估算引擎 ==========
  const TokenEstimator = {
    // 中文：1字 ≈ 2 tokens | 英文：1词 ≈ 1.3 tokens
    estimate(text) {
      if (!text) return 0;
      const chineseChars = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length;
      const remaining = text.replace(/[\u4e00-\u9fff\u3400-\u4dbf]/g, '');
      const englishWords = remaining.split(/\s+/).filter(Boolean).length;
      const punctuation = (remaining.match(/[^\w\s]/g) || []).length;
      return Math.ceil(chineseChars * 2 + englishWords * 1.3 + punctuation * 0.5);
    },

    // 文件类型 token 估算
    estimateFile(type, meta) {
      switch(type) {
        case 'pdf': return meta.pages * 2250; // 1500-3000 取中值
        case 'image': return Math.ceil((meta.width * meta.height) / 750);
        case 'text': return this.estimate(meta.content);
        default: return 0;
      }
    }
  };

  // ========== Fetch Hook ==========
  const originalFetch = window.fetch;
  let sessionStats = {
    totalInputTokens: 0,
    totalOutputTokens: 0,
    messageCount: 0,
    conversationStart: null,
    history: []
  };

  window.fetch = async function(...args) {
    const [url, options] = args;

    // 仅拦截 Claude completion 请求
    if (typeof url === 'string' && url.includes('/completion')) {
      try {
        const body = JSON.parse(options?.body || '{}');
        const inputTokens = TokenEstimator.estimate(body.prompt || '');

        sessionStats.messageCount++;
        sessionStats.totalInputTokens += inputTokens;
        if (!sessionStats.conversationStart) {
          sessionStats.conversationStart = Date.now();
        }

        // 记录本次消息
        sessionStats.history.push({
          time: new Date().toISOString(),
          type: 'input',
          tokens: inputTokens,
          cumulative: sessionStats.totalInputTokens
        });

        updateUI();
      } catch(e) { /* 静默失败 */ }
    }

    // 执行原始请求
    const response = await originalFetch.apply(this, args);

    // 拦截 SSE 响应流以统计输出 token
    if (typeof url === 'string' && url.includes('/completion') && response.body) {
      const reader = response.body.getReader();
      let outputText = '';
      const decoder = new TextDecoder();

      const newStream = new ReadableStream({
        async start(controller) {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              // 流结束，统计输出 token
              const outputTokens = TokenEstimator.estimate(outputText);
              sessionStats.totalOutputTokens += outputTokens;
              sessionStats.history.push({
                time: new Date().toISOString(),
                type: 'output',
                tokens: outputTokens,
                cumulative: sessionStats.totalOutputTokens
              });
              updateUI();
              controller.close();
              break;
            }
            // 解析 SSE 数据块
            const chunk = decoder.decode(value, { stream: true });
            outputText += extractTextFromSSE(chunk);
            controller.enqueue(value);
          }
        }
      });

      return new Response(newStream, {
        headers: response.headers,
        status: response.status,
        statusText: response.statusText
      });
    }

    return response;
  };

  // ========== SSE 文本提取 ==========
  function extractTextFromSSE(chunk) {
    // Claude SSE 格式: data: {"type":"content_block_delta","delta":{"text":"..."}}
    let text = '';
    const lines = chunk.split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          if (data.delta?.text) text += data.delta.text;
          if (data.type === 'completion' && data.completion) text += data.completion;
        } catch(e) {}
      }
    }
    return text;
  }

  // ========== UI 渲染 ==========
  function updateUI() { /* 见 UI 模块 */ }
})();
```

#### 3.1.3 UI 注入设计

在 claude.ai 页面右下角注入一个**可折叠浮窗**：

```
┌─────────────────────────────────┐
│ 📊 Token Monitor         [_][×]│
├─────────────────────────────────┤
│                                 │
│  上下文窗口   ████████░░  67%   │
│  134,000 / 200,000 tokens       │
│                                 │
│  ┌───────┬───────┬───────┐     │
│  │ 输入   │ 输出   │ 总计  │     │
│  │ 89.2K  │ 44.8K  │134.0K│     │
│  └───────┴───────┴───────┘     │
│                                 │
│  本轮消息: #12  ⚠️ 建议开新对话  │
│  预估成本: Sonnet $0.42         │
│                                 │
│  [📋 详细统计] [🔄 重置]        │
└─────────────────────────────────┘
```

**警告阈值：**
- 50% (100K)：黄色提示"上下文已过半，注意信息密度"
- 70% (140K)：橙色警告"建议精简或准备接力"
- 90% (180K)：红色警告"即将触发压缩，强烈建议开新对话"
- 消息数 > 12：提示"已超过推荐轮次，建议开新对话"

#### 3.1.4 数据存储

```javascript
// 使用 GM_setValue 持久化统计数据
function saveStats() {
  GM_setValue('token_stats_history', JSON.stringify({
    sessions: [...previousSessions, sessionStats],
    lastUpdated: Date.now()
  }));
}

// 使用 IndexedDB 存储大量历史数据（可选）
const DB_NAME = 'claude_enhancer';
const STORE_NAME = 'token_history';
```

---

### 3.2 [P0] 对话轮次警告器

**对应痛点：** 指南第一章——"每 10-15 条消息开一个新对话"可节省 3 倍 token。

#### 3.2.1 核心逻辑

```javascript
// 监控 DOM 变化，统计对话轮次
const conversationObserver = new MutationObserver((mutations) => {
  // Claude.ai 的消息容器选择器（需根据实际 DOM 调整）
  const messages = document.querySelectorAll('[data-testid="user-message"]');
  const messageCount = messages.length;

  if (messageCount >= 10 && messageCount < 15) {
    showWarning('yellow',
      `已发送 ${messageCount} 条消息，建议考虑开新对话`,
      `当前对话累计处理约 ${estimateCumulativeTokens(messageCount)} tokens`
    );
  } else if (messageCount >= 15) {
    showWarning('red',
      `已发送 ${messageCount} 条消息！强烈建议开新对话`,
      `继续对话的 token 效率仅为新对话的 ${Math.round(100/messageCount*10)}%`,
      { showRelayButton: true }  // 显示"一键接力"按钮
    );
  }
});

// 在消息容器上启动观察
function initObserver() {
  const chatContainer = document.querySelector('[class*="conversation"]')
    || document.querySelector('main');
  if (chatContainer) {
    conversationObserver.observe(chatContainer, {
      childList: true, subtree: true
    });
  }
}
```

#### 3.2.2 警告 UI

在对话界面顶部注入**非侵入式横幅**：

```javascript
function showWarning(level, title, detail, options = {}) {
  const colors = {
    yellow: { bg: '#FEF3C7', border: '#F59E0B', text: '#92400E' },
    red:    { bg: '#FEE2E2', border: '#EF4444', text: '#991B1B' }
  };
  const c = colors[level];

  const banner = document.createElement('div');
  banner.id = 'claude-enhancer-warning';
  banner.innerHTML = `
    <div style="
      position: fixed; top: 8px; left: 50%; transform: translateX(-50%);
      z-index: 10000; padding: 12px 20px; border-radius: 12px;
      background: ${c.bg}; border: 1px solid ${c.border};
      color: ${c.text}; font-size: 14px; max-width: 600px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      display: flex; align-items: center; gap: 12px;
    ">
      <span style="font-size: 20px;">${level === 'red' ? '🔴' : '🟡'}</span>
      <div>
        <div style="font-weight: 600;">${title}</div>
        <div style="font-size: 12px; opacity: 0.8; margin-top: 2px;">${detail}</div>
      </div>
      ${options.showRelayButton ? `
        <button id="relay-btn" style="
          margin-left: auto; padding: 6px 14px; border-radius: 8px;
          background: ${c.border}; color: white; border: none;
          cursor: pointer; font-size: 13px; white-space: nowrap;
        ">🔄 一键接力</button>
      ` : ''}
      <button onclick="this.parentElement.remove()" style="
        background: none; border: none; cursor: pointer;
        font-size: 18px; color: ${c.text}; opacity: 0.5;
      ">×</button>
    </div>
  `;

  // 移除旧警告
  document.getElementById('claude-enhancer-warning')?.remove();
  document.body.appendChild(banner);

  // 绑定接力按钮
  if (options.showRelayButton) {
    banner.querySelector('#relay-btn')?.addEventListener('click', triggerRelay);
  }
}
```

---

### 3.3 [P0] 上下文接力助手

**对应痛点：** 指南第一章——手动接力工作流可实现 80-95% 的 token 缩减。

#### 3.3.1 核心功能

1. **一键注入摘要 Prompt**：在输入框中自动填入接力摘要请求
2. **场景化模板**：编程 / 写作 / 分析 / 翻译 / 通用 五套模板
3. **摘要暂存区**：将 Claude 的摘要回复保存到本地，方便粘贴到新对话
4. **新对话快捷跳转**：保存摘要后一键跳转新对话并自动粘贴

#### 3.3.2 模板库

```javascript
const RELAY_TEMPLATES = {
  general: {
    name: '通用接力',
    prompt: `请为当前对话生成一份接力摘要，用于在新对话中恢复上下文。严格按以下 XML 结构输出：

<relay_summary>
  <decisions>本次对话中的所有关键决策及理由</decisions>
  <current_state>项目/任务的当前进展状态</current_state>
  <open_questions>尚未解决的问题和待确认事项</open_questions>
  <context>关键背景信息、约束条件</context>
  <next_steps>接下来需要执行的具体任务（按优先级排列）</next_steps>
</relay_summary>

要求：总长度 500 词以内，信息密度最大化，去除所有冗余描述。`
  },

  coding: {
    name: '编程接力',
    prompt: `请为当前编程对话生成接力摘要：

<relay_summary>
  <architecture>技术选型、项目结构、架构决策</architecture>
  <completed>已完成的功能模块及关键实现细节</completed>
  <current_code>当前正在处理的代码（仅关键部分）</current_code>
  <bugs_and_issues>已知问题、待修复 bug</bugs_and_issues>
  <dependencies>关键依赖、版本、配置</dependencies>
  <next_tasks>下一步开发任务（按优先级）</next_tasks>
</relay_summary>

要求：保留关键代码片段和文件路径，去除探索性讨论。`
  },

  writing: {
    name: '写作接力',
    prompt: `请为当前写作对话生成接力摘要：

<relay_summary>
  <topic>文章主题和核心论点</topic>
  <outline>当前大纲结构</outline>
  <completed_sections>已完成的章节摘要</completed_sections>
  <style_guide>确定的风格、语气、受众要求</style_guide>
  <pending>待撰写的部分及要点</pending>
  <feedback>已收到的修改意见</feedback>
</relay_summary>`
  },

  analysis: {
    name: '分析接力',
    prompt: `请为当前分析对话生成接力摘要：

<relay_summary>
  <objective>分析目标和关键问题</objective>
  <data_sources>使用的数据源及处理方法</data_sources>
  <findings>已得出的关键发现（附数据支撑）</findings>
  <methodology>采用的分析方法</methodology>
  <open_questions>待验证的假设和未解答的问题</open_questions>
  <next_analysis>下一步分析计划</next_analysis>
</relay_summary>`
  },

  translation: {
    name: '翻译接力',
    prompt: `请为当前翻译对话生成接力摘要：

<relay_summary>
  <source_info>源文档信息（语言、领域、风格）</source_info>
  <glossary>已确定的专业术语翻译对照表</glossary>
  <style_decisions>翻译风格决策（直译/意译/混合）</style_decisions>
  <completed>已翻译部分的概要</completed>
  <pending>待翻译的内容描述</pending>
  <issues>翻译难点和待讨论的表达</issues>
</relay_summary>`
  }
};
```

#### 3.3.3 输入框注入逻辑

```javascript
function injectPromptToInput(promptText) {
  // Claude.ai 使用 ProseMirror / contenteditable 编辑器
  // 需要模拟真实输入以触发 React 状态更新
  const editor = document.querySelector(
    '[contenteditable="true"].ProseMirror'  // 主输入框选择器
    // 备选: 'div[contenteditable="true"]'
  );

  if (!editor) {
    console.error('未找到输入框');
    return;
  }

  // 方案 A：使用 execCommand（兼容性好）
  editor.focus();
  document.execCommand('selectAll', false, null);
  document.execCommand('insertText', false, promptText);

  // 方案 B：直接设置内容 + 触发 input 事件（备选）
  // editor.textContent = promptText;
  // editor.dispatchEvent(new Event('input', { bubbles: true }));

  // 显示成功提示
  showToast('✅ 接力 Prompt 已注入输入框');
}
```

#### 3.3.4 完整工作流

```
用户点击"一键接力"
      │
      ▼
弹出场景选择面板 ──────► 用户选择场景
      │
      ▼
注入摘要 Prompt 到输入框
      │
      ▼
用户确认发送 → Claude 生成摘要
      │
      ▼
脚本检测到摘要回复 → 弹出"保存并跳转"按钮
      │
      ▼
用户点击 → 摘要保存到 GM_setValue
            + 打开新对话页面
            + 自动将摘要粘贴到新对话输入框
```

---

### 3.4 [P1] Prompt 模板快捷面板

**对应痛点：** 指南第二章——结构化 Prompt 可将 6 轮澄清缩减为 1 轮。

#### 3.4.1 功能设计

在 claude.ai 页面**左侧或右侧注入可折叠侧边栏**：

```
┌──────────────────────────┐
│ 📋 Prompt 模板      [◀]  │
├──────────────────────────┤
│ 🔍 搜索模板...           │
├──────────────────────────┤
│ 📁 编程开发               │
│   ├ 代码审查              │
│   ├ Bug 分析              │
│   ├ 架构设计              │
│   └ API 文档生成          │
│ 📁 内容创作               │
│   ├ 博客文章              │
│   ├ 技术文档              │
│   └ 邮件撰写              │
│ 📁 数据分析               │
│   ├ 数据清洗              │
│   └ 报告生成              │
│ 📁 翻译                   │
│   ├ 中英互译              │
│   └ 法律文档翻译          │
│ 📁 自定义模板 ⭐           │
│   ├ [用户创建的模板]       │
│   └ + 新建模板            │
├──────────────────────────┤
│ ⚙️ 设置  📤 导出  📥 导入  │
└──────────────────────────┘
```

#### 3.4.2 模板数据结构

```javascript
const PromptTemplate = {
  id: 'code-review-001',
  name: '代码审查',
  category: '编程开发',
  description: '全面审查代码的安全性、性能和风格',
  // 四段式结构
  sections: {
    instructions: `You are a senior code reviewer. Analyze for:
1. Security vulnerabilities  2. Performance bottlenecks
3. Code style violations.  Respond in Chinese.`,
    context: '项目类型：{{framework}}\n代码规范：{{standard}}\n重点关注：{{focus}}',
    task: '请对以下代码进行全面审查：\n\n{{code}}',
    outputFormat: `按以下结构输出：
## 严重问题（必须修复）
## 建议优化
## 代码亮点
每个问题含：行号、描述、修复建议、修复代码。`
  },
  variables: [
    { key: 'framework', label: '框架', default: 'Next.js' },
    { key: 'standard', label: '规范', default: 'ESLint Recommended' },
    { key: 'focus', label: '关注点', default: '安全性' },
    { key: 'code', label: '代码', type: 'textarea' }
  ],
  tags: ['编程', '审查', '安全'],
  tokenEstimate: 350, // 模板自身的预估 token 数
  isBuiltin: true
};
```

#### 3.4.3 变量填充弹窗

点击模板后弹出变量填充对话框：

```javascript
function showTemplateDialog(template) {
  const overlay = document.createElement('div');
  overlay.innerHTML = `
    <div style="
      position: fixed; inset: 0; background: rgba(0,0,0,0.5);
      z-index: 10001; display: flex; justify-content: center; align-items: center;
    ">
      <div style="
        background: white; border-radius: 16px; padding: 24px;
        width: 560px; max-height: 80vh; overflow-y: auto;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      ">
        <h3 style="margin: 0 0 16px; font-size: 18px;">📋 ${template.name}</h3>
        <p style="color: #666; font-size: 14px; margin-bottom: 20px;">
          ${template.description}
        </p>

        <div id="template-vars">
          ${template.variables.map(v => `
            <div style="margin-bottom: 12px;">
              <label style="display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px;">
                ${v.label}
              </label>
              ${v.type === 'textarea'
                ? `<textarea data-var="${v.key}" rows="6"
                     style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 8px;
                            font-family: monospace; font-size: 13px;"
                     placeholder="${v.default || ''}">${v.default || ''}</textarea>`
                : `<input data-var="${v.key}" type="text" value="${v.default || ''}"
                     style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 8px;"
                   />`
              }
            </div>
          `).join('')}
        </div>

        <div style="display: flex; gap: 8px; margin-top: 20px; justify-content: flex-end;">
          <button onclick="this.closest('[style*=fixed]').remove()"
            style="padding: 8px 16px; border: 1px solid #ddd; border-radius: 8px;
                   background: white; cursor: pointer;">
            取消
          </button>
          <button id="inject-prompt-btn"
            style="padding: 8px 16px; border: none; border-radius: 8px;
                   background: #D97706; color: white; cursor: pointer; font-weight: 600;">
            📝 填入输入框
          </button>
          <button id="copy-prompt-btn"
            style="padding: 8px 16px; border: none; border-radius: 8px;
                   background: #2563EB; color: white; cursor: pointer; font-weight: 600;">
            📋 复制
          </button>
        </div>

        <div style="margin-top: 12px; padding: 8px; background: #F3F4F6; border-radius: 8px;">
          <span style="font-size: 12px; color: #666;">
            预估 Token：<strong>${template.tokenEstimate}</strong>
            （占 200K 窗口的 ${(template.tokenEstimate / 2000).toFixed(1)}%）
          </span>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  // 绑定按钮事件
  overlay.querySelector('#inject-prompt-btn').onclick = () => {
    const prompt = buildPromptFromTemplate(template, overlay);
    injectPromptToInput(prompt);
    overlay.remove();
  };
  overlay.querySelector('#copy-prompt-btn').onclick = () => {
    const prompt = buildPromptFromTemplate(template, overlay);
    navigator.clipboard.writeText(prompt);
    showToast('已复制到剪贴板');
    overlay.remove();
  };
}

function buildPromptFromTemplate(template, container) {
  let result = '';
  const sections = template.sections;
  const vars = {};

  // 收集变量值
  container.querySelectorAll('[data-var]').forEach(el => {
    vars[el.dataset.var] = el.value || el.dataset.default || '';
  });

  // 拼装并替换变量
  for (const [key, content] of Object.entries(sections)) {
    let filled = content;
    for (const [varKey, varVal] of Object.entries(vars)) {
      filled = filled.replaceAll(`{{${varKey}}}`, varVal);
    }
    result += `<${key}>\n${filled}\n</${key}>\n\n`;
  }

  return result.trim();
}
```

---

### 3.5 [P1] 模型 & 功能状态栏

**对应痛点：** 指南第四/六章——模型选错成本差 3-5 倍，MCP 连接器隐性消耗约 5-10K tokens/个。

#### 3.5.1 UI 设计

在 claude.ai 页面**顶部导航栏下方**注入一条信息栏：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 🤖 Sonnet 4.6  │ 🔍 搜索:ON │ 💻 代码:ON │ 🧠 思考:OFF │ 🔌 MCP:2  │
│ 💰 ≈$3/MTok    │ 🆓 免费    │ 🆓 免费    │ +20-50%     │ ≈15K tok  │
└─────────────────────────────────────────────────────────────────────┘
```

#### 3.5.2 状态检测逻辑

```javascript
function detectCurrentState() {
  // 通过 DOM 检测当前模型和功能状态
  // 具体选择器需根据 claude.ai 实际 DOM 结构调整

  return {
    model: detectModel(),        // 解析模型选择器 DOM
    webSearch: detectToggle('search'),
    codeExec: detectToggle('code'),
    thinking: detectToggle('thinking'),
    mcpCount: detectMCPConnectors(),
  };
}

function detectModel() {
  // 方案1：读取模型选择器文本
  const modelSelector = document.querySelector('[data-testid="model-selector"]')
    || document.querySelector('button[class*="model"]');
  if (modelSelector) {
    const text = modelSelector.textContent.toLowerCase();
    if (text.includes('opus')) return { name: 'Opus 4.6', inputCost: 5, outputCost: 25 };
    if (text.includes('haiku')) return { name: 'Haiku 4.5', inputCost: 1, outputCost: 5 };
    return { name: 'Sonnet 4.6', inputCost: 3, outputCost: 15 };
  }

  // 方案2：从拦截的 API 请求体中读取 model 字段
  return lastDetectedModel || { name: 'Sonnet 4.6', inputCost: 3, outputCost: 15 };
}

// 计算当前功能组合的隐性 token 开销
function estimateFeatureOverhead(state) {
  let overhead = 0;
  if (state.mcpCount > 0) overhead += state.mcpCount * 7500; // 每个 MCP 约 5-10K
  // Web 搜索和代码执行在 4.6 模型上免费（2026年2月更新）
  if (state.thinking) overhead *= 1.35; // 思考模式额外 20-50%
  return overhead;
}
```

---

### 3.6 [P1] 额度监控面板

**对应痛点：** 指南第九章——5h 滚动窗口、共享额度池、Pro 用户约 45 条短消息/窗口。

#### 3.6.1 核心功能

```javascript
const QuotaTracker = {
  WINDOW_HOURS: 5,
  ESTIMATES: {
    pro:   { sonnet: 45, opus: 10, haiku: 90 },
    max5:  { sonnet: 225, opus: 50, haiku: 450 },
    max20: { sonnet: 900, opus: 200, haiku: 1800 }
  },

  // 记录每次消息发送
  recordMessage(model) {
    const records = GM_getValue('quota_records', []);
    records.push({
      time: Date.now(),
      model: model,
    });
    // 只保留最近 48 小时的记录
    const cutoff = Date.now() - 48 * 60 * 60 * 1000;
    const filtered = records.filter(r => r.time > cutoff);
    GM_setValue('quota_records', filtered);
    return filtered;
  },

  // 计算当前 5h 窗口内的使用量
  getCurrentWindowUsage() {
    const records = GM_getValue('quota_records', []);
    const windowStart = Date.now() - this.WINDOW_HOURS * 60 * 60 * 1000;
    return records.filter(r => r.time > windowStart);
  },

  // 预估剩余消息数
  estimateRemaining(plan = 'pro') {
    const usage = this.getCurrentWindowUsage();
    const limits = this.ESTIMATES[plan];

    // 按模型加权计算（Opus 消耗约 Sonnet 的 3-5 倍）
    const weightedUsage = usage.reduce((sum, r) => {
      const weight = r.model === 'opus' ? 4.5 : r.model === 'haiku' ? 0.5 : 1;
      return sum + weight;
    }, 0);

    const remaining = Math.max(0, limits.sonnet - weightedUsage);
    return Math.round(remaining);
  },

  // 计算窗口重置时间
  getNextReset() {
    const records = GM_getValue('quota_records', []);
    const windowStart = Date.now() - this.WINDOW_HOURS * 60 * 60 * 1000;
    const windowRecords = records.filter(r => r.time > windowStart);

    if (windowRecords.length === 0) return null;

    const oldestInWindow = Math.min(...windowRecords.map(r => r.time));
    return new Date(oldestInWindow + this.WINDOW_HOURS * 60 * 60 * 1000);
  },

  // 获取本周总使用量（检测周限制）
  getWeeklyUsage() {
    const records = GM_getValue('quota_records', []);
    const weekStart = getStartOfWeek();
    return records.filter(r => r.time > weekStart.getTime());
  }
};
```

#### 3.6.2 UI 面板

在页面右上角注入可展开的额度面板：

```
┌─────────────────────────────────────┐
│ 📊 额度监控                    [▼]  │
├─────────────────────────────────────┤
│                                     │
│  ⏱️ 窗口重置倒计时                   │
│     02:37:14                        │
│                                     │
│  📬 当前窗口 (Pro)                   │
│     已用: 23 / ~45 条               │
│     ████████████░░░░░░░░  51%       │
│     剩余约 22 条 (Sonnet 当量)       │
│                                     │
│  📅 本周累计                         │
│     周一 ██████████ 42              │
│     周二 ████████   35              │
│     周三 ████████████████ 67 ← 今天  │
│                                     │
│  💡 省额度建议：                      │
│     · 当前使用 Opus，切到 Sonnet     │
│       可多发约 35 条消息             │
│     · 非高峰时段(夜间)额度更宽松     │
│                                     │
│  ⚙️ [Pro ▼] 切换计划                │
└─────────────────────────────────────┘
```

---

### 3.7 [P2] 对话导出器

#### 3.7.1 核心功能

```javascript
function exportConversation(format = 'markdown') {
  // 从 DOM 中提取对话内容
  const messages = [];
  const messageElements = document.querySelectorAll('[class*="message"]');

  messageElements.forEach(el => {
    const role = el.querySelector('[class*="user"]') ? 'user' : 'assistant';
    const content = el.querySelector('[class*="content"]')?.textContent || '';
    messages.push({ role, content });
  });

  // 根据格式导出
  let output;
  const title = document.title || 'Claude Conversation';
  const timestamp = new Date().toISOString().slice(0, 10);

  if (format === 'markdown') {
    output = `# ${title}\n_导出时间: ${timestamp}_\n\n`;
    output += messages.map(m =>
      `## ${m.role === 'user' ? '👤 用户' : '🤖 Claude'}\n\n${m.content}\n`
    ).join('\n---\n\n');
  } else if (format === 'json') {
    output = JSON.stringify({ title, exportedAt: timestamp, messages }, null, 2);
  }

  // 下载文件
  downloadFile(output, `claude-${timestamp}.${format === 'json' ? 'json' : 'md'}`);
}

function downloadFile(content, filename) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
```

---

### 3.8 [P2] 快捷键增强

```javascript
const SHORTCUTS = {
  'Alt+N': { action: 'newChat',     desc: '新建对话' },
  'Alt+R': { action: 'relay',       desc: '一键接力' },
  'Alt+T': { action: 'toggleToken', desc: '显示/隐藏 Token 面板' },
  'Alt+E': { action: 'export',      desc: '导出对话' },
  'Alt+P': { action: 'promptPanel', desc: '打开 Prompt 面板' },
  'Alt+1': { action: 'modelSonnet', desc: '切换到 Sonnet' },
  'Alt+2': { action: 'modelOpus',   desc: '切换到 Opus' },
  'Alt+3': { action: 'modelHaiku',  desc: '切换到 Haiku' },
};

document.addEventListener('keydown', (e) => {
  const key = [
    e.altKey && 'Alt',
    e.ctrlKey && 'Ctrl',
    e.shiftKey && 'Shift',
    e.key.toUpperCase()
  ].filter(Boolean).join('+');

  const shortcut = SHORTCUTS[key];
  if (shortcut) {
    e.preventDefault();
    executeAction(shortcut.action);
  }
});

function executeAction(action) {
  switch(action) {
    case 'newChat':
      window.location.href = 'https://claude.ai/new';
      break;
    case 'relay':
      triggerRelay();
      break;
    case 'toggleToken':
      toggleTokenPanel();
      break;
    case 'export':
      exportConversation('markdown');
      break;
    case 'promptPanel':
      togglePromptSidebar();
      break;
    // ...
  }
}
```

---

## 四、公共基础设施

### 4.1 DOM 选择器适配层

Claude.ai 的 DOM 结构可能随版本更新变化，需要一个**选择器适配层**做隔离：

```javascript
const Selectors = {
  // 集中管理所有 DOM 选择器，便于维护更新
  chatInput: () =>
    document.querySelector('[contenteditable="true"].ProseMirror')
    || document.querySelector('div[contenteditable="true"]')
    || document.querySelector('textarea'),

  messageContainer: () =>
    document.querySelector('[class*="conversation-content"]')
    || document.querySelector('main [class*="react-scroll"]')
    || document.querySelector('main'),

  userMessages: () =>
    document.querySelectorAll('[data-testid*="user"]')
    || document.querySelectorAll('[class*="human-message"]'),

  modelSelector: () =>
    document.querySelector('[data-testid="model-selector"]')
    || document.querySelector('button[aria-label*="model"]'),

  sendButton: () =>
    document.querySelector('[data-testid="send-button"]')
    || document.querySelector('button[aria-label="Send"]'),

  newChatButton: () =>
    document.querySelector('a[href="/new"]')
    || document.querySelector('[data-testid="new-chat"]'),

  // 版本检测：用于判断 DOM 结构是否变化
  _version: '2026-03',
  validate() {
    const critical = ['chatInput', 'messageContainer'];
    const missing = critical.filter(key => !this[key]());
    if (missing.length > 0) {
      console.warn(`[Claude Enhancer] DOM 选择器失效: ${missing.join(', ')}，可能需要更新脚本`);
      GM_notification({
        title: 'Claude Enhancer',
        text: '部分功能可能因页面更新而失效，请检查脚本更新',
        timeout: 5000
      });
    }
    return missing.length === 0;
  }
};
```

### 4.2 通用 UI 工具

```javascript
// Toast 提示
function showToast(message, duration = 3000) {
  const toast = document.createElement('div');
  toast.textContent = message;
  Object.assign(toast.style, {
    position: 'fixed', bottom: '24px', right: '24px', zIndex: '10001',
    padding: '12px 20px', borderRadius: '10px', fontSize: '14px',
    background: '#1F2937', color: '#F9FAFB',
    boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
    transition: 'opacity 0.3s', opacity: '0'
  });
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.style.opacity = '1');
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// 注入全局样式
function injectStyles() {
  GM_addStyle(`
    .ce-panel {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 14px;
      line-height: 1.5;
    }
    .ce-panel * { box-sizing: border-box; }
    .ce-btn {
      padding: 6px 12px; border-radius: 8px; border: none;
      cursor: pointer; font-size: 13px; transition: all 0.15s;
    }
    .ce-btn:hover { filter: brightness(0.9); }
    .ce-btn-primary { background: #D97706; color: white; }
    .ce-btn-secondary { background: #E5E7EB; color: #374151; }
    .ce-badge { 
      display: inline-flex; align-items: center; gap: 4px;
      padding: 2px 8px; border-radius: 12px; font-size: 12px; 
    }
    .ce-progress-bar {
      height: 8px; border-radius: 4px; background: #E5E7EB; overflow: hidden;
    }
    .ce-progress-fill {
      height: 100%; border-radius: 4px; transition: width 0.5s ease;
    }
  `);
}
```

### 4.3 SPA 路由监听

Claude.ai 是 SPA（单页应用），切换对话时页面不刷新，需要监听路由变化：

```javascript
function watchRouteChanges(callback) {
  // 方案1: 监听 URL 变化
  let lastUrl = location.href;
  const urlObserver = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      callback(lastUrl);
    }
  });
  urlObserver.observe(document.body, { childList: true, subtree: true });

  // 方案2: 拦截 history API
  const originalPushState = history.pushState;
  const originalReplaceState = history.replaceState;

  history.pushState = function(...args) {
    originalPushState.apply(this, args);
    callback(location.href);
  };
  history.replaceState = function(...args) {
    originalReplaceState.apply(this, args);
    callback(location.href);
  };

  window.addEventListener('popstate', () => callback(location.href));
}

// 使用示例
watchRouteChanges((url) => {
  if (url.includes('/chat/')) {
    // 进入对话页面，初始化对话相关模块
    initConversationModules();
  }
});
```

---

## 五、模块化打包与分发

### 5.1 文件结构

```
claude-enhancer/
├── src/
│   ├── core/
│   │   ├── selectors.js       # DOM 选择器适配层
│   │   ├── fetch-hook.js      # fetch 拦截器
│   │   ├── router.js          # SPA 路由监听
│   │   ├── storage.js         # GM_* 存储封装
│   │   └── ui-utils.js        # 通用 UI 工具
│   ├── modules/
│   │   ├── token-counter.js   # P0: Token 计数器
│   │   ├── turn-warning.js    # P0: 对话轮次警告
│   │   ├── context-relay.js   # P0: 上下文接力
│   │   ├── prompt-panel.js    # P1: Prompt 模板面板
│   │   ├── status-bar.js      # P1: 模型状态栏
│   │   ├── quota-tracker.js   # P1: 额度监控
│   │   ├── exporter.js        # P2: 对话导出
│   │   └── shortcuts.js       # P2: 快捷键
│   ├── data/
│   │   ├── prompt-templates.js # 预置 Prompt 模板库
│   │   └── relay-templates.js  # 接力摘要模板库
│   └── main.js                 # 入口：初始化所有模块
├── dist/
│   └── claude-enhancer.user.js # 打包后的单文件脚本
├── build.js                    # 构建脚本（合并为单文件）
└── README.md
```

### 5.2 构建流程

```javascript
// build.js - 将多模块合并为单个 .user.js 文件
const fs = require('fs');
const path = require('path');

const HEADER = `// ==UserScript==
// @name         Claude.ai Enhancer (全功能增强)
// @namespace    https://claude.ai/
// @version      1.0.0
// @description  Token 计数 | 对话接力 | Prompt 模板 | 额度监控 | 快捷键
// @author       Your Name
// @match        https://claude.ai/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_deleteValue
// @grant        GM_addStyle
// @grant        GM_registerMenuCommand
// @grant        GM_notification
// @grant        GM_setClipboard
// @run-at       document-idle
// @noframes
// @license      MIT
// @downloadURL  https://your-host.com/claude-enhancer.user.js
// @updateURL    https://your-host.com/claude-enhancer.user.js
// ==/UserScript==`;

// 按依赖顺序合并文件
const modules = [
  'src/core/selectors.js',
  'src/core/storage.js',
  'src/core/fetch-hook.js',
  'src/core/router.js',
  'src/core/ui-utils.js',
  'src/data/prompt-templates.js',
  'src/data/relay-templates.js',
  'src/modules/token-counter.js',
  'src/modules/turn-warning.js',
  'src/modules/context-relay.js',
  'src/modules/prompt-panel.js',
  'src/modules/status-bar.js',
  'src/modules/quota-tracker.js',
  'src/modules/exporter.js',
  'src/modules/shortcuts.js',
  'src/main.js'
];

let output = HEADER + '\n\n(function() {\n  "use strict";\n\n';
for (const file of modules) {
  const content = fs.readFileSync(path.join(__dirname, file), 'utf-8');
  output += `  // ========== ${file} ==========\n`;
  output += content + '\n\n';
}
output += '})();';

fs.writeFileSync('dist/claude-enhancer.user.js', output);
console.log('Build complete: dist/claude-enhancer.user.js');
```

### 5.3 分发渠道

| 渠道 | 说明 |
|------|------|
| **GreasyFork** | 最大的用户脚本分发平台，支持自动更新 |
| **GitHub Releases** | 开源分发，配合 `@updateURL` 实现自动更新 |
| **直接安装** | 将 `.user.js` 文件拖入浏览器安装 |

---

## 六、开发路线图

```
Phase 1 (Week 1-2): 核心引擎
├── 搭建项目骨架 + 构建流程
├── 实现 DOM 选择器适配层 + SPA 路由监听
├── 实现 fetch hook 拦截器
├── P0: Token 实时计数器（含 UI 浮窗）
└── P0: 对话轮次警告器

Phase 2 (Week 3-4): 接力 + 模板
├── P0: 上下文接力助手（含 5 套场景模板）
├── P1: Prompt 模板快捷面板（含侧边栏 UI）
└── 预置模板库填充（10+ 常用场景）

Phase 3 (Week 5-6): 监控 + 状态
├── P1: 模型 & 功能状态栏
├── P1: 额度监控面板（含 5h 窗口倒计时）
└── 数据导入/导出功能

Phase 4 (Week 7-8): 增强 + 发布
├── P2: 对话导出器 + 快捷键系统
├── 全模块联调 + 性能优化
├── DOM 选择器兼容性测试
└── GreasyFork / GitHub 发布
```

---

## 七、关键风险与应对

| 风险 | 影响 | 应对策略 |
|------|------|---------|
| **claude.ai DOM 结构更新** | 选择器失效，UI 注入失败 | 选择器适配层集中管理 + 自动检测 + 版本号标记 |
| **fetch API 变化** | Token 统计失效 | SSE 解析做多格式兼容，降级为纯 DOM 统计 |
| **CSP 策略限制** | 样式/脚本注入被阻止 | 使用 `GM_addStyle`（绕过 CSP）+ `unsafeWindow` |
| **性能影响** | 页面卡顿 | SSE 拦截用 TransformStream 异步处理，DOM 观察防抖 |
| **Anthropic 主动阻止** | 脚本被检测封禁 | 保持只读行为（不修改请求），不触及反作弊 |
| **Token 估算不准确** | 用户决策偏差 | UI 明确标注"估算值"，提供误差范围（±15%） |

---

## 八、合规性说明

本方案所有脚本**仅在客户端浏览器层面运行**，具体行为边界如下：

- ✅ 读取页面 DOM 内容（对话文本、UI 状态）
- ✅ 拦截并分析网络请求/响应（不修改内容）
- ✅ 在页面上叠加 UI 元素（浮窗、侧边栏、状态栏）
- ✅ 本地存储使用数据（GM_setValue / IndexedDB）
- ❌ **不修改**发送给 Claude 的请求内容
- ❌ **不绕过**任何速率限制或付费墙
- ❌ **不自动发送**消息（所有发送由用户手动触发）
- ❌ **不采集或上传**用户数据到第三方
