# Native Messaging Host 集成方案

> 基于 `Claude插件开发方案.docx` 的增量更新，引入 Chrome Native Messaging 实现浏览器插件 → Claude Code CLI 的可靠通信通道。

---

## 一、架构变更概览

### 1.1 变更前（纯 DOM 注入）

```
浏览器插件
  └── Content Script (DOM Bridge)
        ├── 注入输入框 → 模拟发送
        ├── 监听 DOM 变化 → 采集响应
        └── 选择器脆弱，依赖逆向工程
```

### 1.2 变更后（混合执行架构）

```
浏览器插件 (Orchestrator)
  ├── Background Service Worker
  │     ├── TaskScheduler（原有，不变）
  │     ├── ExecutorRouter（新增）── 根据 task.executor 分发
  │     └── NativeMessagingBridge（新增）── 与本地 Host 通信
  │           │
  │           ▼  chrome.runtime.connectNative()
  │     Native Messaging Host (Node.js)
  │           │
  │           ▼  child_process.spawn()
  │     Claude Code CLI (`claude -p "..."`)
  │           ├── 原生 MCP / Skills / 文件系统
  │           └── /loop cron tools（可选）
  │
  ├── Content Script (DOM Bridge)（保留，降级路径）
  │     └── 仅用于：claude.ai 网页对话、ChatGPT 等第三方平台
  │
  └── UI Layer（Popup / Side Panel / Options）
        └── 任务编辑器增加 executor 类型选择
```

### 1.3 核心价值

| 指标 | DOM 注入 | Native Messaging + CLI |
|------|---------|----------------------|
| 执行可靠性 | 低（选择器随时失效） | 高（官方 CLI 稳定接口） |
| 能力范围 | 仅网页对话 | MCP、Skills、文件系统、worktree |
| 响应采集 | 轮询 DOM + 启发式判断 | CLI stdout 直接返回 |
| 维护成本 | 高（跟踪前端变更） | 低（CLI 接口向后兼容） |
| 安装复杂度 | 零 | 需安装 Host + CLI |

---

## 二、Native Messaging 机制详解

### 2.1 Chrome Native Messaging 工作原理

```
Chrome 扩展 (Background SW)
      │
      │  chrome.runtime.connectNative("com.promptvault.host")
      │  或 chrome.runtime.sendNativeMessage(...)
      ▼
Chrome 浏览器进程
      │
      │  查找注册表/manifest → 启动 Host 进程
      ▼
Native Messaging Host (node.js 进程)
      │
      │  stdin/stdout（带 4 字节长度前缀的 JSON）
      ▼
Claude Code CLI (子进程)
```

### 2.2 通信协议

Chrome 与 Host 之间通过 stdin/stdout 交换消息，每条消息格式：

```
[4 bytes: uint32 little-endian 长度][JSON payload]
```

消息大小限制：单条最大 1MB。

### 2.3 Host 注册

**Windows**：注册表项

```
HKCU\Software\Google\Chrome\NativeMessagingHosts\com.promptvault.host
```

默认值指向 manifest JSON 文件路径。

**macOS**：

```
~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.promptvault.host.json
```

**Linux**：

```
~/.config/google-chrome/NativeMessagingHosts/com.promptvault.host.json
```

---

## 三、组件设计

### 3.1 Native Messaging Host Manifest

文件名：`com.promptvault.host.json`

```json
{
  "name": "com.promptvault.host",
  "description": "PromptVault Native Messaging Host - bridges Chrome extension to Claude Code CLI",
  "path": "/path/to/promptvault-host.js",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://<EXTENSION_ID>/"
  ]
}
```

> `path` 在 Windows 上指向 `.bat` 包装脚本，macOS/Linux 上直接指向 Node.js 脚本。

### 3.2 Host 进程实现

```typescript
// promptvault-host.ts
// 编译为 JS 后由 Node.js 运行

import { spawn, ChildProcess } from 'child_process';

// ─── Native Messaging I/O ───

function readMessage(): Promise<any> {
  return new Promise((resolve, reject) => {
    let lenBuf = Buffer.alloc(0);

    const onData = (chunk: Buffer) => {
      lenBuf = Buffer.concat([lenBuf, chunk]);

      if (lenBuf.length >= 4) {
        const msgLen = lenBuf.readUInt32LE(0);
        const remaining = lenBuf.slice(4);

        if (remaining.length >= msgLen) {
          process.stdin.removeListener('data', onData);
          const json = remaining.slice(0, msgLen).toString('utf-8');
          resolve(JSON.parse(json));
        }
        // else: wait for more data
      }
    };

    process.stdin.on('data', onData);
    process.stdin.once('error', reject);
    process.stdin.once('end', () => reject(new Error('stdin closed')));
  });
}

function sendMessage(msg: any): void {
  const json = JSON.stringify(msg);
  const buf = Buffer.from(json, 'utf-8');
  const lenBuf = Buffer.alloc(4);
  lenBuf.writeUInt32LE(buf.length, 0);
  process.stdout.write(lenBuf);
  process.stdout.write(buf);
}

// ─── Claude Code CLI Executor ───

interface ExecRequest {
  type: 'execute';
  id: string;           // request correlation ID
  prompt: string;       // prompt to send to Claude
  model?: string;       // e.g. 'sonnet' | 'opus'
  cwd?: string;         // working directory
  timeout?: number;     // ms, default 300000 (5 min)
  allowedTools?: string[];  // MCP tools whitelist
}

interface ExecResponse {
  type: 'result' | 'error' | 'progress';
  id: string;
  data?: string;
  exitCode?: number;
  error?: string;
}

async function executeClaudeCode(req: ExecRequest): Promise<void> {
  const args = ['-p', req.prompt, '--output-format', 'json'];

  if (req.model) {
    args.push('--model', req.model);
  }

  if (req.allowedTools?.length) {
    args.push('--allowedTools', req.allowedTools.join(','));
  }

  const proc: ChildProcess = spawn('claude', args, {
    cwd: req.cwd || process.env.HOME,
    timeout: req.timeout || 300_000,
    env: {
      ...process.env,
      // inherit proxy settings if needed
    },
    shell: process.platform === 'win32',
  });

  let stdout = '';
  let stderr = '';

  proc.stdout?.on('data', (chunk: Buffer) => {
    stdout += chunk.toString();
    // stream partial progress back to extension
    sendMessage({
      type: 'progress',
      id: req.id,
      data: chunk.toString(),
    } as ExecResponse);
  });

  proc.stderr?.on('data', (chunk: Buffer) => {
    stderr += chunk.toString();
  });

  proc.on('close', (code) => {
    if (code === 0) {
      sendMessage({
        type: 'result',
        id: req.id,
        data: stdout,
        exitCode: code,
      } as ExecResponse);
    } else {
      sendMessage({
        type: 'error',
        id: req.id,
        error: stderr || `Process exited with code ${code}`,
        exitCode: code,
      } as ExecResponse);
    }
  });

  proc.on('error', (err) => {
    sendMessage({
      type: 'error',
      id: req.id,
      error: err.message,
    } as ExecResponse);
  });
}

// ─── Capability Probing ───

interface ProbeRequest {
  type: 'probe';
  id: string;
}

async function handleProbe(req: ProbeRequest): Promise<void> {
  try {
    const proc = spawn('claude', ['--version'], { shell: process.platform === 'win32' });
    let version = '';
    proc.stdout?.on('data', (chunk) => { version += chunk.toString(); });
    proc.on('close', (code) => {
      sendMessage({
        type: 'result',
        id: req.id,
        data: JSON.stringify({
          available: code === 0,
          version: version.trim(),
          platform: process.platform,
          nodeVersion: process.version,
        }),
      });
    });
    proc.on('error', () => {
      sendMessage({
        type: 'result',
        id: req.id,
        data: JSON.stringify({ available: false, reason: 'claude CLI not found in PATH' }),
      });
    });
  } catch (e: any) {
    sendMessage({
      type: 'error',
      id: req.id,
      error: e.message,
    });
  }
}

// ─── /loop Integration ───

interface LoopRequest {
  type: 'loop';
  id: string;
  interval: string;    // e.g. '30m', '2h'
  prompt: string;
  cwd?: string;
}

async function executeLoop(req: LoopRequest): Promise<void> {
  // /loop runs inside an interactive Claude session
  // We use `claude` in non-interactive mode with cron tools
  const cronPrompt = `/loop ${req.interval} ${req.prompt}`;
  await executeClaudeCode({
    type: 'execute',
    id: req.id,
    prompt: cronPrompt,
    cwd: req.cwd,
  });
}

// ─── Main Loop ───

async function main() {
  while (true) {
    try {
      const msg = await readMessage();

      switch (msg.type) {
        case 'execute':
          await executeClaudeCode(msg as ExecRequest);
          break;
        case 'probe':
          await handleProbe(msg as ProbeRequest);
          break;
        case 'loop':
          await executeLoop(msg as LoopRequest);
          break;
        case 'ping':
          sendMessage({ type: 'pong', id: msg.id });
          break;
        default:
          sendMessage({ type: 'error', id: msg.id, error: `Unknown type: ${msg.type}` });
      }
    } catch (e: any) {
      // stdin closed = extension disconnected, exit gracefully
      if (e.message === 'stdin closed') break;
      // try to report error
      try { sendMessage({ type: 'error', id: 'unknown', error: e.message }); } catch {}
    }
  }
}

main();
```

### 3.3 Windows 启动包装脚本

`promptvault-host.bat`：

```bat
@echo off
node "%~dp0promptvault-host.js" %*
```

### 3.4 扩展侧 NativeMessagingBridge

在 Background Service Worker 中新增模块：

```typescript
// src/background/native-messaging-bridge.ts

type MessageHandler = (response: ExecResponse) => void;

class NativeMessagingBridge {
  private port: chrome.runtime.Port | null = null;
  private handlers: Map<string, MessageHandler> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private available: boolean | null = null; // null = unknown

  connect(): boolean {
    try {
      this.port = chrome.runtime.connectNative('com.promptvault.host');

      this.port.onMessage.addListener((msg: ExecResponse) => {
        const handler = this.handlers.get(msg.id);
        if (handler) {
          handler(msg);
          if (msg.type === 'result' || msg.type === 'error') {
            this.handlers.delete(msg.id);
          }
        }
      });

      this.port.onDisconnect.addListener(() => {
        const error = chrome.runtime.lastError?.message;
        console.warn('[NMBridge] Disconnected:', error);
        this.port = null;

        // reject all pending handlers
        for (const [id, handler] of this.handlers) {
          handler({ type: 'error', id, error: `Host disconnected: ${error}` });
        }
        this.handlers.clear();
      });

      this.reconnectAttempts = 0;
      this.available = true;
      return true;
    } catch (e) {
      this.available = false;
      return false;
    }
  }

  async probe(): Promise<{ available: boolean; version?: string }> {
    try {
      const result = await this.send({ type: 'probe', id: crypto.randomUUID() });
      const data = JSON.parse(result.data || '{}');
      this.available = data.available;
      return data;
    } catch {
      this.available = false;
      return { available: false };
    }
  }

  send(msg: any): Promise<ExecResponse> {
    return new Promise((resolve, reject) => {
      if (!this.port) {
        if (!this.connect()) {
          reject(new Error('Cannot connect to Native Messaging Host'));
          return;
        }
      }

      const timeout = setTimeout(() => {
        this.handlers.delete(msg.id);
        reject(new Error('Native Messaging timeout'));
      }, (msg.timeout || 300_000) + 5000); // CLI timeout + buffer

      this.handlers.set(msg.id, (response) => {
        clearTimeout(timeout);
        if (response.type === 'error') {
          reject(new Error(response.error));
        } else {
          resolve(response);
        }
      });

      this.port!.postMessage(msg);
    });
  }

  isAvailable(): boolean | null {
    return this.available;
  }

  disconnect(): void {
    this.port?.disconnect();
    this.port = null;
  }
}

export const nativeBridge = new NativeMessagingBridge();
```

### 3.5 ExecutorRouter（核心调度变更）

修改 `TaskScheduler.handleAlarm`，新增执行器路由层：

```typescript
// src/background/executor-router.ts

import { nativeBridge } from './native-messaging-bridge';

type ExecutorType = 'cli' | 'dom-inject' | 'auto';

interface TaskWithExecutor extends Task {
  executor: {
    type: ExecutorType;
    model?: string;         // CLI: model selection
    cwd?: string;           // CLI: working directory
    allowedTools?: string[]; // CLI: MCP tools whitelist
  };
}

class ExecutorRouter {
  /**
   * Determine the best executor for a task.
   * 'auto' mode: prefer CLI if available, fallback to DOM injection.
   */
  async resolveExecutor(task: TaskWithExecutor): Promise<'cli' | 'dom-inject'> {
    if (task.executor.type === 'cli') return 'cli';
    if (task.executor.type === 'dom-inject') return 'dom-inject';

    // auto: check CLI availability
    const cliAvailable = nativeBridge.isAvailable();

    if (cliAvailable === null) {
      // first time: probe
      const probe = await nativeBridge.probe();
      return probe.available ? 'cli' : 'dom-inject';
    }

    return cliAvailable ? 'cli' : 'dom-inject';
  }

  async execute(task: TaskWithExecutor, resolvedPrompt: string): Promise<ExecutionResult> {
    const executor = await this.resolveExecutor(task);

    switch (executor) {
      case 'cli':
        return this.executeCLI(task, resolvedPrompt);
      case 'dom-inject':
        return this.executeDOMInject(task, resolvedPrompt);
    }
  }

  private async executeCLI(
    task: TaskWithExecutor,
    prompt: string,
  ): Promise<ExecutionResult> {
    const startTime = Date.now();
    try {
      const response = await nativeBridge.send({
        type: 'execute',
        id: `task_${task.id}_${Date.now()}`,
        prompt,
        model: task.executor.model,
        cwd: task.executor.cwd,
        allowedTools: task.executor.allowedTools,
      });

      return {
        success: true,
        output: response.data || '',
        duration: Date.now() - startTime,
        executor: 'cli',
      };
    } catch (error: any) {
      // CLI failed → check if fallback is allowed
      if (task.executor.type === 'auto') {
        console.warn('[ExecutorRouter] CLI failed, falling back to DOM:', error.message);
        return this.executeDOMInject(task, prompt);
      }
      return {
        success: false,
        error: error.message,
        duration: Date.now() - startTime,
        executor: 'cli',
      };
    }
  }

  private async executeDOMInject(
    task: TaskWithExecutor,
    prompt: string,
  ): Promise<ExecutionResult> {
    // delegate to existing DOM Bridge via Content Script messaging
    const startTime = Date.now();
    try {
      const tab = await this.findOrOpenTargetTab(task);
      const response = await chrome.tabs.sendMessage(tab.id!, {
        type: 'EXECUTE_PROMPT',
        payload: { prompt, taskId: task.id },
      });
      return {
        success: true,
        output: response.output,
        duration: Date.now() - startTime,
        executor: 'dom-inject',
      };
    } catch (error: any) {
      return {
        success: false,
        error: error.message,
        duration: Date.now() - startTime,
        executor: 'dom-inject',
      };
    }
  }

  private async findOrOpenTargetTab(task: TaskWithExecutor): Promise<chrome.tabs.Tab> {
    const urlPattern = task.targetUrl || 'https://claude.ai/*';
    const [existing] = await chrome.tabs.query({ url: urlPattern });
    if (existing) return existing;
    return chrome.tabs.create({ url: task.targetUrl || 'https://claude.ai/new' });
  }
}

export const executorRouter = new ExecutorRouter();

interface ExecutionResult {
  success: boolean;
  output?: string;
  error?: string;
  duration: number;
  executor: 'cli' | 'dom-inject';
}
```

---

## 四、数据模型变更

### 4.1 Task 接口扩展

在原有 `Task` 接口基础上增加 `executor` 字段：

```typescript
interface Task {
  // ... 原有字段不变 ...

  // 新增：执行器配置
  executor: {
    type: 'cli' | 'dom-inject' | 'auto';  // auto = prefer CLI, fallback DOM
    // CLI-specific options
    model?: string;           // 'sonnet' | 'opus' | 'haiku'
    cwd?: string;             // Claude Code working directory
    allowedTools?: string[];  // MCP tools whitelist
    timeout?: number;         // execution timeout in ms
  };
}
```

默认值：`{ type: 'auto' }`，确保向后兼容。

### 4.2 执行历史扩展

```typescript
interface ExecutionLog {
  // ... 原有字段 ...

  // 新增
  executor: 'cli' | 'dom-inject';  // 实际使用的执行器
  cliExitCode?: number;            // CLI 退出码
  fallbackUsed?: boolean;          // 是否触发了降级
}
```

---

## 五、安装器设计

### 5.1 安装流程

用户首次使用 CLI 执行器时，插件检测 Host 未注册 → 弹出安装引导：

```
┌──────────────────────────────────────────┐
│  🔧 启用 Claude Code 集成               │
│                                          │
│  检测到尚未安装 Native Messaging Host。  │
│  安装后可通过 Claude Code CLI 执行任务， │
│  获得 MCP、Skills 等原生能力。           │
│                                          │
│  前提条件：                              │
│  ✅ Node.js ≥ 18                         │
│  ✅ Claude Code CLI 已安装               │
│                                          │
│  [一键安装]  [手动安装]  [跳过]          │
└──────────────────────────────────────────┘
```

### 5.2 一键安装脚本

**`install.sh`（macOS / Linux）**：

```bash
#!/bin/bash
set -euo pipefail

EXTENSION_ID="${1:?Usage: install.sh <chrome-extension-id>}"
HOST_NAME="com.promptvault.host"
HOST_DIR="$HOME/.promptvault"
HOST_SCRIPT="$HOST_DIR/promptvault-host.js"

# 1. Create host directory
mkdir -p "$HOST_DIR"

# 2. Copy host script
cp "$(dirname "$0")/promptvault-host.js" "$HOST_SCRIPT"
chmod +x "$HOST_SCRIPT"

# 3. Determine manifest location
if [[ "$OSTYPE" == "darwin"* ]]; then
  MANIFEST_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
else
  MANIFEST_DIR="$HOME/.config/google-chrome/NativeMessagingHosts"
fi
mkdir -p "$MANIFEST_DIR"

# 4. Write manifest
cat > "$MANIFEST_DIR/$HOST_NAME.json" <<EOF
{
  "name": "$HOST_NAME",
  "description": "PromptVault ↔ Claude Code CLI bridge",
  "path": "$HOST_SCRIPT",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://$EXTENSION_ID/"
  ]
}
EOF

# 5. Create Node.js wrapper (shebang)
TEMP=$(mktemp)
echo "#!/usr/bin/env node" > "$TEMP"
cat "$HOST_SCRIPT" >> "$TEMP"
mv "$TEMP" "$HOST_SCRIPT"
chmod +x "$HOST_SCRIPT"

# 6. Verify claude CLI
if command -v claude &>/dev/null; then
  echo "✅ Claude Code CLI found: $(claude --version)"
else
  echo "⚠️  Claude Code CLI not found in PATH. Install it first:"
  echo "   npm install -g @anthropic-ai/claude-code"
fi

echo "✅ Native Messaging Host installed at $MANIFEST_DIR/$HOST_NAME.json"
echo "   Restart Chrome to activate."
```

**`install.bat`（Windows）**：

```bat
@echo off
setlocal

set "EXTENSION_ID=%~1"
if "%EXTENSION_ID%"=="" (
    echo Usage: install.bat ^<chrome-extension-id^>
    exit /b 1
)

set "HOST_NAME=com.promptvault.host"
set "HOST_DIR=%USERPROFILE%\.promptvault"
set "HOST_SCRIPT=%HOST_DIR%\promptvault-host.js"
set "HOST_BAT=%HOST_DIR%\promptvault-host.bat"

:: 1. Create directory
if not exist "%HOST_DIR%" mkdir "%HOST_DIR%"

:: 2. Copy files
copy /Y "%~dp0promptvault-host.js" "%HOST_SCRIPT%"

:: 3. Create bat wrapper
(
echo @echo off
echo node "%%~dp0promptvault-host.js" %%*
) > "%HOST_BAT%"

:: 4. Write manifest
set "MANIFEST=%HOST_DIR%\%HOST_NAME%.json"
(
echo {
echo   "name": "%HOST_NAME%",
echo   "description": "PromptVault - Claude Code CLI bridge",
echo   "path": "%HOST_BAT%",
echo   "type": "stdio",
echo   "allowed_origins": [
echo     "chrome-extension://%EXTENSION_ID%/"
echo   ]
echo }
) > "%MANIFEST%"

:: 5. Register in Windows Registry
reg add "HKCU\Software\Google\Chrome\NativeMessagingHosts\%HOST_NAME%" /ve /t REG_SZ /d "%MANIFEST%" /f

:: 6. Verify claude CLI
where claude >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Claude Code CLI found
) else (
    echo [WARN] Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code
)

echo.
echo [OK] Native Messaging Host installed.
echo      Restart Chrome to activate.
```

### 5.3 卸载脚本

**`uninstall.sh`**：

```bash
#!/bin/bash
HOST_NAME="com.promptvault.host"
rm -rf "$HOME/.promptvault"

if [[ "$OSTYPE" == "darwin"* ]]; then
  rm -f "$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/$HOST_NAME.json"
else
  rm -f "$HOME/.config/google-chrome/NativeMessagingHosts/$HOST_NAME.json"
fi

echo "✅ Native Messaging Host removed."
```

**`uninstall.bat`**：

```bat
@echo off
set "HOST_NAME=com.promptvault.host"
rd /s /q "%USERPROFILE%\.promptvault" 2>nul
reg delete "HKCU\Software\Google\Chrome\NativeMessagingHosts\%HOST_NAME%" /f 2>nul
echo [OK] Native Messaging Host removed.
```

---

## 六、Manifest V3 权限变更

在 `manifest.json` 中新增：

```json
{
  "permissions": [
    "nativeMessaging",
    "alarms",
    "storage",
    "notifications"
  ]
}
```

`nativeMessaging` 是唯一新增权限，不需要额外的 host permissions，不会触发 Chrome Web Store 的额外审核门槛。

---

## 七、UI 变更

### 7.1 任务编辑器增加执行器选项

在任务编辑器（抽屉式弹出）中，新增"执行方式"区块：

```
┌─────────────────────────────────────────┐
│ 执行方式                                │
│                                         │
│ ○ 自动选择（推荐）                      │
│   优先使用 Claude Code CLI，不可用时    │
│   降级为网页注入                        │
│                                         │
│ ○ Claude Code CLI                       │
│   通过本地 CLI 执行，支持 MCP/Skills    │
│   ┌─ 模型: [Sonnet ▾]                  │
│   ├─ 工作目录: [~/projects/myapp    ]   │
│   └─ MCP 工具: [filesystem, github  ]   │
│                                         │
│ ○ 网页注入                              │
│   通过 DOM 注入 claude.ai/ChatGPT 执行  │
│   ┌─ 目标平台: [Claude.ai ▾]           │
│   └─ 目标 URL: [                     ]  │
│                                         │
└─────────────────────────────────────────┘
```

### 7.2 状态指示

任务列表中增加执行器标识：

```
⏰ 每日日报生成    🔴高   [CLI]
   9:00 AM · 每天 · Claude Code
   [完成] [暂缓] [编辑]

⏰ ChatGPT 翻译检查  🟡中  [DOM]
   10:00 AM · 工作日 · ChatGPT
   [完成] [暂缓] [编辑]
```

### 7.3 Options 页面增加诊断面板

```
┌─────────────────────────────────────────┐
│ Claude Code 集成状态                    │
│                                         │
│ Native Messaging Host:  ✅ 已连接       │
│ Claude Code CLI:        ✅ v1.2.3       │
│ Node.js:                ✅ v20.11.0     │
│ 上次探测:               2 分钟前        │
│                                         │
│ [重新检测]  [重新安装 Host]             │
└─────────────────────────────────────────┘
```

---

## 八、错误处理与降级策略

### 8.1 降级路径

```
CLI 执行尝试
  │
  ├── Host 未安装 → 提示安装 → 降级 DOM
  ├── Host 连接失败 → 重试 3 次 → 降级 DOM
  ├── Claude CLI 不在 PATH → 提示安装 → 降级 DOM
  ├── CLI 执行超时 → 记录日志 → 降级 DOM（仅 auto 模式）
  └── CLI 返回错误 → 记录日志 → 降级 DOM（仅 auto 模式）
```

### 8.2 错误码映射

| Host 错误 | 原因 | 处理 |
|-----------|------|------|
| `chrome.runtime.lastError: "Specified native messaging host not found"` | Host 未注册 | 弹出安装引导 |
| `chrome.runtime.lastError: "Native host has exited"` | Node.js 崩溃 | 重连，3次失败后降级 |
| CLI exit code 1 | Prompt 执行错误 | 记录 stderr，通知用户 |
| CLI exit code 127 | `claude` 命令未找到 | 提示安装 Claude Code |
| 消息超过 1MB | 响应过长 | 截断 + 提示用户 |

### 8.3 健康检查

Background Service Worker 每 30 分钟执行一次 probe：

```typescript
chrome.alarms.create('nm_health_check', { periodInMinutes: 30 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'nm_health_check') {
    nativeBridge.probe().then((status) => {
      // update badge icon based on CLI availability
      chrome.action.setBadgeText({
        text: status.available ? '' : '!',
      });
    });
  }
});
```

---

## 九、安全考量

### 9.1 权限最小化

- Host 进程仅执行 `claude` CLI，不执行任意命令
- `allowed_origins` 锁定到特定扩展 ID，防止其他扩展调用
- Prompt 内容通过 JSON 传递，不经过 shell 解析（避免命令注入）

### 9.2 输入验证

Host 端对所有输入进行校验：

```typescript
function validateRequest(msg: any): boolean {
  if (!msg || typeof msg !== 'object') return false;
  if (!['execute', 'probe', 'loop', 'ping'].includes(msg.type)) return false;
  if (msg.type === 'execute') {
    if (typeof msg.prompt !== 'string' || msg.prompt.length > 100_000) return false;
    if (msg.cwd && !isValidPath(msg.cwd)) return false;
  }
  return true;
}

function isValidPath(p: string): boolean {
  // reject path traversal, special chars
  return !p.includes('..') && /^[a-zA-Z0-9\-_\/\\.:~ ]+$/.test(p);
}
```

### 9.3 代理环境兼容

Host 进程继承系统环境变量。对于需要代理的场景（如你的 Clash Verge 配置），确保 `HTTP_PROXY` / `HTTPS_PROXY` 在 Host 启动时可用：

```typescript
const proc = spawn('claude', args, {
  env: {
    ...process.env,
    HTTP_PROXY: process.env.HTTP_PROXY || 'http://127.0.0.1:7897',
    HTTPS_PROXY: process.env.HTTPS_PROXY || 'http://127.0.0.1:7897',
  },
});
```

---

## 十、与 /loop 的深度集成

### 10.1 场景：插件编排 + /loop 执行

对于需要 Claude Code 内部持续轮询的任务，插件可以：

1. 通过 Native Messaging 启动一个 **交互式 Claude Code 会话**
2. 向该会话发送 `/loop` 命令
3. 会话在后台持续运行，直到 3 天过期或手动取消

```typescript
// Start an interactive session with /loop
async function startLoopSession(interval: string, prompt: string, cwd: string) {
  return nativeBridge.send({
    type: 'loop',
    id: crypto.randomUUID(),
    interval,
    prompt,
    cwd,
  });
}
```

### 10.2 场景：链式任务跨执行器

```
Task A (CLI): 分析代码库 → output: analysis.json
    │ complete
    ▼
Task B (CLI): 基于 analysis.json 生成重构计划
    │ complete
    ▼
Task C (DOM): 将重构计划发送到 ChatGPT 做 second opinion
    │ complete
    ▼
Task D (CLI): /loop 15m 监控重构 PR 的 CI 状态
```

链式任务引擎（原 `TaskChainEngine`）不需要修改，`ExecutorRouter` 会根据每个子任务的 `executor.type` 自动路由。

---

## 十一、开发计划调整

### 11.1 新增阶段

在原有 Phase 1-4 之间插入 **Phase 1.5**：

| Phase | 内容 | 工期 |
|-------|------|------|
| **1.5** | **Native Messaging 集成** | 1.5 周 |
| 任务 1 | 实现 Host 进程（Node.js stdio 通信 + Claude CLI 调用） | 2 天 |
| 任务 2 | 实现 NativeMessagingBridge（扩展侧连接管理） | 1 天 |
| 任务 3 | 实现 ExecutorRouter + Task 数据模型扩展 | 1 天 |
| 任务 4 | 编写跨平台安装/卸载脚本 | 1 天 |
| 任务 5 | UI：任务编辑器执行器选项 + Options 诊断面板 | 2 天 |
| 任务 6 | 端到端测试：CLI 执行、降级、链式跨执行器 | 1.5 天 |

### 11.2 里程碑补充

| 里程碑 | 时间 | 验收标准 |
|--------|------|---------|
| **M1.5 CLI 集成 Demo** | Phase 1.5 末 | 插件通过 Native Messaging 调用 `claude -p` 并采集完整输出，降级到 DOM 注入正常工作 |

### 11.3 风险矩阵补充

| 风险项 | 影响 | 可能性 | 应对 |
|--------|------|--------|------|
| 用户未安装 Node.js | 中 | 中 | 安装引导检测 + 提供 Node.js 下载链接；DOM 注入作为完整 fallback |
| Claude Code CLI 版本不兼容 | 低 | 低 | probe 时检测版本，维护最低兼容版本清单 |
| Native Messaging Host 被杀毒软件拦截 | 中 | 低 | 提供白名单指引文档；签名 Host 可执行文件（远期） |
| 代理环境导致 CLI 403 | 中 | 中 | Host 继承代理环境变量；Options 页面支持自定义代理配置 |

---

## 十二、文件结构变更

```
promptvault-extension/
├── src/
│   ├── background/
│   │   ├── index.ts                    // Service Worker entry
│   │   ├── task-scheduler.ts           // 原有，无变更
│   │   ├── executor-router.ts          // 🆕 执行器路由
│   │   └── native-messaging-bridge.ts  // 🆕 NM 通信层
│   ├── content/
│   │   ├── dom-bridge.ts              // 原有，保留为降级路径
│   │   └── ...
│   ├── ui/
│   │   ├── task-editor/
│   │   │   └── executor-config.tsx    // 🆕 执行器配置组件
│   │   └── options/
│   │       └── cli-diagnostics.tsx    // 🆕 诊断面板组件
│   └── types/
│       └── task.ts                    // 扩展 Task 接口
├── native-host/
│   ├── promptvault-host.ts            // 🆕 Host 进程源码
│   ├── tsconfig.json
│   └── package.json
├── scripts/
│   ├── install.sh                     // 🆕 macOS/Linux 安装
│   ├── install.bat                    // 🆕 Windows 安装
│   ├── uninstall.sh                   // 🆕
│   └── uninstall.bat                  // 🆕
├── manifest.json                      // 新增 nativeMessaging 权限
└── ...
```

---

## 十三、总结

| 方面 | 说明 |
|------|------|
| **核心改动** | 新增 Native Messaging Host + ExecutorRouter，实现 CLI 优先、DOM 降级的混合执行 |
| **向后兼容** | Task 默认 `executor: { type: 'auto' }`，未安装 Host 时自动使用 DOM 注入，用户无感 |
| **新增依赖** | Node.js ≥ 18（Host 运行时）、Claude Code CLI |
| **新增权限** | `nativeMessaging`（Chrome 侧唯一新增） |
| **额外工期** | ~1.5 周（可与 Phase 2 并行部分任务） |
| **最大风险** | 安装复杂度提升 → 通过一键安装脚本 + 清晰引导缓解 |
