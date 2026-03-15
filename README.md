# Claude 中国开发者使用指南

> 面向中国开发者的 Claude 安全使用、数据备份与效率优化完整指南。

## 为什么需要这份指南

- Claude 账号封禁**即时生效**，无数据导出缓冲期
- 从中国使用 VPN 访问 Claude 存在额外风险
- Claude Code CLI 与 Web 共享额度池，需要合理规划
- 没有官方的批量数据导出功能

## 指南目录

| 指南 | 内容 | 适用对象 |
|------|------|---------|
| [01-账号安全](guides/01-account-safety.md) | 注册、网络、内容规范、API 使用 | 所有用户 |
| [02-数据备份](guides/02-data-backup.md) | 对话/Prompt/日志备份方案 | 所有用户 |
| [03-效率方法论](guides/03-efficiency.md) | 高密度 Prompt、时间管理、批量任务 | Pro/Max 用户 |
| [04-Claude Code 专项](guides/04-claude-code.md) | CLI 工具最佳实践 | Claude Code 用户 |

## 模板与工具

- **[CLAUDE.md 模板](templates/CLAUDE.md.template)** — 项目级配置模板（8 个生产项目实战版）
- **[Slash Commands](templates/slash-commands/)** — 开箱即用的自定义命令
- **[Hooks](templates/hooks/)** — 安全扫描、通知等 hook 脚本
- **[claude-guard](tools/claude-guard/)** — 安全审计与备份 CLI 工具

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/你的用户名/claude-guides.git

# 2. 安装全局 pre-commit hook（防止 API Key 泄露）
cp templates/hooks/pre-commit ~/.git-hooks/pre-commit
chmod +x ~/.git-hooks/pre-commit
git config --global core.hooksPath ~/.git-hooks

# 3. 复制 CLAUDE.md 模板到你的项目
cp templates/CLAUDE.md.template your-project/CLAUDE.md
# 编辑 [占位符] 为实际内容

# 4. 安装 claude-guard 工具
pip install ./tools/claude-guard
claude-guard scan your-project/
```

## 贡献

欢迎提交 Issue 和 PR。

## 免责声明

本仓库基于 Anthropic 公开政策和社区经验整理，不代表官方立场。政策随时可能更新，请以 [Anthropic 官方文档](https://www.anthropic.com/legal/aup) 为准。
