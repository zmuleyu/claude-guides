# 复杂多步骤浏览器自动化深度研究：Playwright CLI 与 MCP

## 一、核心问题

当需要执行注册流程测试、端到端用户旅程测试、批量数据提取等**多步骤**浏览器自动化任务时，如何选择和配置最优方案？

本文聚焦两个主角：**Playwright CLI**（2026 年新方案）和 **Playwright MCP**（MCP 协议方案），二者均由 Microsoft 维护，共享同一个 Playwright 引擎，但架构设计理念截然不同。

---

## 二、架构差异：状态存放在哪里？

这是理解两者区别的核心问题。

### Playwright MCP：状态在模型上下文中

```
AI Agent ←→ MCP Server ←→ Playwright ←→ 浏览器
            ↑
       每次操作返回完整的
       可访问性树 + 控制台日志
       → 全部注入 LLM 上下文窗口
```

MCP 是一个持久化的 JSON 协议服务器。AI 客户端发送高级动作指令（如 `browser_click`），MCP 服务器将其转换为 Playwright 命令执行，然后返回**结构化的可访问性快照**（accessibility tree）、控制台消息和操作结果——全部注入模型的上下文窗口。

**优势**：AI 能实时"看到"完整的页面结构，适合探索性分析。

**代价**：每次交互都向上下文注入大量 token。

### Playwright CLI：状态在磁盘上

```
AI Agent → Shell 命令 → playwright-cli → 浏览器
                            ↓
                     快照保存为 YAML 文件
                     截图保存为 PNG 文件
                     → 仅返回文件路径给 Agent
                     → Agent 按需读取
```

CLI 是一系列简洁的 shell 命令。Agent 通过 Bash 工具调用它，就像运行 `git` 或 `npm` 一样。页面状态保存到磁盘文件，Agent 只在需要时才读取。

**优势**：上下文窗口保持干净，长流程不会退化。

**代价**：需要文件系统访问权限。

---

## 三、Token 消耗对比

这是决定性的差距。Microsoft 官方基准测试数据：

| 指标 | Playwright MCP | Playwright CLI | 差距 |
|------|---------------|----------------|------|
| **典型任务 Token 消耗** | ~114,000 tokens | ~27,000 tokens | **4 倍** |
| 长流程衰减 | 15 步后性能明显下降 | 50+ 步仍保持稳定 | 差距随步骤增加而扩大 |
| 截图处理 | 图片二进制注入上下文 | 保存到磁盘，返回文件路径 | CLI 几乎零 token |
| 页面快照 | 完整可访问性树内联返回 | 保存为 YAML 文件，按需读取 | CLI 仅一行路径 |

**关键洞察**：对于多步骤自动化（30-50 步），MCP 的上下文窗口可能被快速填满，导致推理能力退化和 token 成本飙升。CLI 的优势在长流程中呈指数级放大。

---

## 四、Playwright CLI 完整指南

### 4.1 安装

```bash
# 全局安装
npm install -g @playwright/cli

# 安装 Playwright Skills（关键步骤！）
npx playwright-cli install

# 验证安装
playwright-cli --help
```

> **重要**：`install` 命令会同时安装 Skills 文件——这是结构化的知识文件，教会 Agent 正确使用 CLI 命令。跳过此步骤会导致 Agent 猜测命令语法，浪费 token。

### 4.2 核心命令集

```bash
# 浏览器管理
playwright-cli open https://example.com          # 打开页面（默认无头模式）
playwright-cli open https://example.com --headed  # 可视化模式
playwright-cli close                              # 关闭浏览器
playwright-cli close-all                          # 关闭所有浏览器

# 页面交互
playwright-cli click e21        # 点击元素（e21 是快照中的元素引用）
playwright-cli fill e15 "value" # 填写输入框
playwright-cli type "Hello"     # 键入文本
playwright-cli press Enter      # 按键
playwright-cli check e21        # 勾选复选框

# 页面感知
playwright-cli snapshot                    # 获取页面快照（保存为 YAML）
playwright-cli snapshot --filename=page.yaml  # 指定文件名
playwright-cli screenshot                  # 截图（保存为 PNG）

# 状态管理
playwright-cli state-save auth.json        # 保存登录状态
playwright-cli state-load auth.json        # 恢复登录状态

# Cookie 操作
playwright-cli cookie-list
playwright-cli cookie-set session_id abc123 --domain=example.com --httpOnly --secure
playwright-cli cookie-delete session_id
playwright-cli cookie-clear

# LocalStorage / SessionStorage
playwright-cli localstorage-get theme
playwright-cli localstorage-set theme dark
playwright-cli sessionstorage-set step 3

# 网络拦截（Mock）
playwright-cli route "**/*.jpg" --status=404
playwright-cli route "https://api.example.com/**" --body='{"mock": true}'
playwright-cli route-list
playwright-cli unroute

# 多会话管理
playwright-cli -s=login open https://example.com   # 命名会话
playwright-cli -s=login click e5
playwright-cli list                                  # 列出所有会话
playwright-cli -s=login close
playwright-cli -s=login delete-data                  # 清除会话数据

# 可视化仪表盘
playwright-cli show   # 打开会话网格，实时预览所有活跃浏览器
```

### 4.3 与 Claude Code 集成

**方式一：直接使用 Bash 工具**

Claude Code 本身就有 Bash 工具，可以直接调用 playwright-cli 命令，无需额外配置。只需告诉 Claude：

> "用 playwright-cli 测试 https://demo.playwright.dev/todomvc 的添加待办事项流程。先查看 playwright-cli --help 了解可用命令。"

**方式二：安装 Playwright Skills**

Skills 是结构化的 markdown 知识库，教会 AI Agent 正确的自动化模式。

```bash
# 安装微软官方 CLI Skill
npx skills add https://github.com/microsoft/playwright-cli --skill playwright-cli

# 或安装社区增强 Skill 套件（70+ 指南）
npx skills add testdino-hq/playwright-skill/core           # 46 指南：定位器、断言、认证、Mock、调试
npx skills add testdino-hq/playwright-skill/playwright-cli  # 11 指南：CLI 浏览器自动化
npx skills add testdino-hq/playwright-skill/ci              # 9 指南：CI/CD 流水线
npx skills add testdino-hq/playwright-skill/pom             # 2 指南：Page Object Model
npx skills add testdino-hq/playwright-skill/migration       # 2 指南：从 Cypress/Selenium 迁移
```

安装后 Skills 文件位于项目目录中，Claude Code 会自动读取并在生成测试时参考。

### 4.4 多步骤自动化实战示例

**示例：电商网站注册 → 登录 → 添加商品 → 结账**

```bash
# 第 1 步：打开网站
playwright-cli open https://shop.example.com --headed

# 第 2 步：获取页面快照，识别元素
playwright-cli snapshot
# → 保存为 .playwright-cli/page-2026-03-04T10-00-00.yaml
# Agent 读取 YAML，找到注册按钮 e12

# 第 3 步：进入注册页面
playwright-cli click e12

# 第 4 步：再次快照，识别表单字段
playwright-cli snapshot
# Agent 识别出 e5=用户名, e8=邮箱, e11=密码, e15=提交按钮

# 第 5 步：填写注册表单
playwright-cli fill e5 "testuser2026"
playwright-cli fill e8 "test@example.com"
playwright-cli fill e11 "SecureP@ss123"
playwright-cli click e15

# 第 6 步：验证注册成功
playwright-cli snapshot
# Agent 检查是否出现欢迎页面

# 第 7 步：保存登录状态（后续测试可复用）
playwright-cli state-save auth.json

# 第 8 步：搜索商品
playwright-cli snapshot
playwright-cli fill e3 "iPhone 16"
playwright-cli press Enter

# 第 9 步：添加到购物车
playwright-cli snapshot
playwright-cli click e28  # "加入购物车" 按钮

# 第 10 步：进入结账
playwright-cli click e40  # "去结算" 按钮
playwright-cli snapshot
playwright-cli screenshot  # 截图保留结账页面证据

# 第 11 步：填写收货地址
playwright-cli fill e55 "北京市海淀区"
playwright-cli fill e58 "张三"
playwright-cli fill e61 "13800138000"

# 第 12 步：提交订单
playwright-cli click e70
playwright-cli snapshot
# Agent 验证订单确认页面
```

在整个 12 步流程中，每一步 CLI 只返回一行文件路径或简短确认，Agent 的上下文窗口始终保持干净。

---

## 五、Playwright MCP 完整指南

### 5.1 安装配置

**Claude Code 中添加（推荐）**：

```bash
claude mcp add playwright -s user -- npx -y @playwright/mcp@latest
```

运行后 Claude Code 会自动将配置持久化到 `~/.claude.json`。

**手动配置 `~/.claude.json`**：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
```

**Claude Desktop 配置 `claude_desktop_config.json`**：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
```

> 修改配置后必须完全关闭并重启应用（Windows 上需在任务管理器中结束进程），否则配置不会生效。

### 5.2 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--browser` | 浏览器引擎：chrome / firefox / webkit / msedge | chromium |
| `--caps` | 启用额外能力：vision / pdf / devtools | 无 |
| `--allowed-origins` | 允许访问的域名白名单 | 全部允许 |
| `--blocked-origins` | 禁止访问的域名黑名单 | 无 |
| `--cdp-endpoint` | 连接到已运行的浏览器实例 | 无 |
| `--user-data-dir` | 浏览器用户数据目录（持久化登录状态） | 无 |
| `--extension` | 使用 Playwright MCP Bridge 扩展连接已有 Chrome | 关闭 |
| `--codegen` | 代码生成语言：typescript / none | typescript |
| `--console-level` | 控制台日志级别：error / warning / info / debug | 无 |

### 5.3 MCP 提供的工具列表

在 Claude Code 中运行 `/mcp` → 选择 `playwright`，可查看所有可用工具：

- `browser_navigate` — 导航到 URL
- `browser_click` — 点击元素
- `browser_type` — 在元素中输入文本
- `browser_fill` — 填充表单字段
- `browser_select_option` — 选择下拉选项
- `browser_snapshot` — 获取页面可访问性快照
- `browser_screenshot` — 截图
- `browser_console_messages` — 获取控制台消息
- `browser_wait` — 等待条件满足
- `browser_press_key` — 按键
- `browser_go_back` / `browser_go_forward` — 前进 / 后退
- `browser_tab_*` — 标签页管理
- `browser_file_upload` — 文件上传

### 5.4 认证处理

MCP 使用可见浏览器窗口时，认证非常简单：

1. 让 Claude 导航到登录页面
2. 用户在浏览器中手动登录
3. 告诉 Claude "我已登录，继续下一步"
4. Cookie 会在整个会话期间保持有效

也可以使用 `--user-data-dir` 参数保存浏览器配置文件，在会话间持久化登录状态。

---

## 六、混合工作流（最佳实践）

经验丰富的团队通常采用**三阶段混合策略**：

### 阶段 1：探索（用 MCP）

使用 MCP 让 Agent 了解应用结构，识别可测试的用户流程。每个页面区域通常只需 8-10 步操作，MCP 的上下文成本在可控范围内。

```
"用 Playwright MCP 打开 https://shop.example.com，
 探索整个注册和购物流程，列出所有关键用户路径。"
```

### 阶段 2：执行（用 CLI）

具体的测试执行可能涉及 30-50 步操作。此时切换到 CLI 以保持 token 效率。

```
"用 playwright-cli 执行完整的用户注册 → 搜索商品 → 加入购物车 → 结账流程，
 每一步截图保存到 ./screenshots/ 目录。"
```

### 阶段 3：固化（不用 AI）

对于稳定的回归测试，让 Agent 在 CLI 会话中生成 `.spec.ts` 测试文件。之后直接用 `npx playwright test` 确定性地运行，不再消耗 AI token。

```bash
# Agent 生成的测试文件
npx playwright test tests/checkout-flow.spec.ts
```

---

## 七、决策树

```
你的 Agent 有文件系统访问权限吗？
├── 是（Claude Code / Copilot / Cursor）
│   ├── 短期探索性任务（< 10 步）→ MCP 或 CLI 均可
│   ├── 长流程多步骤任务（> 15 步）→ CLI（必选）
│   └── 混合策略 → 探索用 MCP，执行用 CLI
└── 否（Claude Desktop / 沙盒环境 / 自定义聊天界面）
    └── MCP（唯一选择）
```

**一句话总结**：如果只装一个，装 Playwright CLI + Skills。它兼顾 token 效率和专业能力，是编程 Agent 的最佳默认选择。MCP 作为调试和沙盒环境的备选方案保留。

---

## 八、常见问题与陷阱

### 8.1 Shadow DOM 盲区

两种工具都基于可访问性树工作。使用 Web Components 的现代设计系统中，Shadow DOM 内的元素可能完全不可见。这是 2026 年 AI 测试中最被忽视的问题。

### 8.2 Bot 检测

两种工具都无法绕过 CAPTCHA 或 WAF 挑战。如果测试环境有严格的防机器人保护，需要单独处理基础设施层面的问题。

### 8.3 上下文累积

即使 CLI 的单步成本很低，200 步的会话仍然会累积大量对话历史。需要准备策略：摘要压缩、滑动窗口、检查点重置等。CLI 提供了更大的空间余量，但没有消除根本限制。

### 8.4 版本兼容性

Playwright MCP 最常见的问题是版本不匹配。如果 `@latest` 出错，指定一个已知可用的版本：

```bash
npx -y @playwright/mcp@1.56.0
```

### 8.5 浏览器安装失败

让 Claude 自动安装 Playwright 浏览器经常失败（需要 sudo 权限）。务必手动预装：

```bash
npx playwright install chromium
# 或安装全部浏览器
npx playwright install
```

---

## 九、Playwright v1.56+ 内置测试 Agent

自 Playwright v1.56 起，内置了三个测试 Agent：

| Agent | 功能 | 用途 |
|-------|------|------|
| **Planner** | 分析应用结构，规划测试策略 | 自动识别应测试的用户流程 |
| **Generator** | 根据计划生成测试代码 | 自动编写 `.spec.ts` 测试文件 |
| **Healer** | 分析失败，修复定位器和断言 | 自动修复因 UI 变更导致的测试失败 |

这些 Agent 不是独立的二进制文件，而是一组指令和 MCP 工具定义的集合，由你的 AI 编码助手（Claude Code / Copilot）代为执行。它们需要 LLM 后端（OpenAI / Anthropic 等 API），因此要将 API 访问和 token 成本纳入规划。

---

## 十、参考资源

- Microsoft Playwright CLI（官方仓库）：https://github.com/microsoft/playwright-cli
- Microsoft Playwright MCP（官方仓库）：https://github.com/microsoft/playwright-mcp
- Playwright CLI npm 包：https://www.npmjs.com/package/@playwright/cli
- Playwright Skill 知识库：https://github.com/testdino-hq/playwright-skill
- Simon Willison 的 Playwright MCP + Claude Code 教程：https://til.simonwillison.net/claude-code/playwright-mcp-claude-code
- Token 消耗对比实测：https://scrolltest.medium.com/playwright-mcp-burns-114k-tokens-per-test-the-new-cli-uses-27k

---

*报告生成日期：2026年3月4日*
