---
name: script-coder-reference
description: script-coder Skill 的排错指南与完整代码模板
---

# Script Coder Reference

Agent 编写脚本时需要查阅的完整代码模板和排错指南。SKILL.md 中的 Conditional 模式指向本文。

---

## §1 Retry Decorator — 完整实现

### 同步版

```python
import time
import functools
import random

def retry(
    max_retries: int = 3,
    backoff_base: float = 1.0,
    exceptions: tuple = (Exception,),
    jitter: bool = True,
):
    """同步重试装饰器 — 指数退避 + 随机抖动。

    Args:
        max_retries: 最大重试次数（不含首次调用）
        backoff_base: 退避基数（秒）
        exceptions: 触发重试的异常类型元组
        jitter: 是否添加随机抖动（防止雷群效应）
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_retries:
                        raise
                    delay = backoff_base * (2 ** attempt)
                    if jitter:
                        delay *= (0.5 + random.random())
                    print(f"  ⚠️ Retry {attempt+1}/{max_retries}: {e} → wait {delay:.1f}s", flush=True)
                    time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator

# 使用示例
@retry(max_retries=3, backoff_base=2.0, exceptions=(ConnectionError, TimeoutError))
def fetch_data(url: str) -> dict:
    """带重试的 HTTP 请求。"""
    import urllib.request, json
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())
```

### 异步版

```python
import asyncio
import functools
import random

def async_retry(
    max_retries: int = 3,
    backoff_base: float = 1.0,
    exceptions: tuple = (Exception,),
    jitter: bool = True,
):
    """异步重试装饰器 — 指数退避 + 随机抖动。"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_retries:
                        raise
                    delay = backoff_base * (2 ** attempt)
                    if jitter:
                        delay *= (0.5 + random.random())
                    print(f"  ⚠️ Retry {attempt+1}/{max_retries}: {e} → wait {delay:.1f}s", flush=True)
                    await asyncio.sleep(delay)
            raise last_exc
        return wrapper
    return decorator
```

---

## §2 线程安全日志 + 双通道写入

### Python 侧双通道（推荐）

```python
import io
import os
import threading
import sys

# 强制行缓冲 — 确保 conda run / nohup 下实时可见
if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass  # Python < 3.7

_log_lock = threading.Lock()
_log_file = None

def _setup_log_tee(build_dir: str) -> None:
    """初始化构建日志：后续 _log() 输出同时写入 build.log。"""
    global _log_file
    os.makedirs(build_dir, exist_ok=True)
    _log_file = open(os.path.join(build_dir, 'build.log'), 'w', encoding='utf-8')

def _log(*args, **kwargs) -> None:
    """线程安全 print — 同步写入 stdout 与 build.log（双通道）。

    比 Shell `tee` 更可靠：不受管道缓冲影响，Python 侧完全可控。
    """
    kwargs.setdefault('flush', True)
    with _log_lock:
        print(*args, **kwargs)
        if _log_file:
            buf = io.StringIO()
            print(*args, **{**kwargs, 'file': buf, 'flush': False})
            _log_file.write(buf.getvalue())
            _log_file.flush()
```

### Shell 侧备选（简单场景）

```bash
export PYTHONUNBUFFERED=1
python3 your_script.py "$@" 2>&1 | tee build.log
```

> [!TIP] 选型指南
>
> - **Python 双通道**：长时间运行管线、asyncio + 多线程、需要日志文件与控制台完全同步
> - **Shell tee**：简单脚本、无多线程、调用方控制日志落盘

---

## §3 Singleton Client — GenAI API（Proxy-Aware）

> **关键知识**：`GOOGLE_API_KEY` 和 `http_proxy` 通常在 `~/.zshrc` 中通过 `export` 设定，
> `conda run` / `bash -c` 等子进程会自动继承这些环境变量。

```python
import httpx
from google import genai
from google.genai import types, errors
import os

PROXY_URL = os.environ.get('http_proxy', os.environ.get('HTTP_PROXY', 'none'))
# ↑ 读取 ~/.zshrc 中 `export http_proxy=http://127.0.0.1:7897` 等标准代理配置

_client = None

def _get_client() -> genai.Client:
    """获取或创建全局 Gemini Client（单例复用 + 代理 + SDK 内置重试）。

    代理策略（来源：md2ppt _build_client 生产验证）：
      - 从 http_proxy / HTTP_PROXY 读取代理地址
      - 构造 httpx.Client(proxy=..., verify=False) 绕过代理 SSL 握手问题
      - 通过 HttpOptions(httpx_client=...) 注入 genai.Client
      - verify=False 仅在代理模式下启用，直连模式保持默认 SSL 验证
    """
    global _client
    if _client is None:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ConfigError(
                "API Key not set. Please run:\n"
                "  export GOOGLE_API_KEY=your-key\n"
                "or:\n"
                "  export GEMINI_API_KEY=your-key"
            )
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
```

> [!WARNING]
> **不要**直接使用 `types.HttpOptions(timeout=..., retry_options=...)` 而不传入自定义 `httpx_client`。
> genai SDK 内部会创建默认 httpx 客户端，其代理处理与 `http_proxy` 环境变量的交互可能导致
> SSL 握手超时（`httpx.ConnectTimeout: The handshake operation timed out`）。

---

## §4 防御式 Response 提取

### 非流式

```python
def _safe_response_text(response) -> str:
    """安全提取 Gemini 非流式 response 的文本。

    逐层检查 candidates → content → parts → text，
    每层提供诊断信息。

    Raises:
        ValueError: 任何层级校验失败
    """
    candidates = getattr(response, 'candidates', None)
    if not candidates:
        raise ValueError(
            f"Empty candidates "
            f"(prompt_feedback={getattr(response, 'prompt_feedback', '?')})"
        )
    candidate = candidates[0]
    finish = getattr(candidate, 'finish_reason', None)

    if not getattr(candidate, 'content', None):
        raise ValueError(f"No content (finish_reason={finish})")

    parts = candidate.content.parts
    if not parts:
        raise ValueError(f"Empty parts (finish_reason={finish})")

    for part in parts:
        if hasattr(part, 'text') and part.text:
            return part.text

    raise ValueError(f"All {len(parts)} parts have no text (finish_reason={finish})")
```

### 流式

```python
def _safe_stream_text(chunks) -> str:
    """安全收集流式 response 的文本片段（自动跳过 thinking tokens）。

    Raises:
        ValueError: 流式响应未返回任何有效文本
    """
    texts = []
    for chunk in chunks:
        try:
            t = chunk.text
        except (AttributeError, ValueError):
            t = None
        if t:
            texts.append(t)
    if not texts:
        raise ValueError("Stream returned no valid text")
    return ''.join(texts)
```

### 深度防御：JSON Autofix 截断处理 (From Mermaid-Chart SCSH)

在使用大模型输出超长 JSON 结构时，极有可能遭遇模型截断断点或安全过滤器触发，导致 `JSONDecodeError` 尾部不带结束符 `}` 的恶性错误。不要盲目依赖原生的 `json.loads`。

```python
import json
import re

def _parse_robust_json(clean_text: str) -> dict:
    """尝试加载模型 JSON 输出，在遇到截断损坏时主动拦截并通过正则抢救核心数据。"""
    try:
        return json.loads(clean_text, strict=False)
    except json.JSONDecodeError as e:
        # Heuristic fix for truncated outputs (e.g. truncated inside nested structure)
        # 不要直接抛出异常，使用正则进行关键字段（如总体评分、大纲）提取，手动重新组装有效 JSON。
        repaired_text = clean_text
        
        # 1. 解析外层独立有效字段 
        pass_match = re.search(r'"overall_pass"\s*:\s*(true|false)', repaired_text)
        overall_pass = True if pass_match and pass_match.group(1) == 'true' else False
        
        # 2. 从未闭合或损坏的 nested list 中榨取合法数据块 (如提取独立的 issue 对象)
        # 用 findall() 抽取全部合法子集 "\{[^{}]*\}"
        issues_matches = re.findall(r'(\s*\{\s*"dimension".*?\}\s*)', repaired_text, re.DOTALL)
        
        # 3. 拦截损坏的闭尾从而重建字典，允许管线容错继续
        return {
            "overall_pass": overall_pass,
            "issues": [json.loads(im) for im in issues_matches if '"severity"' in im]
        }
```

---

## §5 API Trace 审计日志 — 三段式全链路

> 来源：md2video render_video.py 生产级管线 — Director / Reviewer / Editor 三角色 Gemini API 调用链路排查

### 设计原则

1. **三段式审计**：每次 LLM 调用必须产出 3 条日志 — `*_request` → `*_response` → `*_success`
2. **Trace 与主日志分离**：`api_trace.log` 独立于 `build.log`，不污染控制台
3. **不中断主流程**：`suppress(OSError)` 包裹，日志失败绝不影响管线
4. **可追溯但不过载**：Request 记录配置参数 + prompt 字符数（不记录 prompt 原文），Response 保留完整输出

### `_trace_log` 基础设施

```python
import datetime
import json
from contextlib import suppress

def _trace_log(build_dir: str, action: str, payload: dict | str) -> None:
    """将 API trace 写入独立审计文件。

    截断策略：payload 上限 8000 chars，足以容纳 3-5 segment 完整 response，
    同时防止意外超大 payload 撑爆日志。
    """
    with suppress(OSError):
        trace_path = os.path.join(build_dir, "api_trace.log")
        with open(trace_path, "a", encoding="utf-8") as f:
            ts = datetime.datetime.now().isoformat()
            f.write(f"\n[{ts}] {action}\n")
            if isinstance(payload, dict):
                f.write(json.dumps(payload, ensure_ascii=False, indent=2)[:8000])
            else:
                f.write(str(payload)[:8000])
            f.write("\n" + "-" * 80 + "\n")
```

> [!IMPORTANT]
> 截断上限 **8000 chars**，不是 2000。调用侧**不要**再做额外截断（如 `text[:3000]`），统一由 `_trace_log` 内部控制。

### 三段式约定

每次 LLM API 调用**必须**在 `_trace_log` 中产出以下 3 条记录：

#### 1. `*_request` — API 调用前

记录 LLM 配置参数和 Prompt 规模（不含完整 Prompt 文本）。

```python
_trace_log(build_dir, "director_request", {
    "model": model_name,
    "temperature": cfg.get("temperature", 0.3),
    "max_output_tokens": cfg.get("max_output_tokens", 48000),
    "thinking_budget": cfg.get("thinking_budget", 8192),  # 如适用
    "user_prompt_chars": len(user_prompt),
    "system_prompt_chars": len(sys_prompt),
})
```

**Reviewer 等 per-item 调用**还需附加上下文字段：

```python
_trace_log(build_dir, "reviewer_request", {
    "model": model_name,
    "segment_id": seg_id,          # 正在审查的工作单元
    "num_assets": len(assets),     # 候选素材数量
    "temperature": ...,
    "max_output_tokens": ...,
    "user_prompt_chars": len(prompt),
    "system_prompt_chars": len(sys_prompt),
})
```

#### 2. `*_response` — API 返回后

记录完整 response 文本，由 `_trace_log` 统一截断至 8000 chars：

```python
raw_text = _safe_stream_text(response)    # 或 _safe_response_text()
_trace_log(build_dir, "director_response", raw_text)  # 不要 [:N] 截断
```

#### 3. `*_success` — 业务验证通过后

由 `_call_with_fallback()` 自动写入，包含模型名、尝试次数和角色配置快照：

```python
role_cfg_snapshot = {k: v for k, v in role_cfg.items() if k != "model"}
_trace_log(build_dir, f"{step_name}_success", {
    "model": model_name,
    "attempt": attempt + 1,
    **role_cfg_snapshot,  # temperature, thinking_budget 等
})
```

### 日志文件示例

```text
[2026-03-07T02:27:20.123] director_request
{
  "model": "gemini-3.1-pro-preview",
  "temperature": 0.3,
  "max_output_tokens": 48000,
  "thinking_budget": 8192,
  "user_prompt_chars": 2847,
  "system_prompt_chars": 1523
}
--------------------------------------------------------------------------------

[2026-03-07T02:27:21.504] director_response
{
  "version": "1.0",
  "segments": [...]
}
--------------------------------------------------------------------------------

[2026-03-07T02:27:21.505] director_success
{
  "model": "gemini-3.1-pro-preview",
  "attempt": 1,
  "temperature": 0.3,
  "thinking_budget": 8192
}
--------------------------------------------------------------------------------
```

### 反模式

```python
# ❌ 调用侧截断 — 与 _trace_log 内部截断叠加，日志不完整
_trace_log(build_dir, "editor_response", text[:3000])

# ✅ 直接传完整文本，由 _trace_log 统一 [:8000]
_trace_log(build_dir, "editor_response", text)

# ❌ 只记录 response，不记录 request — 无法回溯输入参数
def _call(model_name):
    resp = client.models.generate_content(...)
    _trace_log(build_dir, "response", text)

# ✅ request + response + success 三段式完整
def _call(model_name):
    _trace_log(build_dir, "role_request", {"model": model_name, ...})
    resp = client.models.generate_content(...)
    _trace_log(build_dir, "role_response", text)
    # success 由 _call_with_fallback 自动写入
```

---

## §6 429 Fallback 降级

```python
def _call_with_fallback(
    step_name: str,
    call_fn,
    model_config: dict,
    backup_config: dict,
    max_retries: int = 1,
    backoff_base: float = 15.0,
):
    """429 自动切换备用模型 + 退避重试。

    Args:
        step_name: MODEL_CONFIG 中的 key（如 "deep_think"）
        call_fn: 接受 model_name 参数的 callable
        model_config: 主力模型配置字典
        backup_config: 备用模型配置字典
        max_retries: 每个模型的最大重试次数
        backoff_base: 退避基数（秒）
    """
    models = [model_config[step_name]]
    backup = backup_config.get(step_name)
    if backup and backup != models[0]:
        models.append(backup)

    last_error = None
    for model_name in models:
        for attempt in range(max_retries):
            try:
                return call_fn(model_name)
            except errors.APIError as e:
                last_error = e
                if e.code == 429:
                    if attempt < max_retries - 1:
                        wait = backoff_base * (2 ** attempt)
                        print(f"  ⚠️ 429 rate limited ({model_name}), wait {wait:.0f}s...", flush=True)
                        import time; time.sleep(wait)
                    continue
                raise
    raise last_error
```

---

## §7 常见排错

| 症状 | 原因 | 修复 |
|------|------|------|
| `AttributeError: 'NoneType' has no attribute 'text'` | 直接访问 `response.text` 未做防御检查 | 使用 `_safe_response_text()` |
| `429 RESOURCE_EXHAUSTED` | API 限流 | 增大 `HttpRetryOptions.initial_delay`，或使用 `_call_with_fallback()` |
| `json.JSONDecodeError` | 模型输出被截断或格式不符 | 设置 `response_mime_type='application/json'` + 解析重试 |
| Shell 日志大量延迟 | 非 TTY 环境 Python 全缓冲 | `PYTHONUNBUFFERED=1` + `flush=True` + `line_buffering` |
| `sed -i` macOS 报错 | macOS sed 与 GNU sed 语法差异 | macOS 用 `sed -i ''`，Linux 用 `sed -i` |
| Bash 数组/关联数组报错 | macOS 默认 Bash 3.2 不支持 | `brew install bash` 升级到 4.0+ |
| 单个 API 调用等待 >5 分钟 | 双层重试 N×M 放大（内层 @retry × 外层业务循环） | 移除内层 retry 装饰器，重试权归最外层循环 |
| `generate_content_stream` 不超时 | httpx `read` timeout 仅限单 chunk，API 可无限 trickle | 非 thinking 模型改用 `generate_content` 非流式 |
| 超时后下一请求也超时 | `concurrent.futures` 超时不取消底层 HTTP 流 → orphan thread 占连接池 | 改用非流式 API 或超时后 `_client = None` 强制重建 |

---

## §8 GenAI API 超时与重试的陷阱

> 来源：mermaid-chart SCSH 管线实战排查 — 单图表 Gemini Vision 审查等待 >10 分钟

### 陷阱 1：流式 vs 非流式选型

| 场景 | 推荐 API | 原因 |
|------|---------|------|
| Non-thinking 模型 + JSON 输出 | `generate_content` | httpx `read` timeout 覆盖**整个请求**，超时语义精确 |
| Thinking 模型 / 长文本 / 实时显示 | `generate_content_stream` | 需要逐 chunk 处理，但 `read` timeout 仅限**单 chunk** |

**⚠️ 反模式**：对 `gemini-3-flash` + `response_mime_type='application/json'` 使用流式 API
— httpx `read=120s` 仅限单 chunk 读取超时，API 可无限 trickle data，连接永不超时。

```python
# ✅ 正确：非 thinking 模型用非流式
response = client.models.generate_content(
    model='gemini-3-flash-preview',
    contents=contents,
    config=types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type='application/json',
    ),
)
text = response.text  # httpx read=120s 覆盖全请求

# ❌ 错误：非流式场景用流式 API
for chunk in client.models.generate_content_stream(...):
    ...  # httpx read=120s 仅限每个 chunk，总时长不受控
```

### 陷阱 2：双层重试 N×M 放大

当存在多层循环时，**重试控制权必须归属唯一一层**，否则内层 M 次 × 外层 N 次 = M×N 次调用。

```python
# ❌ 错误：内层 @retry + 外层业务循环 → 3×3 = 9 次调用
@_retry_api_call(max_retries=3)      # 内层：API 级重试
def review_with_gemini(...):
    ...

def check_and_fix_block(...):
    while retries <= max_retries:     # 外层：业务级重试
        review = review_with_gemini(...)
        ...

# ✅ 正确：内层无 retry，重试权归外层
def review_with_gemini(...):
    ...  # 纯调用，无装饰器

def check_and_fix_block(...):
    while retries <= max_retries:     # 唯一重试层
        try:
            review = review_with_gemini(...)
        except APIError:
            retries += 1
            continue
```

### 陷阱 3：concurrent.futures 超时的 orphan thread

`ThreadPoolExecutor.future.result(timeout=N)` 超时后，底层线程**不会被取消**
— orphan thread 继续持有 httpx TCP 连接 → 后续请求排队等待连接池释放。

**解决方案**：优先选择非流式 API（彻底规避问题）。
如必须用流式 + 超时，超时后 `_client = None` 强制重建 httpx Client。

### 陷阱 4：异常堆栈丢失

API 异常发生时，`api_trace.log` 中仅记录错误消息不够——需完整 `traceback.format_exc()`：

```python
import traceback

try:
    response = client.models.generate_content(...)
except APIError as e:
    _trace_log(build_dir, '[API Exception]', {
        'error_type': type(e).__name__,
        'error_message': str(e)[:500],
        'cause': str(e.__cause__)[:300] if e.__cause__ else None,
        'traceback': traceback.format_exc(),  # 完整堆栈
    })
    raise
```

---

## §9 SCSH 管线萃取模式

> 来源：mermaid-chart SCSH 管线 v4.0.0 重构 — 1279 行图表自检修复管线的实战经验

### 模式 A: Unified Sanitize Entry

多规则清洗管线中，**必须**提供统一入口函数（如 `sanitize()`），在每次渲染/处理前和每次接收外部输入后各调用一次。禁止将清洗逻辑散落在业务代码各处。

```python
def sanitize(data: str) -> str:
    """统一清洗入口 — 合并所有确定性修复规则，固定顺序执行。"""
    for rule_name in RULE_REGISTRY:
        fixed = apply_rule(data, rule_name)
        if fixed and fixed != data:
            data = fixed
    return data
```

### 模式 B: Flat Pipeline Principle

修复/重试循环 ≤3 步骤，每步单一职责，return 路径 ≤3 条（`passed` / `failed` / `needs_intervention`）：

```text
for attempt in range(max_retries + 1):
    Step 1: sanitize → process     (确定性，零 API 成本)
    Step 2: review → pass/fail     (API 调用，可能失败)
    Step 3: validate_fix → update_best → next round
```

### 模式 C: Best-Score Guard

多轮 AI 优化场景中，追踪历史最佳版本，回写前检查分数，防止振荡退化：

```python
best = {'result': initial, 'score': -1}
for attempt in ...:
    if score > best['score']:
        best = {'result': current, 'score': score}
    if auto_save and score >= best['score']:
        save(current)
    else:
        log("跳过保存: 当前评分 < 历史最佳")
```

### 模式 D: Prompt Externalization

GenAI Prompt ≥20 行时外置为 `.md` 文件，使用 `.replace()` 逐个替换占位符（**不用** `str.format()` — JSON `{}` 冲突）：

```python
def _load_prompt(name: str, **kwargs) -> str:
    template = Path(PROMPT_DIR / name).read_text()
    for key, value in kwargs.items():
        template = template.replace(f'{{{key}}}', str(value) if value else '')
    return template
```

### 模式 E: Dead Code Sweep

架构性变更（流式→非流式、同步→异步、重试层上提等）完成后，**必须**搜索旧 API 的所有调用者，确认零引用后立即删除。不删除 = 技术债累积。

---

## §10 Platform-Aware Shell Scripting

> 来源：md2ppt / md2pdf / md2epub 预处理脚本 `sed -i` macOS 兼容性事故 (2026-02-28)

### 问题本质

macOS 使用 **BSD 工具链**，Linux 使用 **GNU 工具链**，二者在多个常用命令上存在**不可交换的语法差异**。这不是 "最佳实践"，而是 **不做就必定炸** 的硬性约束。

### 高危命令对照表

| 命令 | GNU (Linux) | BSD (macOS) | 差异根因 |
|------|-------------|-------------|----------|
| `sed -i` | `sed -i 's/a/b/' f` | `sed -i '' 's/a/b/' f` | BSD 要求显式 backup extension 参数 |
| `date` ISO | `date -d '2024-01-01' +%s` | `date -j -f '%Y-%m-%d' '2024-01-01' +%s` | `-d` vs `-j -f` 完全不同 |
| `readlink -f` | `readlink -f path` | 不支持 `-f` | 需 `realpath` 或 Python fallback |
| `mktemp` | `mktemp -d` ✅ | `mktemp -d` ✅ | 兼容，但 `mktemp -t` 行为不同 |
| `grep -P` | ✅ PCRE 支持 | ❌ 不支持 | macOS 需 `grep -E` 或 `brew install grep` |
| `find -regex` | GNU regex | BSD regex | 语法微差，建议用 `-name` 替代 |

### 标准防御模式：平台适配函数

**脚本开头**必须检测平台并定义适配函数。任何调用差异命令的地方，**必须**通过适配函数调用：

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── 平台检测 ────────────────────────────────────
OS_TYPE="$(uname -s)"

# sed -i：macOS BSD 需要空字符串 backup extension
_sed_i() {
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# date ISO 转时间戳
_date_epoch() {
    local date_str="$1"
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        date -j -f '%Y-%m-%d' "$date_str" +%s 2>/dev/null || echo "0"
    else
        date -d "$date_str" +%s 2>/dev/null || echo "0"
    fi
}

# readlink 绝对路径
_readlink_abs() {
    if command -v realpath >/dev/null 2>&1; then
        realpath "$1"
    elif [[ "$OS_TYPE" == "Darwin" ]]; then
        python3 -c "import os; print(os.path.realpath('$1'))"
    else
        readlink -f "$1"
    fi
}

# 使用示例
_sed_i 's/\[\[\([^]]*\)\]\]/\1/g' "$file"
```

### Case Study：`sed -i` 导致 md2ppt 构建全面失败

**背景**：三个姊妹 Skill（md2ppt / md2pdf / md2epub）各自的 `preprocess_*.sh` 从同一模板复制，包含 5-7 处 `sed -i 's/.../' "$f"` 调用。

**症状**：macOS 上运行报 `sed: 1: ".build_ppt/00_阅读索 ...": invalid command code .`

**根因**：

```text
sed -i 's/\[\[...\]\]/\1/g' ".build_ppt/00_阅读索引.md"
       ↑                     ↑
       BSD 认为这是          BSD 认为这是 sed expression
       backup extension      → '.' 不是合法 sed 命令 → 报错
```

BSD sed 的 `-i` 参数**必须**紧跟一个 backup extension（即使为空字符串 `''`），否则后续参数解析全部错位。

**修复**：全量搜索 `grep -rn "sed -i 's/" .agent/skills/ --include="*.sh"`，三个文件共 18 处，统一修复为 `sed -i '' 's/...'`。

**教训整合**：

1. Shell 脚本的跨平台兼容**不是可选项**，是 Quality Gate 必查项
2. 所有 `sed -i` 调用**必须**通过 `_sed_i()` 适配函数
3. 从模板复制脚本时，**模板本身**必须已包含平台检测头

---

## §11 Manifest-Based Incremental Build 与异常重试

> 来源：md2ppt v3.1 `render_slides.py` 生产级管线 — 1600 行多模型 AI 渲染管线的增量构建实战

### 问题本质

多步骤构建管线（如 Mermaid 渲染、AI 图像生成、Pandoc 编译）存在两个核心痛点：

1. **重复计算浪费**：源文件未变化时，耗时步骤（如 `mmdc` 图表渲染占 80% 构建时间）被无谓重复执行。
2. **崩溃回滚**：管线中途失败后，已成功的中间产物丢失，必须从头开始。

### 解决方案：`build_manifest.json`

在构建目录（如 `.build_xxx/`）中维护一份 JSON 清单，记录**每个工作单元**（章节、文件、图表）的完成状态和内容哈希。

### 核心架构（5 个函数）

```text
_manifest_path(build_dir)         → 清单文件定位
_load_manifest(build_dir)         → 加载或初始化空结构
_save_manifest(build_dir, data)   → 原子写入（.tmp + os.replace）
_item_needs_rebuild(manifest, key, hash, build_dir)
                                  → 三条件重建判定
_update_manifest(build_dir, key, hash, result)
                                  → 成功后写回记录
```

### Manifest JSON 结构示例

```json
{
  "version": 1,
  "items": {
    "ch01": {
      "status": "completed",
      "source_hash": "a1b2c3d4...sha256",
      "artifacts": ["ch01_diagram.png", "ch01_output.docx"],
      "built_at": "2026-03-04T14:00:00"
    },
    "ch02": {
      "status": "failed",
      "source_hash": "e5f6g7h8...sha256",
      "error": "mmdc render timeout",
      "built_at": "2026-03-04T14:01:00"
    }
  }
}
```

### Python 完整实现

```python
import hashlib
import json
import os
import threading
import datetime

MANIFEST_VERSION = 1
_manifest_lock = threading.Lock()


def _manifest_path(build_dir: str) -> str:
    """Manifest 文件的标准位置。"""
    return os.path.join(build_dir, 'build_manifest.json')


def _load_manifest(build_dir: str) -> dict:
    """加载 manifest，不存在则返回空结构。"""
    path = _manifest_path(build_dir)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'version': MANIFEST_VERSION, 'items': {}}


def _save_manifest(build_dir: str, manifest: dict) -> None:
    """原子写入 manifest（先写 .tmp 再 rename，防止崩溃时文件损坏）。"""
    path = _manifest_path(build_dir)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # 原子操作，保证不会写一半


def _compute_hash(content: str) -> str:
    """计算内容的 SHA-256 哈希。

    可将多个影响因素拼接（如源内容 + 用户指令）再求哈希，
    确保任何输入变化都触发重建。
    """
    return hashlib.sha256(content.encode()).hexdigest()


def _item_needs_rebuild(manifest: dict, key: str,
                        source_hash: str, build_dir: str) -> bool:
    """三条件重建判定——任一不满足即需重建。

    1. 状态检查：是否标记为 'completed'
    2. 哈希比对：源内容是否变更
    3. 产物存在性：磁盘上的构建产物是否完整
    """
    item = manifest.get('items', {}).get(key)
    if not item:
        return True  # 新项目，需构建
    if item.get('status') != 'completed':
        return True  # 上次失败或中断
    if item.get('source_hash') != source_hash:
        return True  # 源内容已变更
    # 检查产物文件是否全部存在
    for artifact in item.get('artifacts', []):
        if not os.path.exists(os.path.join(build_dir, artifact)):
            return True  # 产物丢失，需重建
    return False


def _update_manifest(build_dir: str, key: str, source_hash: str,
                     artifacts: list[str],
                     status: str = 'completed',
                     error: str | None = None) -> None:
    """构建完成后更新 manifest 记录（线程安全）。"""
    with _manifest_lock:
        manifest = _load_manifest(build_dir)
        entry = {
            'status': status,
            'source_hash': source_hash,
            'artifacts': artifacts,
            'built_at': datetime.datetime.now().isoformat(),
        }
        if error:
            entry['error'] = error
        manifest['items'][key] = entry
        _save_manifest(build_dir, manifest)
```

### 主循环集成示例

```python
def process_item(key: str, content: str, build_dir: str) -> None:
    """单个工作单元的处理与增量跳过。"""
    source_hash = _compute_hash(content)
    manifest = _load_manifest(build_dir)

    # ── 增量检查：跳过已完成且未变更的项目 ──
    if not _item_needs_rebuild(manifest, key, source_hash, build_dir):
        print(f"  [{key}] ⏩ 已完成，跳过", flush=True)
        return

    # ── 执行耗时操作 ──
    try:
        artifacts = do_expensive_work(key, content, build_dir)
        _update_manifest(build_dir, key, source_hash,
                         artifacts, status='completed')
        print(f"  [{key}] ✅ 完成", flush=True)
    except Exception as e:
        _update_manifest(build_dir, key, source_hash,
                         [], status='failed', error=str(e)[:200])
        print(f"  [{key}] ❌ 失败: {e}", flush=True)
        raise
```

### Shell 管线集成（简化版）

对于纯 Shell 管线（如 `build_docx.sh`），使用 `shasum` + 临时文件比对：

```bash
# ── 增量检查：Mermaid 图表渲染缓存 ──
MANIFEST="$BUILD_DIR/build_manifest.json"

_needs_rebuild() {
    local key="$1" file="$2"
    local current_hash
    current_hash=$(shasum -a 256 "$file" | awk '{print $1}')

    if [ -f "$MANIFEST" ]; then
        local stored_hash
        stored_hash=$(python3 -c "
import json, sys
m = json.load(open('$MANIFEST'))
print(m.get('items',{}).get('$key',{}).get('source_hash',''))
")
        if [ "$current_hash" = "$stored_hash" ]; then
            return 1  # 不需重建
        fi
    fi
    return 0  # 需要重建
}

_update_manifest() {
    local key="$1" hash="$2" status="$3"
    python3 -c "
import json, os, datetime
path = '$MANIFEST'
m = json.load(open(path)) if os.path.exists(path) else {'version':1,'items':{}}
m['items']['$key'] = {
    'status': '$status',
    'source_hash': '$hash',
    'built_at': datetime.datetime.now().isoformat()
}
tmp = path + '.tmp'
with open(tmp, 'w') as f: json.dump(m, f, indent=2)
os.replace(tmp, path)
"
}

# 使用示例：遍历 Mermaid 图表
for mmd_file in "$BUILD_DIR"/*.mmd; do
    key=$(basename "$mmd_file" .mmd)
    if _needs_rebuild "$key" "$mmd_file"; then
        echo "  [渲染] $key"
        mmdc -i "$mmd_file" -o "$BUILD_DIR/${key}.png" --scale 2
        hash=$(shasum -a 256 "$mmd_file" | awk '{print $1}')
        _update_manifest "$key" "$hash" "completed"
    else
        echo "  [跳过] $key"
    fi
done
```

### 设计决策总结

| 决策 | 原因 |
|------|------|
| 原子写入（`.tmp` + `os.replace`） | 防止崩溃时 JSON 文件损坏，保证读取者始终获取完整文件 |
| SHA-256 而非时间戳 | 时间戳无法检测同一秒内的变更；哈希基于内容，100% 准确 |
| 三条件重建门 | 任一条件不满足即触发重建，避免遍单疑难杂症 |
| 线程安全 `_manifest_lock` | 多线程并发处理时防止并发写入冲突 |
| 失败也写入 manifest | 记录失败原因，方便诊断；下次运行自动重试失败项 |
| 产物存在性检查 | 即使 status=completed，若磁盘产物被删除仍触发重建 |

> [!CAUTION] **绝对禁止 `rm -rf .build_xxx/`**
> 构建目录是增量构建的核心。删除将导致所有工作单元需要重新处理（全量 API / 渲染消耗）。如需重建特定项，直接删除对应 manifest 条目或使用 `--force` 参数。

---

## §12 线程安全陷阱模式 (C21 + C22)

### C21: ThreadPoolExecutor 闭包的名称解析陷阱

**问题**：模块 A 中定义延迟初始化的全局变量（如 `_MediaAssetsError`），模块 B 中在 `ThreadPoolExecutor` worker 函数的 `except` 子句中引用该名称，但未显式 `import`。

```python
# ❌ BAD — _assets.py 裸名引用，未 import
from _infra import _log, _load_media_assets  # _MediaAssetsError 未导入！

def _fetch_sfx_worker(seg):
    try:
        result = ma.fetch_media(...)
    except (_MediaAssetsError, OSError) as e:  # ← NameError in thread!
        _log(f"WARN: {e}")

with ThreadPoolExecutor(max_workers=3) as pool:
    pool.submit(_fetch_sfx_worker, seg)
```

**根因**：Python 在线程闭包中解析裸名时，只检查函数局部变量和定义时模块的 `globals()`。延迟初始化的跨模块变量不在当前模块 `globals()` 中 → `NameError`。主线程偶尔能通过模块属性链解析（`import _infra` + `_infra._MediaAssetsError`），但这在闭包中不可靠。

```python
# ✅ GOOD — 显式导入到当前模块命名空间
from _infra import (
    _log, _load_media_assets,
    _MediaAssetsError,  # 线程内 except 需显式导入
)
```

### C22: 多线程原子文件写入的 tmp 路径冲突

**问题**：多线程并发调用 `_save_manifest()`，每个线程写入同一个确定性 `.tmp` 路径。

```python
# ❌ BAD — 确定性 tmp 路径，多线程冲突
def _save_manifest(build_dir, manifest):
    path = Path(build_dir) / "asset_manifest.json"
    tmp = path.with_suffix(".json.tmp")      # 所有线程写同一个 tmp！
    with open(tmp, "w") as f:
        json.dump(manifest, f)
    os.replace(str(tmp), str(path))          # Thread B 的 tmp 已被 Thread A 消费 → FileNotFoundError
```

**时序分析**：
1. Thread A: `open(tmp, "w")` → 写入 → `close()`
2. Thread B: `open(tmp, "w")` → 覆盖 Thread A 内容 → `close()`
3. Thread A: `os.replace(tmp, path)` → ✅ 成功（但内容是 B 的）
4. Thread B: `os.replace(tmp, path)` → ❌ `FileNotFoundError`（tmp 已被 A 消费）

```python
# ✅ GOOD — Lock 序列化 + NamedTemporaryFile 唯一路径
import tempfile, threading
from contextlib import suppress

_manifest_lock = threading.Lock()

def _save_manifest(build_dir, manifest):
    path = Path(build_dir) / "asset_manifest.json"
    with _manifest_lock:
        fd = tempfile.NamedTemporaryFile(
            mode="w", suffix=".tmp", prefix="manifest_",
            dir=str(build_dir), delete=False, encoding="utf-8",
        )
        try:
            json.dump(manifest, fd, ensure_ascii=False, indent=2)
            fd.close()
            os.replace(fd.name, str(path))
        except BaseException:
            fd.close()
            with suppress(OSError):
                os.unlink(fd.name)
            raise
```

> [!NOTE] **实战案例**
> md2video v2.9 中 `_fetch_sfx_worker` 和 `refetch_for_segments` 均通过 `ThreadPoolExecutor` 并发调用 `media_assets.fetch_media()`，后者内部调用 `_save_manifest()`。单次构建触发 10+ 次 `FileNotFoundError` 和 4 次 `NameError`。修复后 8 并发线程压测零错误。

---

## 参考资料

- [[Python3 异步编程和异常处理的最佳实践]] — §9 异常层级、§10 Retry、§13 日志
- [[Python 访问 Gemini API 最佳实践]] — §1 Client、§3 防御式提取、§4 Trace、§5 多层容错
- [Google GenAI Python SDK](https://github.com/googleapis/python-genai)
