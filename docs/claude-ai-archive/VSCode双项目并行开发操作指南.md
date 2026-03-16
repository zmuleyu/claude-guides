# VSCode + Claude Code 双项目并行开发操作指南

> 方案：两个独立 VSCode 窗口，各自运行 Claude Code 会话
> 项目 A：AI Legislation Tracker（Next.js + TypeScript + Supabase）
> 项目 B：新项目（浏览器相关，待定）

---

## 1. 目录结构与初始化

```
D:\Projects\
├── ai-legislation-tracker\    # 项目 A
│   ├── CLAUDE.md
│   ├── .claude\
│   │   └── settings.json
│   └── src\...
│
└── browser-project\           # 项目 B
    ├── CLAUDE.md
    ├── .claude\
    │   └── settings.json
    └── src\...
```

每个项目独立初始化 Claude Code 上下文：

```bash
# 项目 A
cd D:\Projects\ai-legislation-tracker
claude init   # 生成 CLAUDE.md 骨架（如已有可跳过）

# 项目 B
cd D:\Projects\browser-project
claude init
```

---

## 2. CLAUDE.md 配置要点

两个项目的 CLAUDE.md 应各自独立，包含该项目专属的上下文。关键字段：

```markdown
# CLAUDE.md (项目 A 示例)

## Project
AI Legislation Tracker — 追踪全球 AI 立法动态的 Web 应用

## Tech Stack
- Framework: Next.js 14 (App Router)
- Language: TypeScript (strict mode)
- Database: Supabase (PostgreSQL + Row Level Security)
- Deployment: Cloudflare Pages (@cloudflare/next-on-pages)
- Styling: Tailwind CSS

## Build & Test
```bash
npm run dev          # 本地开发 (localhost:3000)
npm run build        # 生产构建
npm run lint         # ESLint
npm run test         # Vitest
```

## Code Conventions
- 文件命名: kebab-case
- 组件命名: PascalCase
- API 路由: app/api/[resource]/route.ts
- 提交信息: Conventional Commits (feat/fix/chore)

## Key Decisions
- Edge Runtime for Cloudflare Pages compatibility
- Supabase client via @supabase/ssr (not @supabase/auth-helpers)
- 中文 UI + 英文代码/注释
```

项目 B 按实际技术栈编写对应 CLAUDE.md，结构相同但内容独立。

---

## 3. 启动双窗口工作流

### 3.1 打开方式

```bash
# 终端 1 — 项目 A
code D:\Projects\ai-legislation-tracker

# 终端 2 — 项目 B
code D:\Projects\browser-project
```

或在 VSCode 中：`File → New Window`，然后 `File → Open Folder` 选择另一个项目。

### 3.2 Claude Code 会话启动

每个窗口中独立操作：

- **VSCode 扩展方式**：点击侧栏 Spark 图标，或状态栏 `✱ Claude Code`
- **终端方式**：在 VSCode 内置终端中直接运行 `claude`

两个窗口的 Claude Code 实例完全隔离——各自读取自己项目根目录的 CLAUDE.md，上下文互不干扰。

### 3.3 窗口管理建议

| 布局 | 适用场景 |
|------|---------|
| 左右分屏（Win+←/→） | 需要频繁对照两个项目 |
| 虚拟桌面分离（Win+Ctrl+D） | 各项目独立沉浸，减少干扰 |
| 单显示器轮换 + Alt+Tab | 一个项目为主、另一个偶尔切换 |

---

## 4. 代理环境配置

两个窗口共享同一代理配置，无需重复设置。确认 VSCode `settings.json` 中已有：

```jsonc
// 全局 settings.json (Ctrl+Shift+P → Preferences: Open User Settings JSON)
{
  "claudeCode.environmentVariables": [
    { "name": "HTTP_PROXY", "value": "http://127.0.0.1:7897" },
    { "name": "HTTPS_PROXY", "value": "http://127.0.0.1:7897" }
  ]
}
```

如果两个项目需要不同的环境变量（例如不同的 Supabase URL），在各项目 `.vscode/settings.json` 中分别配置：

```jsonc
// ai-legislation-tracker/.vscode/settings.json
{
  "claudeCode.environmentVariables": [
    { "name": "HTTP_PROXY", "value": "http://127.0.0.1:7897" },
    { "name": "HTTPS_PROXY", "value": "http://127.0.0.1:7897" },
    { "name": "SUPABASE_URL", "value": "https://xxx.supabase.co" },
    { "name": "SUPABASE_ANON_KEY", "value": "eyJ..." }
  ]
}
```

---

## 5. 额度管理策略（核心注意事项）

### 5.1 共享额度池

Claude.ai 网页端、Claude Code CLI、Claude Code VSCode 扩展**共享同一个 5 小时滚动窗口额度**。两个窗口同时消耗 = 额度减半速度翻倍。

### 5.2 模型选择策略

| 场景 | 推荐模型 | 理由 |
|------|---------|------|
| 架构设计、复杂 bug 排查 | Opus | 深度推理，但每 5h 约 10 条 |
| 日常编码、组件开发、重构 | Sonnet（默认） | 性价比最优，约 45 条/5h |
| 快速问答、代码审查、文档 | Haiku | 最快，约 Sonnet 3 倍额度 |

**实操建议：** 两个项目同时活跃时，全部使用 Sonnet。只在单个项目需要深度分析时临时切 Opus。

### 5.3 额度优化技巧

1. **交替节奏**：一个项目密集编码时，另一个做不消耗额度的工作（手动测试、写文档、review 代码）
2. **首条消息前置全部上下文**：减少来回澄清轮次，单次交互节省 5-6 倍 token
3. **频繁开新对话**：每个任务完成后新开 Claude Code 会话（`/clear` 或新开终端标签），避免上下文膨胀
4. **中文 token 税意识**：1 汉字 ≈ 2 tokens，prompt 中描述性内容尽量用英文关键词

### 5.4 额度耗尽应急

```
项目 A（高优先级）→ 继续用 Claude Code
项目 B（低优先级）→ 切换到 Claude.ai 网页端用 Haiku，或暂停等待窗口重置
```

---

## 6. Git 分支与版本控制

两个项目各自独立的 Git 仓库，互不影响。建议的分支策略：

```
# 项目 A
main → develop → feature/xxx

# 项目 B
main → develop → feature/xxx
```

Claude Code 默认在当前分支上操作。切换项目时确认当前分支状态：

```bash
# 快速检查（在各自终端中）
git status && git branch --show-current
```

---

## 7. 项目间数据隔离 Checklist

| 检查项 | 说明 |
|-------|------|
| CLAUDE.md 独立 | 各项目根目录有自己的 CLAUDE.md |
| .env 文件独立 | 不同的 API keys、数据库连接 |
| node_modules 独立 | 各自 `npm install`，不共享 |
| .claude/settings.json | 项目级 Claude Code 配置（权限、工具白名单） |
| Port 不冲突 | 项目 A 用 3000，项目 B 用 3001 或其他端口 |

---

## 8. 常见问题与排障

### Q1: 两个窗口的 Claude Code 会互相干扰吗？

不会。每个 VSCode 窗口的 Claude Code 是独立进程，各自有自己的会话上下文和工作目录。

### Q2: 代理连接异常（403/超时）

1. 确认 Clash Verge 处于 **Rule 模式**（非 Global）
2. 检查 `api.anthropic.com`、`claude.ai` 已配置走 OpenAI 代理组 → US 节点
3. TUN 模式下两个进程共享代理通道，通常无问题

### Q3: 一个窗口的 Claude Code 卡住了

不影响另一个窗口。在卡住的窗口中：
- 按 `Ctrl+C` 中断当前操作
- 运行 `/clear` 重置会话
- 最后手段：关闭该 VSCode 窗口重新打开

### Q4: 磁盘空间不足（C 盘 100GB）

两个项目的 node_modules 可能各占 200-500MB。确保项目目录在 D 盘。Claude Code 的全局缓存在 `~/.claude/`（C 盘），定期清理：

```bash
# 查看 Claude Code 缓存大小
du -sh ~/.claude/

# 清理旧会话记录（保留配置）
rm -rf ~/.claude/conversations/
```

---

## 9. 进阶：从方案二升级到 Claude Squad

当两个项目都需要高强度并行开发时，可引入 Claude Squad 统一管理：

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/smtg-ai/claude-squad/main/install.sh | bash

# 为项目 A 启动代理
cs -p claude   # 在 ai-legislation-tracker 目录下

# 为项目 B 启动代理
cs -p claude   # 在 browser-project 目录下
```

Claude Squad 通过 tmux + git worktrees 实现完全隔离，支持后台自动执行。但前提是你已经熟悉方案二的基本工作流。

---

## 10. 快速启动 Checklist

```
□ 两个项目目录已在 D 盘创建
□ 各项目 CLAUDE.md 已编写
□ 各项目 .env 文件已配置（不同端口、不同 API keys）
□ VSCode 全局 settings.json 已配置代理环境变量
□ Clash Verge Rule 模式 + Anthropic 域名走 US 节点
□ 两个 VSCode 窗口分别打开两个项目
□ 各窗口 Claude Code 会话已启动并确认工作目录正确
□ 开发端口已区分（A:3000 / B:3001）
```
