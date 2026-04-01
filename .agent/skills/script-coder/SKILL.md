---
name: script-coder
description: >-
  编写生产级 Python 和 Shell 脚本的 Agent 专项技能。
  强制遵循编程最佳实践：自定义异常层级、指数退避重试、线程安全日志、
  API Trace 审计、防御式响应提取、Google GenAI SDK 工程模式。
  当用户提及"编写脚本、Python 脚本、Shell 脚本、自动化脚本、batch script、
  写个工具、修复脚本、GenAI API 脚本、数据处理脚本、定时任务、
  爬虫、文件处理、CLI 工具、脚本开发"时触发。
metadata:
  version: "1.0.0"
  author: "Ray"
---

# Script Coder

编写**独立可执行的生产级 Python / Shell 脚本**。所有代码输出必须遵循本文档定义的工程模式和质量标准。

## 使用时机

- 独立 Python 脚本（数据处理、API 调用、文件操作、爬虫、CLI 工具）
- 独立 Shell 脚本（部署、备份、环境配置、自动化管线）
- 现有脚本的修复、重构、增强
- Google GenAI API 集成脚本

**不要使用**：

- Web 应用 / 框架项目（Flask / Django / FastAPI）
- 前端开发（HTML / CSS / JS）
- 库 / 包开发（setup.py / pyproject.toml）
- 配置文件编写（YAML / JSON / TOML）
- 单行命令 / 简单 shell 一行代码

## 执行流程

### Step 1: 需求分析 + 复杂度分级

从用户消息中拆解 6 个维度：

| 维度 | 提取内容 | 默认值 |
|------|---------|--------|
| 功能 | 核心逻辑描述 | 无（必须明确） |
| I/O | 输入源 / 输出目标 | stdin → stdout |
| 依赖 | 第三方库 / 外部工具 | 零依赖优先 |
| 并发 | 是否需要并行处理 | 否（同步） |
| 容错 | 异常处理级别 | 基础精确捕获 |
| GenAI | 是否涉及 Gemini API | 否 |

**然后判定复杂度**：

| 级别 | 判定条件 | 执行路径 |
|------|---------|----------|
| **简单** | 单文件 ≤100 行、无外部 API、无并发 | 跳过 Step 2，直接 Step 3 |
| **中等** | 100-500 行 或 涉及外部 API / 文件 I/O | 完整 Step 2 → Step 3 |
| **复杂** | 多文件 / 高并发 / GenAI API 集成 / 管线 | Step 2 含架构设计 → Step 3 |

### Step 2: 方案设计（中等/复杂级别）

输出简洁设计方案：

- **技术选型**：语言、关键依赖库
- **文件结构**：单文件 or 模块拆分
- **核心函数签名**：`def func_name(arg: type) -> type`
- **异常层级**：根异常 → 子类映射
- **并发模型**（如适用）：async / threading / multiprocessing

### Step 3: 代码生成

按照下方「工程模式表」编写代码。**从骨架模板开始**（见本文末尾），逐步填充业务逻辑。

### Step 4: 自审 Quality Gate

交付前**必须**逐项检查下方「Quality Gate 检查清单」。未通过项自动修复，最多 2 轮。

### Step 5: 交付汇报

向用户输出结构化汇报：

```markdown
✅ **脚本已创建**

| 项目 | 详情 |
|------|------|
| 文件 | `{文件路径}` |
| 语言 | Python / Shell |
| 行数 | X 行 |
| 依赖 | `pip install xxx` 或 无 |

**运行方式**：
`python3 script.py --arg1 value`

**注意事项**：（如有）
```

---

## 工程模式表

### Always-On（所有脚本强制执行）

| # | 模式 | 实现要求 |
|---|------|---------|
| 1 | **Shebang** | Python: `#!/usr/bin/env python3`　Shell: `#!/usr/bin/env bash` + `set -euo pipefail` |
| 2 | **Docstring** | 模块级 Purpose 描述；函数/类 docstring 含 Args + Returns + Raises |
| 3 | **Type Hints** | 所有函数参数和返回值必须有类型注解（`-> None` 亦不可省略） |
| 4 | **精确异常捕获** | 禁止裸 `except`、禁止 `except Exception: pass`；必须捕获具体异常类型 |
| 5 | **异常链保留** | `raise X() from e` 保留上下文；仅在隐藏实现细节时用 `from None` |
| 6 | **日志实时输出** | `print(..., flush=True)` 或 `_log()` 封装，确保非 TTY 环境实时可见 |
| 7 | **Shell 防御式** | `set -euo pipefail` + `"$var"` 双引号 + `command -v` 依赖检查 + `trap cleanup EXIT` |
| 8 | **敏感信息管理** | API Key 等 **必须** `os.environ.get()`，禁止硬编码；缺失时 `sys.exit(1)` + 配置指引 |
| 9 | **可读性** | ① 命名语义化（动词+名词）② 函数 ≤50 行 ③ 逻辑分块 + 空行分隔 |
| 10 | **配置与常量管理** | ① 可变配置外置 JSON 文件（如 `config/xxx_default.json`），注释键 `_comment_*` 加载时过滤 ② 所有 `config.get(key, default)` 的 default **必须**引用模块顶部 `_DEFAULT_*` 常量，**禁止内联 magic string / magic number** ③ `_hardcoded_defaults()` 函数作为配置文件不可用时的 Fallback，字典值全部引用 `_DEFAULT_*` 常量 ④ 常量命名：`_DEFAULT_` 前缀 + 大写蛇形（如 `_DEFAULT_API_BASE_URL`、`_DEFAULT_TIMEOUT_SECONDS`） |

### Conditional（特定场景触发）

| # | 模式 | 触发条件 | 实现要求 |
|---|------|---------|---------|
| C1 | **自定义异常层级** | 脚本 ≥3 个异常类型 | `ScriptError(Exception)` 根异常 → `ConfigError`, `APIError`, `ValidationError` |
| C2 | **Retry Decorator** | 涉及网络 / API / 外部服务 | 指数退避 + 随机抖动，分 `retry()` 同步 / `async_retry()` 异步；详见 [reference.md](reference.md) §1 |
| C3 | **线程安全日志** | 多线程 / `ThreadPoolExecutor` | `threading.Lock()` + `flush=True`；详见 [reference.md](reference.md) §2 |
| C4 | **Singleton Client + Proxy** | 涉及 Google GenAI API | `PROXY_URL` 读取 `http_proxy` 环境变量 + `httpx.Client(proxy=..., verify=False)` 注入 + `_get_client()` 全局单例；详见 [reference.md](reference.md) §3 |
| C5 | **防御式 Response 提取** | 涉及 Gemini API 调用 | `_safe_response_text()` / `_safe_stream_text()`；详见 [reference.md](reference.md) §4 |
| C6 | **API Trace 三段式** | 涉及外部 API 调用 | `_trace_log()` 写独立审计文件，强制 `*_request → *_response → *_success` 三段式；详见 [reference.md](reference.md) §5 |
| C7 | **多层容错纵深** | GenAI API 复杂管线 | L1 SDK → L2 Response 校验 → L3 函数重试 → L4 业务重试 |
| C8 | **Semaphore 并发控制** | asyncio 并发 | `asyncio.Semaphore(N)` 限制并发度 |
| C9 | **429 Fallback 降级** | GenAI 管线高可用 | `_call_with_fallback()` 主力 → 备用模型切换 |
| C10 | **流式 vs 非流式选型** | GenAI API 调用 | 非 thinking 模型 + JSON 输出 → **必须用 `generate_content`**（非流式），httpx read timeout 覆盖全请求；thinking 模型 / 长文本 → `generate_content_stream`；详见 [reference.md](reference.md) §8 |
| C11 | **单层重试原则** | 多层循环嵌套 | **禁止**在内层函数和外层循环同时设置重试 → N×M 放大；重试权归最外层业务循环；详见 [reference.md](reference.md) §8 |
| C12 | **Flat Pipeline** | 修复/重试循环 | 循环步骤 ≤3、return ≤3 条、版本追踪单变量 `best`；详见 [reference.md](reference.md) §9 模式 B |
| C13 | **Unified Sanitize** | 多规则清洗管线 | 统一入口 `sanitize()`，渲染前 + 外部输入后各调一次；详见 [reference.md](reference.md) §9 模式 A |
| C14 | **Best-Score Guard** | 多轮 AI 优化 | 追踪历史最佳版本，回写前检查 `score >= best['score']`；详见 [reference.md](reference.md) §9 模式 C |
| C15 | **Prompt 外置** | GenAI Prompt ≥20 行 | 外置 `.md` 文件 + `.replace()` 占位符（不用 `str.format()`）；详见 [reference.md](reference.md) §9 模式 D |
| C16 | **Dead Code Sweep** | 架构性变更后 | 搜索旧 API 调用者，零引用即删；详见 [reference.md](reference.md) §9 模式 E |
| C17 | **双通道日志** | 长时间运行管线 | `_setup_log_tee()` + `_log()` 同步写 stdout 和 `build.log`（比 Shell `tee` 更可靠）；详见 [reference.md](reference.md) §2 |
| C18 | **Platform-Aware Shell** | Shell 脚本含 `sed -i` / `date` / `readlink` / `mktemp` 等 | 脚本开头检测 `uname -s`，设置平台适配函数（如 `_sed_i`）；详见 [reference.md](reference.md) §10 |
| C19 | **Manifest 增量构建** | 多步管线 / 耗时构建任务 | `build_manifest.json` 记录每个工作单元的 SHA-256 + 状态，下次执行智能跳过已完成项，崩溃后极速恢复；详见 [reference.md](reference.md) §11 |
| C20 | **Prompt 数据完整性** | 向 LLM 传入结构化数据 | **严禁**对结构化数据做盲目字符截断（如 `json_str[:15000]`）——会静默丢失后续记录。正确做法：① 按字段精简（剥离非必需字段）构建 slim 版本 ② 若仍需限长则使用模块级 `_DEFAULT_*_MAX_CHARS` 常量并设充裕阈值（≥80K）③ 截断后必须校验结构完整性（如 segment 数量） |
| C21 | **线程闭包显式导入** | `ThreadPoolExecutor` 内使用跨模块全局变量 | 线程 worker 函数中 `except SomeError` 若 `SomeError` 来自其他模块的延迟初始化全局变量（如 `_infra._MediaAssetsError`），**必须**在当前模块顶部 `from _infra import _MediaAssetsError` 显式导入。裸名引用在主线程可能因模块属性解析侥幸通过，但在 `ThreadPoolExecutor` 闭包中会触发 `NameError`。详见 [reference.md](reference.md) §12 |
| C22 | **线程安全原子文件写入** | 多线程并发写同一文件 | `_save_*()` 使用确定性 `.tmp` 后缀（如 `path.with_suffix('.json.tmp')`）时，多线程会写同一 tmp 文件 → 先完成的线程 `os.replace` 消费 tmp → 后完成的线程 `FileNotFoundError`。**必须** `threading.Lock()` 序列化 + `tempfile.NamedTemporaryFile(delete=False)` 生成唯一 tmp 路径。详见 [reference.md](reference.md) §12 |

---

## Quality Gate — 自审检查清单

### 必选项（每个脚本必查）

```
□ Shebang 正确
□ 所有函数有 docstring + type hints
□ 无裸 except、无 pass 吞异常、异常链 raise ... from e
□ 日志输出 flush=True，长时间运行有进度输出
□ 敏感信息读 os.environ，非硬编码
□ Shell: set -euo pipefail + "$var" + command -v 依赖检查
□ 代码可读性：命名语义化、函数 ≤50 行、逻辑分块
□ Python 脚本有 if __name__ == "__main__": 入口
□ 配置默认值全部引用 _DEFAULT_* 常量，函数体内零 magic string / magic number
```

### 条件项（按场景勾选）

```
□ [网络/API] 外部调用有 retry + backoff
□ [GenAI API] 防御式 Response 提取
□ [GenAI API] Singleton Client + Proxy-Aware httpx.Client
□ [多线程] threading.Lock() 线程安全日志
□ [外部 API] API Trace 三段式 (request → response → success)
□ [GenAI API] 非 thinking 模型 + JSON 输出 → 非流式 generate_content
□ [多层循环] 重试控制权归最外层，内层函数无 retry 装饰器
□ [并发] asyncio.Semaphore 限制并发度
□ [文件操作] pathlib.Path 或 os.path，非字符串拼接
□ [危险操作] --dry-run 选项 + 用户确认逻辑
□ [Shell 跨平台] sed -i / date / readlink / mktemp 使用平台适配函数
□ [GenAI Prompt] 传入 LLM 的结构化数据无盲目字符截断，使用字段精简或充裕常量
□ [多线程] ThreadPoolExecutor worker 内 except 的异常类已在当前模块顶部显式 import
□ [多线程写文件] 原子文件写入使用 Lock + NamedTemporaryFile，非确定性 .tmp 后缀
```

---

## 错误处理表

| 情况 | 处理方式 |
|------|---------|
| 用户需求不明确 | 主动提问澄清，**不猜测不假设** |
| 依赖包未安装 | 代码头部 `# Requirements: pip install xxx`，脚本内 import 检测 |
| GenAI API Key 未配置 | 检测 `GOOGLE_API_KEY` / `GEMINI_API_KEY`（来源：`~/.zshrc` `export`），缺失时 `sys.exit(1)` + 配置指引 |
| GenAI API SSL 超时 | 通过代理连接 Gemini API 时 httpx SSL 握手超时 → 使用 `httpx.Client(proxy=PROXY_URL, verify=False)` + `HttpOptions(httpx_client=...)` |
| 生成代码不通过自审 | 自动修复后再次审查，最多 2 轮 |
| 涉及危险操作 | 明确警告 + `--dry-run` 选项 + 确认逻辑 |
| 执行环境不明确 | 询问用户：conda / 系统 Python / venv |
| 目标文件已存在 | 默认不覆盖，提供 `--force` 选项 |
| 跨平台兼容性 | 标注 macOS/Linux 差异（如 `sed -i` vs `sed -i ''`）|

---

## 代码骨架模板

### Python 脚本骨架

```python
#!/usr/bin/env python3
"""[脚本功能一句话描述]。

Usage:
    python3 script_name.py [--arg1 VALUE] [--dry-run]

Requirements:
    pip install xxx
"""

import argparse
import os
import sys

# -- 自定义异常 -------------------------------------------
class ScriptError(Exception):
    """脚本根异常。"""

class ConfigError(ScriptError):
    """配置 / 环境错误。"""

# -- 核心逻辑 ---------------------------------------------
def main(args: argparse.Namespace) -> None:
    """主入口。"""
    # TODO: 实现核心逻辑
    print("Done.", flush=True)

# -- CLI 入口 ---------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="预览模式")
    args = parser.parse_args()

    try:
        main(args)
    except ScriptError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nUser interrupted.", flush=True)
        sys.exit(130)
```

### Shell 脚本骨架

```bash
#!/usr/bin/env bash
# [脚本功能一句话描述]
# Usage: bash script_name.sh <arg1> [arg2]
set -euo pipefail

# -- 平台检测 --
OS_TYPE="$(uname -s)"
_sed_i() {
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# -- 依赖检查 --
for cmd in python3 jq curl; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "Missing: $cmd"; exit 1; }
done

# -- 参数解析 --
ARG1="${1:?Missing argument: arg1}"
ARG2="${2:-default_value}"

# -- 清理函数 --
cleanup() { echo "Cleaning up..."; }
trap cleanup EXIT

# -- 主逻辑 --
echo "Processing: $ARG1"
# TODO: 实现核心逻辑
echo "Done."
```

### GenAI API 追加片段

涉及 Gemini API 时，在 Python 骨架基础上追加以下模块（完整实现见 [reference.md](reference.md)）：

```python
import httpx
from google import genai
from google.genai import types, errors

PROXY_URL = os.environ.get('http_proxy', os.environ.get('HTTP_PROXY', 'none'))  # ~/.zshrc 标准

_client = None
def _get_client() -> genai.Client:
    """Singleton Gemini Client（支持代理 + SDK 内置重试）。"""
    global _client
    if _client is None:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ConfigError("API Key not set. Run: export GOOGLE_API_KEY=your-key")
        timeout = httpx.Timeout(300, connect=30.0)
        if PROXY_URL and PROXY_URL.lower() != 'none':
            http_client = httpx.Client(proxy=PROXY_URL, timeout=timeout, verify=False)
        else:
            http_client = httpx.Client(timeout=timeout)
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(httpx_client=http_client),
        )
    return _client

def _safe_response_text(response) -> str:
    """防御式提取 Gemini 非流式 response 文本。"""
    candidates = getattr(response, 'candidates', None)
    if not candidates:
        raise ValueError(f"Empty candidates (feedback={getattr(response, 'prompt_feedback', '?')})")
    c = candidates[0]
    if not getattr(c, 'content', None):
        raise ValueError(f"No content (finish_reason={getattr(c, 'finish_reason', '?')})")
    for part in c.content.parts or []:
        if hasattr(part, 'text') and part.text:
            return part.text
    raise ValueError("All parts have no text")
```

---

## 参考文档

- 完整代码模板 + 排错指南：[reference.md](reference.md)
- [[Python3 异步编程和异常处理的最佳实践]]
- [[Python 访问 Gemini API 最佳实践]]
- [Google GenAI Python SDK](https://github.com/googleapis/python-genai)
