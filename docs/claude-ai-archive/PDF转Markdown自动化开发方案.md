# PDF → Markdown 自动化管线开发方案

> 方案 A（本地 CLI 工具）+ 方案 C（Claude Code Hook 自动化）融合

---

## 一、架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    用户工作流                                  │
│                                                               │
│  ① Claude Code 中引用 PDF                                     │
│       ↓ Hook: PreToolUse (file_read/file_write)              │
│  ② 自动检测 .pdf 文件                                         │
│       ↓                                                       │
│  ③ 调用 pdf2md CLI 转换                                       │
│       ↓                                                       │
│  ④ 后处理（strip 页眉页脚/压缩空行/移除图片占位符）          │
│       ↓                                                       │
│  ⑤ 输出 .md 文件，Claude Code 直接读取 Markdown              │
│       → token 消耗减少 20-40%                                 │
└─────────────────────────────────────────────────────────────┘
```

**两层设计**：

| 层 | 职责 | 技术选型 |
|---|------|---------|
| **CLI 工具层** | PDF 解析 + Markdown 生成 + 后处理优化 | Python, marker-pdf 1.10.x |
| **Hook 集成层** | 文件检测 + 自动触发 + 缓存管理 | Shell/Node.js, Claude Code Hooks API |

---

## 二、CLI 工具层（`pdf2md`）

### 2.1 引擎选型决策

| 维度 | Marker | MinerU | MarkItDown |
|------|--------|--------|-----------|
| 结构保真度 | ★★★★☆ | ★★★★★ | ★★☆☆☆ |
| 速度（CPU） | ★★★★☆ | ★★★☆☆ | ★★★★★ |
| 安装复杂度 | 中（需 PyTorch） | 高（多模型下载） | 低（pip 一键） |
| 中文支持 | 好 | 优秀 | 一般 |
| GPU 加速 | 支持 | 支持 | 不需要 |
| License | GPLv3 | 部分 AGPL | MIT |
| 多格式支持 | PDF/DOCX/PPTX/EPUB | 主要 PDF | PDF/DOCX/PPT/Excel |

**推荐：Marker 作为主引擎，MarkItDown 作为轻量 fallback。**

理由：Marker 在结构保真和速度间取得最佳平衡，且 `--use_llm` 模式可用 Gemini API 进一步提升表格/公式精度。MarkItDown 作为零依赖 fallback 处理简单文本型 PDF。

### 2.2 安装与环境配置

```bash
# 创建专用虚拟环境
python3.12 -m venv ~/.pdf2md-env
source ~/.pdf2md-env/bin/activate

# 主引擎
pip install marker-pdf  # v1.10.2, 含 PyTorch + surya-ocr

# 轻量 fallback
pip install markitdown  # Microsoft, MIT license

# 可选：LLM 增强模式（需 Gemini API Key）
# export GOOGLE_API_KEY=your_key
```

**代理环境适配**（你的 Clash Verge on port 7890）：

```bash
# pip 安装时走代理
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
pip install marker-pdf
```

### 2.3 CLI 封装实现

```python
#!/usr/bin/env python3
"""pdf2md - PDF to Markdown converter optimized for LLM token reduction."""

import argparse
import json
import os
import re
import sys
import hashlib
from pathlib import Path
from typing import Optional

# ============================================================
# Config
# ============================================================
CACHE_DIR = Path.home() / ".cache" / "pdf2md"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# Core: Conversion Engines
# ============================================================

def convert_with_marker(
    pdf_path: str,
    output_dir: str,
    force_ocr: bool = False,
    use_llm: bool = False,
    max_pages: Optional[int] = None,
) -> str:
    """Primary engine: marker-pdf."""
    from marker.converters.pdf import PdfConverter
    from marker.config.parser import ConfigParser

    config_dict = {
        "output_format": "markdown",
        "disable_image_extraction": True,  # 图片不传给 LLM，节省 token
    }
    if force_ocr:
        config_dict["force_ocr"] = True
    if use_llm:
        config_dict["use_llm"] = True
    if max_pages:
        config_dict["max_pages"] = max_pages

    config_parser = ConfigParser(config_dict)
    converter = PdfConverter(config=config_parser.generate_config_dict())
    result = converter(pdf_path)

    return result.markdown


def convert_with_markitdown(pdf_path: str) -> str:
    """Fallback engine: MarkItDown (lightweight, text-only)."""
    from markitdown import MarkItDown

    md = MarkItDown(enable_plugins=False)
    result = md.convert(pdf_path)
    return result.text_content


# ============================================================
# Post-processing: Token Optimization
# ============================================================

def postprocess(markdown: str, opts: dict) -> str:
    """Apply token-saving transformations to raw Markdown."""

    # 1. Strip repeated page headers/footers (common pattern)
    if opts.get("strip_headers", True):
        # Remove lines that repeat 3+ times (likely headers/footers)
        lines = markdown.split("\n")
        line_counts: dict[str, int] = {}
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) > 5:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1
        repeated = {l for l, c in line_counts.items() if c >= 3}
        lines = [l for l in lines if l.strip() not in repeated]
        markdown = "\n".join(lines)

    # 2. Collapse excessive blank lines (3+ → 2)
    if opts.get("collapse_blanks", True):
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

    # 3. Remove image placeholders (no value for LLM)
    if opts.get("strip_images", True):
        markdown = re.sub(r"!\[.*?\]\(.*?\)", "", markdown)
        # Also remove empty image references
        markdown = re.sub(r"\[image\d*\]", "", markdown, flags=re.IGNORECASE)

    # 4. Strip page numbers (standalone lines like "Page 5" or "- 5 -")
    if opts.get("strip_page_numbers", True):
        markdown = re.sub(r"^(?:Page\s+\d+|[-–—]\s*\d+\s*[-–—])\s*$", "", markdown, flags=re.MULTILINE)

    # 5. Normalize whitespace around headings
    markdown = re.sub(r"\n{3,}(#{1,6}\s)", r"\n\n\1", markdown)

    # 6. Final trim
    markdown = markdown.strip() + "\n"

    return markdown


# ============================================================
# Caching: Avoid redundant conversions
# ============================================================

def get_cache_key(pdf_path: str) -> str:
    """SHA256 of file content for cache lookup."""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def check_cache(pdf_path: str) -> Optional[str]:
    """Return cached Markdown if available and PDF unchanged."""
    cache_key = get_cache_key(pdf_path)
    cache_file = CACHE_DIR / f"{cache_key}.md"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    return None


def write_cache(pdf_path: str, markdown: str) -> None:
    cache_key = get_cache_key(pdf_path)
    cache_file = CACHE_DIR / f"{cache_key}.md"
    cache_file.write_text(markdown, encoding="utf-8")


# ============================================================
# Main CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF to LLM-optimized Markdown"
    )
    parser.add_argument("input", help="PDF file path")
    parser.add_argument("-o", "--output", help="Output .md path (default: same dir, .md ext)")
    parser.add_argument("--engine", choices=["marker", "markitdown", "auto"], default="auto",
                        help="Conversion engine (default: auto)")
    parser.add_argument("--force-ocr", action="store_true",
                        help="Force OCR on all pages (slower, for scanned PDFs)")
    parser.add_argument("--use-llm", action="store_true",
                        help="Use LLM for enhanced table/formula parsing (needs GOOGLE_API_KEY)")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Max pages to convert")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip cache lookup")
    parser.add_argument("--keep-images", action="store_true",
                        help="Keep image placeholders in output")
    parser.add_argument("--keep-headers", action="store_true",
                        help="Keep repeated headers/footers")
    parser.add_argument("--stats", action="store_true",
                        help="Print token estimation stats")

    args = parser.parse_args()

    pdf_path = os.path.abspath(args.input)
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Output path
    if args.output:
        out_path = args.output
    else:
        out_path = str(Path(pdf_path).with_suffix(".md"))

    # Cache check
    if not args.no_cache:
        cached = check_cache(pdf_path)
        if cached:
            Path(out_path).write_text(cached, encoding="utf-8")
            print(f"[cache hit] {out_path}")
            sys.exit(0)

    # Engine selection
    engine = args.engine
    if engine == "auto":
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        # MarkItDown for tiny files (<1MB, likely text-only)
        # Marker for everything else
        engine = "markitdown" if file_size_mb < 1.0 else "marker"

    print(f"[{engine}] Converting {Path(pdf_path).name}...", file=sys.stderr)

    # Convert
    if engine == "marker":
        markdown = convert_with_marker(
            pdf_path,
            output_dir=str(Path(out_path).parent),
            force_ocr=args.force_ocr,
            use_llm=args.use_llm,
            max_pages=args.max_pages,
        )
    else:
        markdown = convert_with_markitdown(pdf_path)

    # Post-process
    post_opts = {
        "strip_headers": not args.keep_headers,
        "strip_images": not args.keep_images,
        "collapse_blanks": True,
        "strip_page_numbers": True,
    }
    markdown = postprocess(markdown, post_opts)

    # Write output
    Path(out_path).write_text(markdown, encoding="utf-8")
    write_cache(pdf_path, markdown)

    # Stats
    if args.stats:
        pdf_size = os.path.getsize(pdf_path)
        md_size = len(markdown.encode("utf-8"))
        # Token estimation (rough)
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", markdown))
        en_words = len(re.findall(r"[a-zA-Z]+", markdown))
        est_tokens = cn_chars * 2 + int(en_words * 1.3)
        print(f"\n--- Stats ---", file=sys.stderr)
        print(f"PDF size:     {pdf_size / 1024:.1f} KB", file=sys.stderr)
        print(f"MD size:      {md_size / 1024:.1f} KB", file=sys.stderr)
        print(f"Est. tokens:  ~{est_tokens:,}", file=sys.stderr)
        print(f"Reduction:    ~{(1 - md_size / pdf_size) * 100:.0f}% (bytes)", file=sys.stderr)

    print(f"[done] {out_path}")


if __name__ == "__main__":
    main()
```

### 2.4 安装为全局命令

```bash
# 方式 1：直接链接
chmod +x pdf2md.py
ln -s $(pwd)/pdf2md.py ~/.local/bin/pdf2md

# 方式 2：通过 pip 可编辑安装（推荐）
# 创建 pyproject.toml 后:
pip install -e . --break-system-packages
```

`pyproject.toml` 最小配置：

```toml
[project]
name = "pdf2md"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "marker-pdf>=1.10.0",
    "markitdown>=0.1.0",
]

[project.scripts]
pdf2md = "pdf2md:main"
```

---

## 三、Claude Code Hook 集成层

### 3.1 Hook 机制概述

Claude Code Hooks 在 agent 生命周期的特定节点触发自定义脚本。与本方案相关的 Hook 点：

| Hook 点 | 触发时机 | 用途 |
|---------|---------|-----|
| `PreToolUse` | Claude 调用工具前 | 拦截 `Read` 工具对 `.pdf` 的读取请求 |
| `PostToolUse` | 工具调用完成后 | 验证转换结果 |
| `UserPromptSubmit` | 用户提交 prompt 时 | 扫描 prompt 中的 PDF 文件路径引用 |

### 3.2 核心 Hook 脚本

**文件：`~/.claude/hooks/pdf-auto-convert.sh`**

```bash
#!/usr/bin/env bash
# Claude Code Hook: Auto-convert PDF to Markdown before reading
# Hook point: PreToolUse (tool_name: Read)
#
# 当 Claude Code 尝试读取 .pdf 文件时：
#   1. 检查是否已有同名 .md 缓存
#   2. 如无缓存，调用 pdf2md 转换
#   3. 将读取路径重写为 .md 文件

set -euo pipefail

# 从 stdin 读取 hook input (JSON)
INPUT=$(cat)

# 提取工具名和文件路径
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# 仅处理 Read 工具 + .pdf 文件
if [[ "$TOOL_NAME" != "Read" ]] || [[ ! "$FILE_PATH" =~ \.pdf$ ]]; then
    exit 0  # 不干预，正常执行
fi

# 转换后的 Markdown 路径
MD_PATH="${FILE_PATH%.pdf}.md"

# 如果 .md 已存在且比 .pdf 新，直接用缓存
if [[ -f "$MD_PATH" ]] && [[ "$MD_PATH" -nt "$FILE_PATH" ]]; then
    echo "ℹ️ Using cached: $(basename "$MD_PATH")" >&2
    # 输出 JSON 修改工具参数，重写路径
    jq -n --arg path "$MD_PATH" '{
        "decision": "modify",
        "tool_input": {"file_path": $path}
    }'
    exit 0
fi

# 执行转换
echo "🔄 Converting $(basename "$FILE_PATH") → Markdown..." >&2

# 激活 pdf2md 虚拟环境
source ~/.pdf2md-env/bin/activate 2>/dev/null || true

if pdf2md "$FILE_PATH" -o "$MD_PATH" --stats 2>&1; then
    echo "✅ Converted: $(basename "$MD_PATH")" >&2
    jq -n --arg path "$MD_PATH" '{
        "decision": "modify",
        "tool_input": {"file_path": $path}
    }'
else
    echo "⚠️ Conversion failed, falling back to raw PDF" >&2
    exit 0  # 不干预，让 Claude Code 读原始 PDF
fi
```

### 3.3 Hook 注册配置

**文件：`~/.claude/settings.json`**（合并到现有配置）

```jsonc
{
  // ... 你现有的代理配置 ...
  "hooks": {
    "PreToolUse": [
      {
        "name": "pdf-auto-convert",
        "command": "bash ~/.claude/hooks/pdf-auto-convert.sh",
        "description": "Auto-convert PDF to Markdown before reading (saves 20-40% tokens)",
        "timeout_ms": 60000,  // 大文件可能需要较长时间
        "enabled": true
      }
    ]
  }
}
```

### 3.4 补充 Hook：Prompt 中 PDF 路径检测

**文件：`~/.claude/hooks/pdf-prompt-detect.sh`**

```bash
#!/usr/bin/env bash
# Hook point: UserPromptSubmit
# 扫描用户 prompt 中引用的 PDF 路径，预先转换

set -euo pipefail

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

# 用正则提取 prompt 中的 .pdf 路径
PDF_PATHS=$(echo "$PROMPT" | grep -oP '(?:^|[\s"'\''])(/[^\s"'\'']+\.pdf)' | tr -d ' "'\''' || true)

if [[ -z "$PDF_PATHS" ]]; then
    exit 0
fi

source ~/.pdf2md-env/bin/activate 2>/dev/null || true

CONVERTED=0
while IFS= read -r pdf; do
    [[ -z "$pdf" ]] && continue
    [[ ! -f "$pdf" ]] && continue

    md="${pdf%.pdf}.md"
    if [[ -f "$md" ]] && [[ "$md" -nt "$pdf" ]]; then
        continue  # 已有缓存
    fi

    echo "🔄 Pre-converting: $(basename "$pdf")" >&2
    pdf2md "$pdf" -o "$md" 2>&1 && ((CONVERTED++)) || true
done <<< "$PDF_PATHS"

if [[ $CONVERTED -gt 0 ]]; then
    echo "✅ Pre-converted $CONVERTED PDF(s) to Markdown" >&2
fi

exit 0
```

注册到 settings.json：

```jsonc
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "name": "pdf-prompt-detect",
        "command": "bash ~/.claude/hooks/pdf-prompt-detect.sh",
        "timeout_ms": 120000,
        "enabled": true
      }
    ]
  }
}
```

---

## 四、高级功能

### 4.1 批量转换模式

用于项目初始化时将整个目录的 PDF 预转换：

```bash
#!/usr/bin/env bash
# batch-pdf2md.sh - Batch convert all PDFs in a directory

DIR="${1:-.}"
PARALLEL="${2:-4}"  # 并行数

find "$DIR" -name "*.pdf" -type f | while read -r pdf; do
    md="${pdf%.pdf}.md"
    if [[ -f "$md" ]] && [[ "$md" -nt "$pdf" ]]; then
        echo "[skip] $(basename "$pdf") (cached)"
        continue
    fi
    echo "[queue] $(basename "$pdf")"
    echo "$pdf"
done | xargs -P "$PARALLEL" -I {} bash -c '
    source ~/.pdf2md-env/bin/activate 2>/dev/null
    pdf2md "{}" --stats 2>&1
'
```

可作为 Claude Code Slash Command 注册：

```markdown
<!-- .claude/commands/convert-pdfs.md -->
批量转换当前项目中所有 PDF 为 Markdown：
1. 扫描项目根目录下所有 .pdf 文件
2. 跳过已有 .md 缓存且未更新的文件
3. 并行转换（默认 4 线程）
4. 输出转换统计

执行: `bash ~/.claude/hooks/batch-pdf2md.sh $PROJECT_DIR`
```

### 4.2 Skill 自动激活集成

参考 `claude-code-infrastructure-showcase` 的 skill-rules.json 模式：

```jsonc
// .claude/skill-rules.json
{
  "rules": [
    {
      "name": "pdf-to-markdown",
      "triggers": {
        "file_patterns": ["*.pdf"],
        "keywords": ["PDF", "pdf", "论文", "报告", "文档转换"],
        "content_patterns": ["读取.*pdf", "分析.*pdf", "read.*\\.pdf"]
      },
      "action": "suggest",
      "message": "💡 检测到 PDF 文件引用。建议先运行 `pdf2md` 转换为 Markdown 以节省 ~30% token。\n执行: `/convert-pdfs` 或让我自动处理。"
    }
  ]
}
```

### 4.3 缓存管理

```bash
# 查看缓存状态
ls -lh ~/.cache/pdf2md/

# 清理过期缓存（>30 天）
find ~/.cache/pdf2md -name "*.md" -mtime +30 -delete

# 清空全部缓存
rm -rf ~/.cache/pdf2md/*
```

可加入 crontab 自动清理：

```bash
# 每周清理 30 天前的缓存
0 3 * * 0 find ~/.cache/pdf2md -name "*.md" -mtime +30 -delete
```

---

## 五、完整数据流示意

```
用户在 Claude Code 中:
  "请分析 ./docs/研究报告.pdf 的第三章"
       │
       ▼
  ┌─ UserPromptSubmit Hook ─────────────────────┐
  │  检测到 ./docs/研究报告.pdf                   │
  │  → pdf2md ./docs/研究报告.pdf                 │
  │  → 生成 ./docs/研究报告.md (缓存)             │
  └─────────────────────────────────────────────┘
       │
       ▼
  Claude Code 尝试 Read("./docs/研究报告.pdf")
       │
       ▼
  ┌─ PreToolUse Hook ───────────────────────────┐
  │  .md 缓存存在且较新                           │
  │  → 重写路径: Read("./docs/研究报告.md")        │
  └─────────────────────────────────────────────┘
       │
       ▼
  Claude Code 读取 .md 文件
  → token 消耗从 ~150K 降至 ~100K
  → 结构化 Markdown 提升模型理解准确度
```

---

## 六、开发路线图

| 阶段 | 内容 | 优先级 | 预计工时 |
|------|------|--------|---------|
| **P0: CLI 核心** | pdf2md.py + Marker 集成 + 后处理 + 缓存 | 🔴 必须 | 2 天 |
| **P0: Hook 基础** | PreToolUse 路径重写 Hook | 🔴 必须 | 1 天 |
| **P1: Prompt 检测** | UserPromptSubmit 预转换 Hook | 🟡 重要 | 0.5 天 |
| **P1: Slash Command** | `/convert-pdfs` 批量转换命令 | 🟡 重要 | 0.5 天 |
| **P2: Skill 激活** | skill-rules.json 自动提示 | 🟢 增强 | 0.5 天 |
| **P2: MarkItDown fallback** | 引擎自动降级 + 错误处理 | 🟢 增强 | 0.5 天 |
| **P3: 统计仪表盘** | 累计节省 token 统计、转换历史 | 🔵 可选 | 1 天 |

---

## 七、风险与应对

| 风险 | 影响 | 概率 | 应对 |
|------|------|------|------|
| Marker 安装依赖复杂（PyTorch ~2GB） | 首次配置耗时 | 中 | 提供一键安装脚本；MarkItDown 作为零依赖 fallback |
| GPU 不可用时 Marker 速度慢 | 大 PDF 转换超时 | 中 | `timeout_ms` 设充裕值；CPU 模式下限制 `--max-pages` |
| Claude Code Hook API 变更 | Hook 失效 | 低 | Hook 脚本 `exit 0` 兜底——失败不影响正常流程 |
| 复杂排版 PDF 转换丢失结构 | Markdown 质量差 | 中 | `--use-llm` 模式补救；保留原 PDF 路径供手动回退 |
| GPLv3 License 传染 | 不可商用 | 低 | 个人工具链使用无影响；商用场景换 MarkItDown (MIT) |
| 代理环境下载模型失败 | 安装中断 | 中 | 安装阶段确保 `HTTP_PROXY` 生效；可提前离线下载模型 |

---

## 八、关键配置参考

### 环境变量（加入 `~/.bashrc` 或 `~/.zshrc`）

```bash
# pdf2md
export PDF2MD_ENGINE=auto          # auto | marker | markitdown
export PDF2MD_CACHE_DIR=~/.cache/pdf2md
export PDF2MD_DEFAULT_OPTS="--stats"

# Marker 配置
export TORCH_DEVICE=cpu            # cpu | cuda | mps
# export GOOGLE_API_KEY=xxx        # 启用 --use-llm 时需要

# 代理（你的 Clash Verge）
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
```

### 与现有 Claude Code 配置合并

你的 `~/.claude/settings.json` 已有代理配置，追加 hooks 字段即可：

```jsonc
{
  "proxy": "http://127.0.0.1:7890",
  // 追加 ↓
  "hooks": {
    "PreToolUse": [
      {
        "name": "pdf-auto-convert",
        "command": "bash ~/.claude/hooks/pdf-auto-convert.sh",
        "timeout_ms": 60000,
        "enabled": true
      }
    ],
    "UserPromptSubmit": [
      {
        "name": "pdf-prompt-detect",
        "command": "bash ~/.claude/hooks/pdf-prompt-detect.sh",
        "timeout_ms": 120000,
        "enabled": true
      }
    ]
  }
}
```
