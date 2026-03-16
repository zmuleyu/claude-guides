# 通过插件使用 Claude 网页版：浏览器自动操作研究报告

## 一、概述

浏览器自动操作 Claude 网页版目前有两大方向：一是 **Anthropic 官方推出的 Claude in Chrome 扩展**，让 Claude AI 直接在浏览器中执行操作；二是通过 **第三方浏览器自动化工具**（如 Playwright、Puppeteer 等）配合 MCP 协议，让 AI 代理控制浏览器完成各类任务。以下逐一展开。

---

## 二、Claude in Chrome（官方浏览器扩展）

### 2.1 产品定位

Claude in Chrome 是 Anthropic 官方推出的 Chrome 浏览器扩展程序，于 2025 年 8 月以研究预览形式启动，最初仅面向 1,000 名 Max 用户测试。2025 年 11 月扩展至所有 Max 订阅用户，2025 年 12 月 18 日正式面向所有付费计划开放（包括 Pro、Team、Enterprise）。

该扩展将 Claude AI 以**侧边栏**的形式嵌入浏览器中，能够看到用户当前页面内容，并执行点击、填写表单、导航等实际操作。

### 2.2 核心能力

| 能力 | 说明 |
|------|------|
| **页面感知** | Claude 能看到浏览器页面，识别按钮、表单、导航菜单等 UI 元素 |
| **自动操作** | 点击按钮、填写表单、导航链接、滚动页面 |
| **多标签页管理** | 将标签拖入 Claude 的标签组，可同时查看和操作多个页面 |
| **快捷指令（Shortcuts）** | 保存常用 Prompt 为 /斜杠命令，一键复用工作流 |
| **定时任务** | 支持每日、每周、每月或每年自动运行保存的快捷指令 |
| **截图与图片上传** | 截取屏幕区域或上传图片，以视觉方式与 Claude 交互 |
| **控制台读取** | 读取浏览器控制台输出，包括错误、网络请求和 DOM 状态 |
| **会话录制** | 将浏览器交互录制为 GIF |

### 2.3 安装与配置

1. **前提条件**：需要 Claude 付费订阅（Pro / Max / Team / Enterprise）
2. **浏览器要求**：Google Chrome 或 Microsoft Edge（不支持 Brave、Arc 等其他 Chromium 浏览器）
3. **安装步骤**：
   - 前往 Chrome Web Store 搜索 "Claude"
   - 点击 "Add to Chrome" 安装
   - 点击工具栏拼图图标，将 Claude 固定到工具栏
   - 使用 Claude 账号登录
   - 授予必要的页面访问权限

### 2.4 权限模式

扩展提供三种权限控制模式：

- **Ask before acting（默认）**：Claude 在每个操作前请求批准，用户拥有完全控制权
- **Follow Claude's Plan**：用户审批 Claude 的整体方案后，Claude 在批准范围内自主执行；遇到高风险操作（如购买、删除数据）仍会请求确认
- **Skip All Permissions**：Claude 无需询问直接操作，需要用户密切监督

此外，用户可以对特定网站设置"始终允许"或"拒绝"策略，在 Settings → Permissions 中管理。

### 2.5 典型使用场景

- **邮件管理**：扫描收件箱，识别营销邮件和通知，批量归档
- **日历协调**：检查日程、预订会议室、提醒冲突
- **表单填写**：重复性的费用报销、供应商申请等
- **网页研究**：访问竞争对手网站提取定价信息
- **数据提取**：从仪表盘提取数据并生成摘要
- **文件整理**：整理 Google Drive 文件夹结构

### 2.6 安全风险与注意事项

Anthropic 特别指出了**提示注入（Prompt Injection）**风险：恶意网站可能在页面中隐藏指令，试图诱骗 Claude 执行未经授权的操作。在未加防护的测试中，对抗性提示注入的攻击成功率为 23.6%（123 个测试用例，29 种攻击场景）。

**安全建议**：
- 从信任的网站和熟悉的工作流开始使用
- 避免金融交易、密码管理或涉及敏感数据的操作
- 如果 Claude 行为异常，立即暂停并检查
- 使用 "Ask before acting" 模式作为默认

### 2.7 与其他产品的集成

| 集成对象 | 工作方式 |
|---------|---------|
| **Claude Code** | 在终端运行 `claude --chrome`，Claude Code 可直接控制浏览器进行测试、调试、数据提取。通过 Chrome 的 Native Messaging API 通信 |
| **Claude Desktop** | 桌面应用中启用 Claude in Chrome 连接器，可在桌面端发起任务并在浏览器中执行 |
| **Cowork** | Chrome 负责网页研究和数据采集，Cowork 将结果转化为 Excel 表格、PPT 演示文稿、格式化报告 |

### 2.8 局限性

- 仅支持 Chrome 和 Edge，不支持其他浏览器
- 使用 Haiku 4.5 模型（非 Sonnet 或 Opus），在复杂推理上有局限
- 不具备 claude.ai 的 Projects、MCP 工具连接或跨会话记忆
- 不能访问金融服务、成人内容或盗版内容网站
- 同一任务每次执行可能有不同结果

---

## 三、Claude Code + Chrome 集成（开发者方向）

### 3.1 工作原理

Claude Code 通过 Claude in Chrome 扩展与浏览器通信，扩展使用 Chrome 的 **Native Messaging API** 接收来自终端的命令并在浏览器中执行。

这套架构让开发者可以：在终端编写代码 → 在浏览器中实时测试 → 读取控制台错误 → 回到终端修复代码，全程无需切换上下文。

### 3.2 使用方式

```bash
# 启动时开启 Chrome 集成
claude --chrome

# 在已有会话中开启
/chrome

# 查看可用的浏览器工具
/mcp → 选择 claude-in-chrome
```

### 3.3 典型工作流

**测试 Web 应用**：
> "我刚更新了登录表单验证。能打开 localhost:3000，用无效数据提交表单，检查错误信息是否正确显示吗？"

**调试控制台错误**：
> "打开仪表盘页面，检查页面加载时控制台有没有错误。"

**数据提取**：
> "打开竞品网站，提取他们的定价信息并整理成 JSON。"

---

## 四、第三方浏览器自动化方案（MCP 生态）

除了官方扩展，开发者生态中已涌现多种通过 MCP（Model Context Protocol）连接 AI 与浏览器的自动化方案。

### 4.1 四大主流方案对比

| 方案 | 开发者 | 特点 | Token 消耗 | 适用场景 |
|------|--------|------|-----------|---------|
| **Agent Browser** | Vercel | 最轻量，启动快 | 最低 | 简单浏览、截图、查看内容 |
| **Playwright CLI** | Microsoft | 2026 年新方案，Token 效率极高 | 低（比 MCP 低 4-100 倍） | 多步骤流程测试、需要 Shell 权限的场景 |
| **Playwright MCP** | Microsoft | 基于可访问性快照，稳定可靠 | 中等 | 沙盒环境、无 Shell 权限的场景 |
| **DevTools MCP** | Google | 直接使用 Chrome DevTools 协议 | 中等 | 性能分析、DOM 调试 |

### 4.2 Puppeteer MCP

Puppeteer 是 Google 开发的 Node.js 库，通过 DevTools Protocol 控制 Chrome。配合 MCP Server 后可直接在 Claude Code 中使用：

```bash
# 一键安装
claude mcp add puppeteer -s user -- npx -y @modelcontextprotocol/server-puppeteer

# 或在配置文件中添加
{
  "mcpServers": {
    "puppeteer": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
    }
  }
}
```

安装后，可以用自然语言指令让 Claude 执行浏览器操作：导航页面、点击元素、填写表单、截屏、执行 JavaScript 等。

### 4.3 Playwright MCP

Playwright 支持 Chromium、Firefox 和 WebKit 三种引擎，通过结构化的可访问性快照（而非截图）与页面交互，更适合 LLM 消费。

```bash
# Claude Code 中添加
claude mcp add playwright -s user -- npx -y @anthropic-ai/mcp-server-playwright
```

### 4.4 Browser MCP（browsermcp.io）

一个通用的浏览器自动化 MCP 服务，支持 Claude、Cursor、VS Code、Windsurf 等多种 AI 应用。所有自动化操作在本地执行，数据不会发送到远程服务器。

安装方式：
1. 安装 Browser MCP 的 Chrome 扩展
2. 在 AI 应用中配置 MCP Server 连接

### 4.5 Dev Browser（开源 Skill）

GitHub 上的开源项目 `SawyerHood/dev-browser`，专为 Claude Code 设计的浏览器自动化 Skill。核心优势是**持久化浏览器状态**——页面只需加载一次，后续操作无需重新加载 DOM。

```bash
# 安装
SKILLS_DIR=~/.claude/skills
mkdir -p $SKILLS_DIR
git clone https://github.com/sawyerhood/dev-browser /tmp/dev-browser-skill
cp -r /tmp/dev-browser-skill/skills/dev-browser $SKILLS_DIR/dev-browser
```

配合 Chrome 扩展后，Claude 可以直接控制用户已有的 Chrome 标签页，使用已登录的会话状态。

---

## 五、方案选择建议

### 场景一：日常办公自动化（非开发者）

→ **推荐：Claude in Chrome 官方扩展**

最适合处理邮件管理、日历安排、表单填写、网页研究等日常任务。无需编程知识，直接用自然语言指令即可。

### 场景二：Web 应用开发测试

→ **推荐：Claude Code + Chrome 集成**

从终端编码，在浏览器测试，读取控制台日志调试，形成完整的开发循环。

### 场景三：复杂的多步骤浏览器自动化

→ **推荐：Playwright CLI（有 Shell 权限）或 Playwright MCP（沙盒环境）**

适合注册流程测试、端到端测试、批量数据提取等需要稳定可靠执行的场景。

### 场景四：快速浏览和截图

→ **推荐：Agent Browser**

最轻量，Token 消耗最低，适合简单的页面查看和信息获取。

---

## 六、关键注意事项

1. **安全第一**：所有浏览器自动化方案都面临提示注入风险，不要在未监督的情况下让 AI 处理敏感操作
2. **模型限制**：Claude in Chrome 扩展使用 Haiku 模型，复杂推理能力有限；Claude Code 集成可使用更强的 Sonnet/Opus
3. **Token 成本**：不同方案的 Token 消耗差异巨大，长流程任务建议选择 Playwright CLI
4. **浏览器兼容性**：官方扩展仅支持 Chrome 和 Edge；第三方方案如 Playwright 支持多浏览器
5. **隐私保护**：Browser MCP 等本地方案在本地执行，数据不外传；云端方案如 Browserbase 需注意数据安全

---

## 七、参考资源

- Anthropic 官方文档：https://support.claude.com/en/articles/12012173
- Claude in Chrome 权限指南：https://support.claude.com/en/articles/12902446
- Claude Code 浏览器集成：https://code.claude.com/docs/en/chrome
- Browser MCP 官网：https://browsermcp.io/
- Dev Browser GitHub：https://github.com/SawyerHood/dev-browser
- Playwright MCP：https://github.com/anthropic-ai/mcp-server-playwright

---

*报告生成日期：2026年3月4日*
