# VSCode 并行开发指南：Git Worktree 与多项目方案

> 基于 Anthropic 官方文档、VSCode 1.103 发布说明、incident.io 实战博客及社区最佳实践整理。
> 最后更新：2025-03

---

## 方案全景对比

| 方案 | 隔离粒度 | 复杂度 | 最适场景 |
|------|---------|--------|---------|
| **`claude --worktree`（原生）** | 同仓库多分支，自动管理 | 极低 | Claude Code v2.1.50+，**首选** |
| **Git Worktree（手动）** | 同仓库多分支 | 低 | 需精确控制目录结构 |
| **双项目窗口** | 不同仓库 | 低 | 两个完全独立的项目 |
| **Claude Squad** | tmux + worktree | 中 | worktree > 3 或需后台自动运行 |
| **多 git clone** | 完全独立副本 | 低（但重） | ❌ 磁盘浪费，不推荐 |

---

## Part 1 — Claude Code 原生 Worktree（推荐首选）

> **来源：** Anthropic 官方 CLI 文档、Claude Code v2.1.50 更新说明

Claude Code v2.1.50 后内置 `--worktree` 旗标，自动创建、管理、清理 worktree，无需手动 `git worktree add`。

### 1.1 基本用法

```bash
# 命名 worktree，自动创建到 .claude/worktrees/feature-auth/
claude --worktree feature-auth

# 缩写
claude -w feature-auth

# 不命名，Claude 自动生成分支名
claude --worktree

# 在独立 tmux pane 中运行
claude --worktree feature-auth --tmux
```

Claude 会自动：
1. 在 `.claude/worktrees/<name>/` 创建隔离工作目录
2. 创建 `worktree-<name>` 分支（基于默认远程分支）
3. 会话结束时提示保留或删除该 worktree

### 1.2 多会话并行示例

```bash
# 终端 1：功能开发
claude -w feature-payments

# 终端 2：同时修复 bug（互不干扰）
claude -w bugfix-auth
```

两个实例各自操作独立文件树，彻底消除文件冲突。incident.io 团队实际运行 4-5 个并行 Claude 代理，将原本预估 2 小时的任务压缩至 10 分钟。

### 1.3 Desktop App 内置支持

Claude Desktop App 的 Code 标签页：
- `+ New session` → 自动创建 worktree 隔离
- Settings → Claude Code → "Worktree location" 更改默认路径
- Settings → "Branch prefix" 为所有 Claude 创建的分支统一加前缀（如 `claude/`）

### 1.4 .gitignore 配置

```gitignore
.claude/worktrees/
```

---

## Part 2 — Git Worktree 手动方案

> **来源：** VSCode 官方文档 (v1.103)、Logan Farci 实践指南、DataCamp Worktree 教程

### 2.1 目录约定：平级而非嵌套

**推荐**将 worktree 建在主仓库**旁边**（平级），而非内部子目录：

```
# ✅ 推荐（平级目录）
/projects/
├── my-app/              ← 主仓库 (main)
├── my-app-feature-a/    ← worktree (feature/user-auth)
└── my-app-bugfix/       ← worktree (fix/404-profile)

# ⚠️ 可用，但有嵌套风险
/projects/my-app/
└── .trees/
    ├── feature-a/
    └── bugfix/
```

> 使用嵌套方案时，需将 `.trees/` 加入 `.gitignore`，避免 git 将 worktree 目录误当子仓库。

### 2.2 创建 Worktree

```bash
cd /projects/my-app

# 创建新分支 + checkout 到平级目录
git worktree add ../my-app-feature-a -b feature/user-auth
git worktree add ../my-app-bugfix -b fix/404-profile

# 基于已有分支（不新建）
git worktree add ../my-app-review existing-branch-name

# 验证
git worktree list
```

### 2.3 在 VSCode 中操作

**命令行开多窗口：**

```bash
code ../my-app-feature-a
code ../my-app-bugfix
```

**VSCode 原生 GUI（v1.103+）：**

Source Control 视图 → 选择仓库 → `...` 菜单 → `Worktrees > Create Worktree`

创建后每个 worktree 作为独立条目出现在 Source Control Repositories 视图，右键可选：
- `Open Worktree in New Window`
- `Migrate Worktree Changes`（合并变更回主工作区）

**统览方案：** 在仓库根目录打开 VSCode（而非某个 worktree），Source Control 面板会列出所有活跃 worktree，便于掌握整体状态。

### 2.4 VSCode 扩展推荐

**Git Worktree Manager**（`jackiotyu.git-worktree-manager`，支持中文）

```jsonc
// .vscode/settings.json
{
  // 新建 worktree 时自动复制非 git 跟踪文件
  "git-worktree-manager.worktreeCopyPatterns": [
    ".env.local",
    ".env.development",
    "config/*.local.json"
  ],
  // 排除大体积目录
  "git-worktree-manager.worktreeCopyIgnores": [
    "node_modules/**",
    "dist/**",
    ".next/**"
  ],
  // 创建后自动执行初始化
  "git-worktree-manager.postCreateCmd": "npm install",
  // 在 Source Control 视图中显示 worktree 列表
  "git-worktree-manager.treeView.toSCM": true
}
```

快捷键 `Ctrl+Shift+R` 快速切换。

### 2.5 处理非 git 跟踪文件

每个 worktree 只含 git 跟踪的文件：

| 文件类型 | 处理方式 |
|---------|---------|
| `.env.local`、`.env.development` | 手动复制，或用 `worktreeCopyPatterns` 自动同步 |
| `node_modules/` | 每个 worktree 独立 `npm install`（约 200-500MB/个，建议放 D 盘） |
| 本地数据库 | 见下方策略 |

**推荐：编写 `setup.sh` 一键初始化：**

```bash
#!/bin/bash
# setup.sh — 放在主仓库根，每个新 worktree 运行一次
cp ../.env.local .env.local
npm install
echo "✅ Worktree ready"
```

### 2.6 本地数据库策略（Supabase 示例）

| 场景 | 策略 |
|------|------|
| 任务不涉及 schema 变更 | 所有 worktree 共用一个 Supabase 实例 |
| 涉及 migration / schema 变更 | 多 Docker 容器，用不同端口隔离（`54321`、`54322`） |

```bash
# worktree B 使用独立端口
SUPABASE_DB_PORT=54322 supabase start
```

---

## Part 3 — 前期配置优化

### 3.1 CLAUDE.md — 所有 Worktree 的共享锚点

`.claude/` 被 git 跟踪，所有 worktree 自动继承。

```markdown
# CLAUDE.md

## Project
AI Legislation Tracker — 追踪全球 AI 立法动态

## Tech Stack
- Next.js 14 (App Router) + TypeScript strict
- Supabase via @supabase/ssr (not @supabase/auth-helpers)
- Cloudflare Pages + Edge Runtime required for all API routes

## Commands
npm run dev | build | lint | test

## Conventions
- kebab-case 文件 | PascalCase 组件
- Conventional Commits: feat/fix/chore/docs/refactor/test
- 中文 UI + 英文代码/注释

## Active Worktrees
- main: stable base
- feature/payments: Stripe integration
- fix/404: Profile page (../my-app-fix404)
```

### 3.2 自定义命令

```bash
mkdir -p .claude/commands
```

`.claude/commands/implement-feature.md`：
```markdown
读取 $ARGUMENTS 作为功能描述
1. 先在 tasks.md 写下实现计划，等待确认
2. 只修改当前 worktree 分支相关文件
3. 每完成一个逻辑单元就 commit（conventional commits 格式）
4. 完成后更新 tasks.md 状态为 done
```

`.claude/commands/done.md`：
```markdown
1. 运行 npm run lint 和 npm test，修复所有错误
2. 提交所有未提交变更
3. git push -u origin HEAD
4. 输出 gh pr create 命令
```

### 3.3 tasks.md — 并行任务追踪

主仓库根目录维护，由主目录 Claude 负责统筹：

```markdown
# Parallel Tasks

| Worktree | Branch | Status | Note |
|----------|--------|--------|------|
| ../my-app-payments | feature/payments | 🔄 in progress | Stripe webhook pending |
| ../my-app-fix404 | fix/404-profile | ✅ PR#42 opened | Waiting review |
| main | - | 📋 coordinator | merge after #42 merges |
```

### 3.4 权限预设

`.claude/settings.local.json`（加入 `.gitignore`）：
```jsonc
{
  "granted_permissions": ["git", "run_tests", "write_files"],
  "allowed_commands": ["implement-feature", "done", "tdd"]
}
```

---

## Part 4 — 合并与 PR 工作流

### 4.1 从 Worktree 直接开 PR

每个 worktree 是独立分支，推送即可：

```bash
# 在 worktree 目录中
git push -u origin feature/payments

# GitHub CLI
gh pr create --title "feat: add Stripe integration" --base main
```

### 4.2 回主仓库合并

```bash
cd /projects/my-app   # main 分支

git fetch --all
git merge feature/payments
git merge fix/404-profile
```

或直接让主目录 Claude 处理：`"合并 feature/payments 到 main，解决冲突，跑测试"`

### 4.3 清理

```bash
# 单个清理
git worktree remove ../my-app-payments
git branch -d feature/payments

# 清理失效引用
git worktree prune
```

`claude --worktree` 原生方案退出时会自动提示清理，无需手动执行。

---

## Part 5 — 双项目并行（不同仓库）

### 5.1 初始化

```bash
cd D:\Projects\ai-legislation-tracker && claude init
cd D:\Projects\browser-automation && claude init
```

### 5.2 项目级环境变量

```jsonc
// ai-legislation-tracker/.vscode/settings.json
{
  "claudeCode.environmentVariables": [
    { "name": "HTTP_PROXY", "value": "http://127.0.0.1:7897" },
    { "name": "HTTPS_PROXY", "value": "http://127.0.0.1:7897" },
    { "name": "NEXT_PUBLIC_SUPABASE_URL", "value": "https://xxx.supabase.co" }
  ]
}
```

端口隔离：项目 A 用 `3000`，项目 B 在 `package.json` 中配置 `"dev": "next dev -p 3001"`。

---

## Part 6 — 通用配置

### 6.1 代理

VSCode 全局 `settings.json`：

```jsonc
{
  "claudeCode.environmentVariables": [
    { "name": "HTTP_PROXY", "value": "http://127.0.0.1:7897" },
    { "name": "HTTPS_PROXY", "value": "http://127.0.0.1:7897" }
  ]
}
```

Clash Verge 保持 **Rule 模式**，`api.anthropic.com` 走 US 节点。

### 6.2 窗口管理

| 布局 | 操作 | 适用 |
|------|------|------|
| 左右分屏 | `Win+←` / `Win+→` | 2 窗口对照 |
| 虚拟桌面 | `Win+Ctrl+D` 新建，`Win+Ctrl+←/→` 切换 | 3+ 窗口各自沉浸 |
| 单屏轮换 | `Alt+Tab` | 主次分明 |

### 6.3 额度管理

所有入口共享同一 5 小时滚动窗口，多开 = 消耗等倍加速。

| 策略 | 说明 |
|------|------|
| 全用 Sonnet | 多开时不切 Opus（Opus ≈ 10 条/5h，Sonnet ≈ 45 条） |
| 交替节奏 | 一窗口密集编码时，其他做 review/文档 |
| 首条消息前置全部上下文 | 节省 5-6x token |
| 任务完成即 `/clear` | 防上下文膨胀 |
| `/compact` | 上下文将满时压缩历史，继续当前会话 |
| 英文 prompt | 1 汉字 ≈ 2 tokens |

---

## Part 7 — 进阶工具

### 7.1 Claude Squad

```bash
curl -fsSL https://raw.githubusercontent.com/smtg-ai/claude-squad/main/install.sh | bash
cs -p claude   # 在项目目录启动
```

自动管理 tmux 会话 + worktree，支持后台持续运行。

### 7.2 worktree-workflow（forrestchang）

```bash
git clone https://github.com/forrestchang/worktree-workflow && cd worktree-workflow && ./install.sh
alias claude-wt='source ~/.local/bin/claude-wt'

# 一键：创建 worktree + 启动 Claude + 传入初始 prompt
claude-wt feature-auth "Implement JWT authentication"
```

提供 `/pr`、`/done` Claude Code 自定义命令。

### 7.3 git-worktree-runner（CodeRabbit）

```bash
git gtr config set gtr.editor.default vscode
git gtr config set gtr.ai.default claude
git gtr config add gtr.copy.include "**/.env.local"
git gtr config add gtr.hook.postCreate "npm install"

# 一键创建 worktree + 打开 VSCode + 启动 Claude
git gtr ai feature-auth
```

---

## 常见错误与修复

| 错误 | 原因 | 修复 |
|------|------|------|
| `fatal: 'branch' is already checked out` | 该分支已在另一 worktree 中 | `git worktree list` 找到冲突项后 `git worktree remove <path>`；或 `--force` 覆盖 |
| Worktree 路径失效（移动后） | `.git` 文件路径引用断裂 | `git worktree repair <path>` |
| Claude 无法访问平级 worktree | 工作目录范围限制 | 改用 `claude --worktree` 或在父目录启动 Claude |
| `node_modules` 丢失 | Worktree 不复制非 git 跟踪文件 | 在新 worktree 中 `npm install`，或配置 `postCreateCmd` |
| 代理 403/超时 | Clash Verge Global 模式拦截认证 | 切回 Rule 模式，确认 `api.anthropic.com` 走 US 节点 |

---

## 快速启动 Checklist

### 方案 A：`claude --worktree`（最简）

```
□ claude --version 确认 ≥ v2.1.50
□ CLAUDE.md 编写完成
□ .gitignore 加入 .claude/worktrees/
□ Clash Verge Rule 模式 + US 节点正常
□ claude -w <task-1> 启动第一个会话
□ 另开终端 claude -w <task-2> 启动第二个会话
□ tasks.md 追踪进度
```

### 方案 B：手动 Worktree

```
□ CLAUDE.md + .claude/commands/ 配置完成
□ .claude/settings.local.json 权限预设
□ setup.sh 编写好（.env 复制 + npm install）
□ git worktree add <平级目录> -b <branch>
□ git worktree list 确认成功
□ code <path> 为每个 worktree 开独立 VSCode 窗口
□ bash setup.sh 初始化环境
□ 启动 claude 确认工作目录正确
□ 完成后：push → PR → git worktree remove 清理
```

### 方案 C：双项目并行

```
□ 两项目在 D 盘，各自 CLAUDE.md 独立
□ 各项目 .vscode/settings.json 配置专属环境变量
□ 端口隔离（A:3000 / B:3001）
□ VSCode 全局 settings.json 配置代理
□ 两窗口分别打开并确认工作目录
```

---

## 参考资源

| 资源 | 说明 |
|------|------|
| [VSCode 官方 Worktree 文档](https://code.visualstudio.com/docs/sourcecontrol/branches-worktrees) | v1.103 原生 GUI 支持 |
| [Anthropic Claude Code Desktop 文档](https://code.claude.com/docs/en/desktop) | `--worktree` 旗标、并行会话 |
| [incident.io 实战案例](https://incident.io/blog/shipping-faster-with-claude-code-and-git-worktrees) | 4-5 个并行代理的真实生产经验 |
| [DataCamp Git Worktree 教程](https://www.datacamp.com/tutorial/git-worktree-tutorial) | 系统入门，含 AI 工作流章节 |
| [Git Worktree Manager 扩展](https://marketplace.visualstudio.com/items?itemName=jackiotyu.git-worktree-manager) | VSCode GUI 管理，支持 postCreateCmd |
| [forrestchang/worktree-workflow](https://github.com/forrestchang/worktree-workflow) | claude-wt 一体化脚本 |
| [coderabbitai/git-worktree-runner](https://github.com/coderabbitai/git-worktree-runner) | git gtr 全功能 worktree 管理 |
