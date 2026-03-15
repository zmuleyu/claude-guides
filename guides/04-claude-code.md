# Claude Code CLI 专项指南

> 面向 Claude Code CLI 用户的安全、效率和最佳实践指南。

---

## 一、核心概念

### 额度共享

Claude Code CLI 与 claude.ai 网页版**共享同一个额度池**。

```
┌─────────────────────────────────┐
│        Claude 额度池             │
│  ┌───────────┐ ┌───────────┐   │
│  │ Claude.ai │ │ Claude    │   │
│  │ 网页版     │ │ Code CLI  │   │
│  └───────────┘ └───────────┘   │
│        ↑ 两者消耗互相叠加 ↑      │
└─────────────────────────────────┘
```

**影响**：
- 重度使用 CLI 时，Web 端可用额度减少
- 多窗口并行 CLI 使用会加速消耗（建议 ≤3 窗口）
- `--print` 模式执行一次性命令，消耗相对较低

### 5 小时滑动窗口

额度不是每天重置，而是从第一条消息开始的 5 小时窗口内计算。

```
10:00 发第1条消息 → 窗口A开始
10:00–15:00 = 窗口A
15:00 窗口A到期 → 可开始窗口B
```

---

## 二、项目配置最佳实践

### CLAUDE.md

每个项目根目录应有 `CLAUDE.md`，Claude Code 每次启动自动读取。

```markdown
# 项目名

## 技术栈
[框架/语言/数据库/测试工具]

## 目录结构
[主要目录及用途]

## 开发规范
[代码风格/命名/Git 规范]

## 禁止事项
[不能做的事，如修改生产配置]

## 常用命令
[启动/测试/构建/数据库命令]
```

详细模板见 [CLAUDE.md.template](../templates/CLAUDE.md.template)。

### Memory 系统

Claude Code 的 memory 系统位于 `~/.claude/projects/*/memory/`，跨会话持久化。

**建议存储**：
- 用户偏好和角色信息
- 项目决策和约束
- 反馈和纠正记录
- 外部资源引用

**不应存储**：
- 代码模式（从代码本身读取）
- Git 历史（用 `git log` 查询）
- 临时状态

---

## 三、安全实践

### 全局 Pre-commit Hook

```bash
# 设置全局 hooks 目录
git config --global core.hooksPath ~/.git-hooks

# 创建 pre-commit 钩子
# 见 templates/hooks/pre-commit
```

自动扫描 staged 文件中的：
- Anthropic / OpenAI / AWS API Key
- GitHub PAT
- Supabase 密钥
- 私钥文件

### .secretsignore

在项目根目录创建 `.secretsignore` 白名单：

```
# 示例配置文件（含占位符）可以豁免
*.example
.env.example
docs/api-reference.md
```

### Hooks 安全规范

- **不要** 使用 `--no-verify` 跳过 pre-commit 检查
- **不要** 在 CLAUDE.md 中要求 Claude "绕过安全限制"
- **不要** 在 System Prompt 中包含 jailbreak 相关指令

---

## 四、效率技巧

### Slash Commands

在 `.claude/commands/` 下创建 `.md` 文件，定义可复用命令：

```
.claude/commands/
├── review.md    # /review — 代码审查
├── test.md      # /test <file> — 生成测试
└── doc.md       # /doc <module> — 生成文档
```

### Worktree 并行

利用 git worktree 在多个终端窗口同时处理不同任务：

```bash
# 任务1：新功能
claude --worktree feature/user-auth

# 任务2：Bug 修复（另一个终端）
claude --worktree fix/payment-bug
```

**关键**：确保两个 worktree 修改的文件**没有交集**。

### Hooks 自动化

```json
// ~/.claude/settings.json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "node /c/tools/claude-usage-logger.js start" }] }],
    "PostToolUse": [{ "matcher": "Write|Edit", "hooks": [{ "type": "command", "command": "bash auto-checkpoint.sh" }] }]
  }
}
```

### 长任务管理

跨 session 的大任务使用 `PROGRESS.md`：

```markdown
# PROGRESS.md

## 当前阶段：Phase 2 / 4

- [x] Phase 1: 数据模型设计
- [ ] Phase 2: API 端点实现  ← 当前
  - [x] GET /api/users
  - [ ] POST /api/users
  - [ ] PATCH /api/users/:id
- [ ] Phase 3: 前端组件
- [ ] Phase 4: 测试覆盖
```

新 session 开始时读 `PROGRESS.md` + `git log --oneline -10` 恢复上下文。

---

## 五、备份

### 关键资产

| 文件 | 位置 | 作用 |
|------|------|------|
| Memory 文件 | `~/.claude/projects/*/memory/` | 跨会话知识 |
| 全局配置 | `~/.claude/settings.json` | Hooks/权限/模型 |
| CLAUDE.md | 各项目根目录 | 项目指令 |
| Lessons | `~/.claude/lessons.md` | 经验教训 |
| Agent 日志 | `~/.claude/agent-logs/` | 会话记录 |

### 一键备份

```bash
# 使用 claude-guard 工具
python claude-guard/cli.py backup

# 紧急模式（跳过确认）
python claude-guard/cli.py backup --emergency
```

---

## 六、故障排查

| 问题 | 可能原因 | 解决 |
|------|---------|------|
| Edit 报 "File not read" | Session 压缩后恢复 | 先 Read 再 Edit |
| API 返回 429 | 额度耗尽 | 等待窗口重置 / 切 Haiku |
| Git push 失败 | PAT 缺 workflow scope | 更新 PAT 权限 |
| VPN 超时 | 节点不稳定 | 固定节点 + 检查 NO_PROXY |
| 多窗口冲突 | 同一文件被多 session 修改 | 声明文件边界 |
