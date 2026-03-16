# VSCode + Claude Code + Git Worktree 并行开发指南

> 核心思路：用 Git Worktree 为同一项目创建多个隔离工作目录，每个目录开一个 VSCode 窗口 + Claude Code 会话，实现**同一仓库内多任务并行开发**，最后合并回主分支。

---

## 1 | 适用场景

| 场景 | 说明 |
|------|------|
| 同一项目多 feature 并行 | 前端 UI + 测试 + 代码质量同时推进 |
| 长任务不阻塞短任务 | Claude 在 worktree A 跑大重构，worktree B 继续修 bug |
| 降低上下文冲突 | 每个 Claude Code 实例只看到自己分支的代码，不会互相覆盖 |

**与"双项目并行"的区别：** 双项目是两个独立仓库各开一个 VSCode 窗口；Worktree 方案是**一个仓库拆出多个工作目录**，共享 git 历史，适合单项目内的并行开发。

---

## 2 | 前期准备

### 2.1 创建自定义命令目录

```bash
mkdir -p .claude/commands
```

### 2.2 编写自定义命令（可选但推荐）

以 `/implement-feature` 为例，在 `.claude/commands/implement-feature.md` 中写：

```markdown
读取 $ARGUMENTS 作为功能描述
只修改前端目录
把变更摘要写入 frontend-changes.md
自动生成清晰的 commit message
```

其他常用命令参考：`/tdd`（测试驱动）、`/check`（代码质量扫描）、`/commit`（规范提交）。

### 2.3 配置权限预设

在 `.claude/settings.local.json` 中添加：

```jsonc
{
  "allowed_commands": ["implement-feature"],
  "granted_permissions": ["git", "run_tests", "write_files"]
}
```

这样 Claude 执行 git add/commit 或跑测试时不会反复要求确认。

---

## 3 | 建立 Git Worktree

### 3.1 创建工作树目录

```bash
# 在项目根目录执行
mkdir -p .trees

# 创建三个工作树，各自对应一个新分支
git worktree add .trees/ui_feature -b ui_feature
git worktree add .trees/testing_feature -b testing_feature
git worktree add .trees/quality_feature -b quality_feature
```

每条命令做了两件事：(1) 创建分支 (2) 在 `.trees/` 下 checkout 该分支为独立目录。

### 3.2 验证

```bash
git branch -a
# 应看到 main, ui_feature, testing_feature, quality_feature

git worktree list
# 应列出主目录 + 三个 .trees 子目录
```

### 3.3 目录结构

```
my-project/                    ← 主仓库 (main 分支)
├── .claude/
│   ├── commands/
│   │   └── implement-feature.md
│   └── settings.local.json
├── .trees/
│   ├── ui_feature/            ← 独立工作目录 (ui_feature 分支)
│   ├── testing_feature/       ← 独立工作目录 (testing_feature 分支)
│   └── quality_feature/       ← 独立工作目录 (quality_feature 分支)
├── src/
└── CLAUDE.md
```

> **注意：** `.claude/` 目录和 `CLAUDE.md` 在每个 worktree 中都可见（因为它们被 git 跟踪），所以自定义命令和项目上下文自动共享。

---

## 4 | 多开协作

### 4.1 在 VSCode 中打开多个窗口

```bash
# 方法一：命令行直接开三个窗口
code .trees/ui_feature
code .trees/testing_feature
code .trees/quality_feature

# 方法二：VSCode 内 File → New Window → Open Folder
```

**窗口管理建议：**

| 方案 | 操作 | 适用 |
|------|------|------|
| 左右分屏 | `Win+←` / `Win+→` | 2 个窗口对照 |
| 虚拟桌面 | `Win+Ctrl+D` | 3+ 个窗口各自沉浸 |
| 单屏轮换 | `Alt+Tab` | 主次分明时 |

### 4.2 每个窗口启动 Claude Code

在每个 VSCode 窗口的内置终端中：

```bash
claude
```

或使用 VSCode 侧栏的 Claude Code 扩展图标启动。

三个 Claude Code 实例**完全隔离**——各自的工作目录、分支、会话上下文互不干扰。

### 4.3 分工示例

| Worktree | 分支 | 任务 | Claude 指令示例 |
|----------|------|------|----------------|
| `.trees/ui_feature` | ui_feature | 前端功能开发 | `/implement-feature "主题切换功能"` |
| `.trees/testing_feature` | testing_feature | 编写测试用例 | `为 src/components/ 下所有组件编写单元测试，跑 vitest 并生成覆盖率报告` |
| `.trees/quality_feature` | quality_feature | 代码质量改进 | `新增 ESLint 规则、Prettier 配置，修复所有 lint 警告` |

---

## 5 | 代码合并

### 5.1 各分支提交

在每个 worktree 的终端中让 Claude 完成工作后提交：

```bash
# 在 Claude Code 中直接说：
# "提交当前所有更改，commit message 用英文 conventional commits 格式"

# 或手动：
git add -A && git commit -m "feat: implement theme toggle"
```

### 5.2 回主分支合并

关闭所有 worktree 的终端，回到主仓库目录：

```bash
cd /path/to/my-project   # 主仓库根目录（main 分支）

# 逐个合并
git merge ui_feature
git merge testing_feature
git merge quality_feature
```

如果不熟悉 git 命令，在主目录启动 Claude Code，直接说：

> "合并 .trees 目录下所有 worktree 的分支到 main，如有冲突帮我解决"

### 5.3 清理 Worktree

合并完成、测试通过后：

```bash
# 删除工作树
git worktree remove .trees/ui_feature
git worktree remove .trees/testing_feature
git worktree remove .trees/quality_feature

# 删除分支（可选）
git branch -d ui_feature testing_feature quality_feature

# 清理目录
rm -rf .trees
```

---

## 6 | 额度与效率管理

### 6.1 共享额度池

Claude.ai 网页端、Claude Code CLI、VSCode 扩展**共享同一个 5 小时滚动窗口额度**。三个 worktree 同时跑 = 额度消耗 ×3。

### 6.2 实操策略

| 策略 | 说明 |
|------|------|
| 交替节奏 | 一个 worktree 密集编码时，其他做手动测试/文档/review |
| 全用 Sonnet | 多开时全部用默认 Sonnet 模型，不要用 Opus |
| 首条消息前置上下文 | 减少来回澄清，单次交互节省 5-6 倍 token |
| 任务完成即 `/clear` | 避免上下文膨胀导致后续消息 token 爆炸 |
| 英文 prompt | 1 汉字 ≈ 2 tokens，描述性内容用英文关键词 |

### 6.3 额度不足时降级

```
高优先级 worktree → 继续用 Claude Code (Sonnet)
中优先级 worktree → 切 Haiku 模型
低优先级 worktree → 暂停，等 5h 窗口重置
```

---

## 7 | 代理环境配置

三个 VSCode 窗口共享代理配置。确认 VSCode 全局 `settings.json` 中已有：

```jsonc
{
  "claudeCode.environmentVariables": [
    { "name": "HTTP_PROXY", "value": "http://127.0.0.1:7897" },
    { "name": "HTTPS_PROXY", "value": "http://127.0.0.1:7897" }
  ]
}
```

Clash Verge 保持 **Rule 模式**，确保 `api.anthropic.com` 走 US 节点。

---

## 8 | 进阶方案对比

| 方案 | 隔离粒度 | 复杂度 | 适用场景 |
|------|----------|--------|----------|
| **Git Worktree**（本文） | 同仓库多分支 | 低 | 单项目多 feature 并行 |
| 双项目并行 | 不同仓库 | 低 | 完全不同的项目 |
| Claude Squad | tmux + worktree | 中 | 需要后台自动执行、统一管理 |
| Container Use (Dagger) | Docker 隔离 | 高 | 需要沙箱安全、多代理编排 |

### 8.1 升级到 Claude Squad

当 worktree 数量 > 3 或需要后台自动运行时：

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/smtg-ai/claude-squad/main/install.sh | bash

# 启动
cs -p claude
```

Claude Squad 自动管理 tmux 会话 + git worktree，支持任务在后台持续运行。

---

## 9 | 常见问题

**Q: Worktree 之间的 Claude Code 会互相干扰吗？**
不会。每个 VSCode 窗口的 Claude Code 是独立进程，工作目录不同，上下文完全隔离。

**Q: `.claude/` 配置在 worktree 中能共享吗？**
是的。只要 `.claude/` 目录被 git 跟踪，所有 worktree 都能访问自定义命令和配置。但 `settings.local.json` 如果在 `.gitignore` 中则需要手动复制。

**Q: 合并时冲突怎么办？**
在主目录启动 Claude Code，让它执行 merge 并自动解决冲突。对于复杂冲突，Claude 会展示冲突内容让你确认。

**Q: 磁盘空间够吗？**
每个 worktree 共享 `.git` 对象，额外占用很小（主要是工作区文件副本）。如果项目有大的 `node_modules`，每个 worktree 需要独立 `npm install`，约 200-500MB/个。建议项目放 D 盘。

---

## 10 | 快速启动 Checklist

```
□ CLAUDE.md 已编写，包含项目上下文和构建命令
□ .claude/commands/ 中写好常用自定义命令
□ .claude/settings.local.json 配置好权限预设
□ mkdir -p .trees 并创建所需 worktree
□ git branch -a 确认分支创建成功
□ 每个 worktree 用 code <path> 打开独立 VSCode 窗口
□ 每个窗口启动 Claude Code 并确认工作目录正确
□ Clash Verge Rule 模式 + US 节点正常
□ 开发完成后回主分支合并 + 测试 + 清理 worktree
```
