#!/usr/bin/env python3
"""
Mermaid Self-Check & Self-Heal (SCSH)
扫描 Markdown 中 Mermaid 图表，逐块渲染、审查、修复。

Usage:
    # 单文件模式（兼容旧接口）
    python3 mermaid_scsh.py --file target.md [--auto-fix] [--only-charts 0,2]

    # 多文件批量模式（启用章节级并发）
    python3 mermaid_scsh.py --files ch01.md ch02.md ch03.md [--auto-fix]

Env Vars:
    GOOGLE_API_KEY                   (必须) Gemini API Key
    MERMAID_SCSH_MODEL               (可选) 审查模型, 默认 gemini-3-flash-preview
    MERMAID_SCSH_MAX_RETRIES         (可选) 最大重试次数, 默认 2
    MERMAID_SCSH_PASS_SCORE          (可选) 通过分数阈值, 默认 7
    MERMAID_SCSH_CONCURRENCY         (可选) 图表级并发数, 默认 5
    MERMAID_SCSH_CHAPTER_CONCURRENCY (可选) 章节级并发数, 默认 3
"""

import argparse
import asyncio
import datetime
import functools
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google import genai


# ─────────────────────────────────────────────────────────────────────
# 配置常量
# ─────────────────────────────────────────────────────────────────────

## gemini-3-flash-preview
## gemini-3.1-pro-preview

DEFAULT_VISION_MODEL = "gemini-3-flash-preview"

GEMINI_MODEL = os.environ.get('MERMAID_SCSH_MODEL', DEFAULT_VISION_MODEL)
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
MAX_RETRIES = int(os.environ.get('MERMAID_SCSH_MAX_RETRIES', '2'))
GEMINI_REVIEW_TIMEOUT = int(os.environ.get('MERMAID_SCSH_REVIEW_TIMEOUT', '120'))
PASS_THRESHOLD = int(os.environ.get('MERMAID_SCSH_PASS_SCORE', '7'))
CONCURRENCY_CHART   = int(os.environ.get('MERMAID_SCSH_CONCURRENCY', '5'))
# 章节（文件）级并发：同时处理的 Markdown 文件数上限
# 当通过 --files 指定多个文件时生效；可通过 MERMAID_SCSH_CHAPTER_CONCURRENCY 覆盖
CONCURRENCY_CHAPTER = int(os.environ.get('MERMAID_SCSH_CHAPTER_CONCURRENCY', '3'))
# 代理配置：读取 ~/.zshrc 中标准的 http_proxy 环境变量
# ⚠️ 必须用 http:// 而非 https://，因为本地代理(Clash/V2Ray)监听端口不支持 TLS，
#    使用 https:// 会导致 httpx 尝试与代理握手 TLS → SSL: UNEXPECTED_EOF_WHILE_READING
PROXY_URL = os.environ.get('http_proxy', os.environ.get('HTTP_PROXY', 'none'))


# ─────────────────────────────────────────────────────────────────────
# 自定义异常层级
# ─────────────────────────────────────────────────────────────────────

class ScriptError(Exception):
    """mermaid_scsh 根异常。"""


class ConfigError(ScriptError):
    """配置 / 环境错误（API Key 缺失、mmdc 未安装等）。"""


class APIError(ScriptError):
    """Gemini API 调用异常。"""



def _is_retryable(api_error: APIError) -> bool:
    '''判断 APIError 是否值得重试。

    可重试: httpx 连接/读取错误, genai 429/500/503, JSONDecodeError
    不可重试: genai 400/401/403, ValueError, 无 __cause__
    '''
    import httpx
    from google.genai import errors as genai_errors

    cause = api_error.__cause__
    if cause is None:
        return False

    # httpx transport errors → retryable
    if isinstance(cause, (httpx.ConnectError, httpx.ReadTimeout,
                          httpx.ConnectTimeout, httpx.PoolTimeout)):
        return True

    # genai API errors → retryable for 429, 5xx
    if isinstance(cause, genai_errors.APIError):
        code = getattr(cause, 'code', None) or getattr(cause, 'status', None)
        if code and int(code) in (429, 500, 502, 503):
            return True
        return False

    # JSON parse error → retryable (Gemini sometimes returns partial JSON)
    if isinstance(cause, json.JSONDecodeError):
        return True

    return False




# ─────────────────────────────────────────────────────────────────────
# 构建日志基础设施
# ─────────────────────────────────────────────────────────────────────

_log_file = None
_build_dir = ''
_log_lock = threading.Lock()


def _setup_log_tee(build_dir: str) -> None:
    """初始化构建日志：后续 _log() 输出同时写入 build.log。"""
    global _log_file, _build_dir
    _build_dir = build_dir
    os.makedirs(build_dir, exist_ok=True)
    _log_file = open(
        os.path.join(build_dir, 'build.log'), 'w', encoding='utf-8',
    )


def _log(*args, **kwargs) -> None:
    """线程安全 print — 同步写入 stdout 与 build.log。"""
    kwargs.setdefault('flush', True)
    with _log_lock:
        print(*args, **kwargs)
        if _log_file:
            buf = io.StringIO()
            print(*args, **{**kwargs, 'file': buf, 'flush': False})
            _log_file.write(buf.getvalue())
            _log_file.flush()


def _trace_log(build_dir: str, action: str, payload) -> None:
    """将 API trace 写入 api_trace.log，不输出到控制台（线程安全）。"""
    with suppress(OSError):
        os.makedirs(build_dir, exist_ok=True)
    log_file = os.path.join(build_dir, 'api_trace.log')
    timestamp = datetime.datetime.now().isoformat()
    with _log_lock:
        with suppress(OSError):
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f'\n[{timestamp}] {action}\n')
                if isinstance(payload, str):
                    f.write(payload + '\n')
                else:
                    f.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
                f.write('-' * 80 + '\n')



# ─────────────────────────────────────────────────────────────────────
# Phase 0: Manifest I/O + 目录隔离 (v4.1)
# ─────────────────────────────────────────────────────────────────────

MANIFEST_VERSION = "4.1"
_manifest_lock = threading.Lock()

import hashlib


def _chart_dir(work_dir: str, file_stem: str) -> str:
    """按 MD 文件名创建隔离子目录。

    子目录名 = MD 文件名去掉 .md 扩展名（file_stem），
    实现多文件产物完全隔离。
    """
    d = os.path.join(work_dir, file_stem)
    os.makedirs(d, exist_ok=True)
    return d


def _load_manifest(chart_dir: str) -> dict:
    """加载 build_manifest.json，不存在则返回空结构。"""
    path = os.path.join(chart_dir, 'build_manifest.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                # Manifest 损坏时返回空结构，下次写入会覆盖
                return {'version': MANIFEST_VERSION, 'charts': {}}
    return {'version': MANIFEST_VERSION, 'charts': {}}


def _save_manifest(chart_dir: str, manifest: dict) -> None:
    """线程安全保存 manifest。"""
    with _manifest_lock:
        path = os.path.join(chart_dir, 'build_manifest.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)


def _code_hash(code: str) -> str:
    """计算 Mermaid 代码的短 SHA-256 hash。"""
    return 'sha256:' + hashlib.sha256(code.encode('utf-8')).hexdigest()[:16]


def _chart_needs_rebuild(manifest: dict, index: int,
                         code_hash: str, chart_dir: str) -> bool:
    """判定图表是否需要重建。

    Returns:
        True = 需要重建, False = 可跳过 (manifest hit)
    """
    key = str(index)
    ch = manifest.get('charts', {}).get(key)
    if not ch:
        return True                           # 新图表
    if ch.get('status') != 'passed':
        return True                           # 上次未通过
    if ch.get('code_hash') != code_hash:
        return True                           # 源代码已变更
    png = ch.get('png')
    if png and not os.path.exists(os.path.join(chart_dir, png)):
        return True                           # PNG 丢失
    return False


def _update_chart_manifest(chart_dir: str, index: int,
                           block: dict, result: dict) -> None:
    """单图表结果持久化到 manifest (线程安全)。

    注意: 此函数已持有 _manifest_lock，内部直接操作文件，
    不可调用 _save_manifest()（同一不可重入 Lock 会 deadlock）。
    """
    with _manifest_lock:
        manifest = _load_manifest(chart_dir)
        manifest['charts'][str(index)] = {
            'status': result['status'],
            'heading': block.get('heading', ''),
            'chart_type': block.get('chart_type', 'unknown'),
            'start_line': block.get('start_line', 0),
            'code_hash': _code_hash(result.get('code', '')),
            'overall_score': result.get('score', -1),
            'scores': {k: result.get(k) for k in
                       ('layout_score', 'color_score', 'readability_score')
                       if result.get(k) is not None},
            'png': f"chart_{index}.png",
            'attempts': len(result.get('history', [])) + 1,
            'history': result.get('history', []),
            'built_at': datetime.datetime.now().isoformat(),
        }
        # 直接写文件，避免调用 _save_manifest() 导致 deadlock
        path = os.path.join(chart_dir, 'build_manifest.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)


def _cleanup_chart_dir(chart_dir: str, blocks: list) -> None:
    """入口清理：删除不属于当前图表集的旧文件。

    仅在全量运行时调用，--only-charts 重入时跳过。
    保留 build_manifest.json / debrief.json / mermaid-font.css。
    """
    if not os.path.isdir(chart_dir):
        return
    valid = {f'chart_{i}.mmd' for i in range(len(blocks))}
    valid |= {f'chart_{i}.png' for i in range(len(blocks))}
    valid |= {'build_manifest.json', 'debrief.json', 'mermaid-font.css'}
    removed = 0
    for f in os.listdir(chart_dir):
        if f not in valid:
            with suppress(OSError):
                os.remove(os.path.join(chart_dir, f))
                removed += 1
    if removed:
        _log(f"  🧹 清理 {removed} 个旧产物")


def _parse_chart_indices(spec: str, total: int) -> set[int]:
    """解析 --only-charts 参数: "1,3,5-7" → {1,3,5,6,7}。"""
    indices: set[int] = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            if '-' in part and not part.startswith('-'):
                a, b = part.split('-', 1)
                indices.update(range(int(a), int(b) + 1))
            else:
                indices.add(int(part))
        except ValueError:
            continue  # 跳过无法解析的部分
    return {i for i in indices if 0 <= i < total}


def _generate_debrief(chart_dir: str, results: list[dict | None],
                      md_file: str, max_agent_retries: int = 2) -> dict:
    """生成结构化复盘报告，供上层 AI Agent 解析决策。

    Args:
        chart_dir: 图表产物隔离目录
        results: 各图表的 SCSH 结果 (None = 被跳过)
        md_file: 源 Markdown 文件路径
        max_agent_retries: 上层 Agent 最大重入次数

    Returns:
        复盘报告 dict，含 failed_charts 列表和可粘贴的 reentry_command
    """
    active = [(i, r) for i, r in enumerate(results) if r is not None]
    failed = [
        {
            'chart_index': i,
            'status': r['status'],
            'score': r.get('score', -1),
            'heading': r.get('heading', ''),
            'chart_type': r.get('chart_type', ''),
            'remaining_issues': [
                {'dimension': iss.get('dimension', ''),
                 'description': iss.get('description', '')}
                for iss in r.get('issues', [])
            ],
        }
        for i, r in active if r['status'] != 'passed'
    ]
    return {
        'file': md_file,
        'total_charts': len(active),
        'passed': sum(1 for _, r in active if r['status'] == 'passed'),
        'failed': len(failed),
        'all_passed': len(failed) == 0,
        'max_agent_retries': max_agent_retries,
        'failed_charts': failed,
        'reentry_command': (
            f"python3 mermaid_scsh.py --file \"{md_file}\" --auto-fix "
            f"--only-charts \"{','.join(str(c['chart_index']) for c in failed)}\""
        ) if failed else None,
    }



# ─────────────────────────────────────────────────────────────────────
# Prompt 模板加载（外置于 resources/，与 md2ppt 同模式）
# ─────────────────────────────────────────────────────────────────────

def _load_prompt(name: str, **kwargs) -> str:
    """从 resources/ 加载 Prompt 模板并替换占位符。

    空值安全：kwargs 中 None 的 value 替换为空字符串。
    使用 .replace() 逐个替换，避免 JSON `{}` 冲突。
    """
    prompt_dir = os.path.join(os.path.dirname(__file__), '..', 'resources')
    path = os.path.join(prompt_dir, name)
    with open(path, 'r', encoding='utf-8') as f:
        template = f.read()
    for key, value in kwargs.items():
        template = template.replace(f'{{{key}}}', str(value) if value else '')
    return template


REVIEW_PROMPT = _load_prompt(
    'REVIEW_PROMPT.md', pass_threshold=PASS_THRESHOLD,
)

# ─────────────────────────────────────────────────────────────────────
# Phase 1: 提取 Mermaid 代码块
# ─────────────────────────────────────────────────────────────────────

MERMAID_BLOCK_RE = re.compile(r'```mermaid\s*\n(.*?)```', re.DOTALL)
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# 图表类型关键字 → 显示名映射
_CHART_TYPE_MAP = {
    'graph': 'flowchart', 'flowchart': 'flowchart',
    'xychart-beta': 'xychart', 'pie': 'pie',
    'sankey-beta': 'sankey', 'timeline': 'timeline',
    'sequenceDiagram': 'sequence', 'mindmap': 'mindmap',
    'classDiagram': 'classDiagram', 'stateDiagram': 'stateDiagram',
    'erDiagram': 'erDiagram', 'gantt': 'gantt', 'gitgraph': 'gitgraph',
}

# 图表类型 → 模板文件名映射（用于审查时注入对应配色/布局规范）
_CHART_TEMPLATE_MAP = {
    'flowchart': 'flowchart.md',
    'xychart':   'bar_chart.md',    # xychart 使用 bar_chart 模板
    'pie':       'pie_chart.md',
    'sankey':    'sankey_chart.md',
    'timeline':  'timeline_chart.md',
    'sequence':  None,               # 暂无模板
    'mindmap':   None,
}


def _load_chart_template(chart_type: str) -> str | None:
    """加载图表类型对应的模板文件。无匹配时加载通用兜底模板 common_chart.md。"""
    tpl_name = _CHART_TEMPLATE_MAP.get(chart_type)
    if not tpl_name:
        tpl_name = 'common_chart.md'
        
    tpl_dir = os.path.join(
        os.path.dirname(__file__), '..', 'resources', 'chart_templates')
    tpl_path = os.path.join(tpl_dir, tpl_name)
    if not os.path.isfile(tpl_path):
        return None
    with open(tpl_path, 'r', encoding='utf-8') as f:
        return f.read()


def detect_chart_type(code: str) -> str:
    """从 Mermaid 代码检测图表类型（稳定跳过多行 init 块和 frontmatter）。"""
    # 移除多行 %%{init: ... }%% 块
    clean_code = re.sub(r'%%\{.*?\}%%', '', code, flags=re.DOTALL)
    # 移除顶部的 YAML frontmatter
    clean_code = re.sub(r'^---\s*\n.*?\n---\s*\n', '', clean_code, flags=re.DOTALL)

    for line in clean_code.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('%%'):
            continue
        for keyword, display in _CHART_TYPE_MAP.items():
            if stripped.startswith(keyword):
                # 确保是独立关键词（防止匹配到 node id 等）
                if len(stripped) == len(keyword) or not stripped[len(keyword)].isalpha():
                    return display
        break  # 仅检查第一行真正的有效代码
    return 'unknown'


def find_nearest_heading(md_content: str, block_start_pos: int) -> str:
    """从 Markdown 内容中提取距离代码块最近的上方标题。

    向上查找最近的 # 标题行，返回标题文本（去掉 # 前缀）。
    如果没有找到，返回空字符串。
    """
    text_before = md_content[:block_start_pos]
    headings = list(HEADING_RE.finditer(text_before))
    if headings:
        return headings[-1].group(2).strip()
    return ''


def extract_mermaid_blocks(md_content: str) -> list[dict]:
    """提取 Markdown 中所有 Mermaid 代码块，返回列表含位置信息。"""
    blocks = []
    for match in MERMAID_BLOCK_RE.finditer(md_content):
        code = match.group(1).strip()
        start_line = md_content[:match.start()].count('\n') + 1
        blocks.append({
            'code': code,
            'start_line': start_line,
            'start_pos': match.start(),
            'end_pos': match.end(),
            'raw_match': match.group(0),
            'heading': find_nearest_heading(md_content, match.start()),
            'chart_type': detect_chart_type(code),
        })
    return blocks


# ─────────────────────────────────────────────────────────────────────
# Phase 3a: 静态语法修复（L1 层）— 辅助函数
# ─────────────────────────────────────────────────────────────────────

def fix_timeline_colons(code: str) -> str:
    """替换 timeline 事件文本中的冒号（Mermaid 将 : 视为分隔符）。

    仅处理 `: ` 分隔符之后的文本部分中出现的冒号，
    避免误替换 Mermaid 语法本身的 `:` 分隔符。
    """
    lines = code.split('\n')
    result = []
    in_timeline = False

    for line in lines:
        stripped = line.strip()

        # 检测 timeline 块开始
        if stripped.startswith('timeline'):
            in_timeline = True
            result.append(line)
            continue

        if not in_timeline:
            result.append(line)
            continue

        # timeline 内的事件行格式: `    时间 : 事件文本` 或 `         : 补充说明`
        # 匹配第一个 ` : ` 分隔符，然后替换之后的冒号
        colon_match = re.match(r'^(\s*(?:\S.*?)?\s*:\s*)(.*)', line)
        if colon_match:
            prefix = colon_match.group(1)  # 保留分隔符语法
            event_text = colon_match.group(2)
            # 替换事件文本中的英文冒号和中文冒号
            event_text = event_text.replace('：', '—').replace(':', '—')
            result.append(prefix + event_text)
        else:
            result.append(line)

    return '\n'.join(result)


def fix_init_json(code: str) -> str:
    """修复 %%{init}%% 块中的 JSON 格式问题。

    常见问题：单引号→双引号、尾逗号、多行合并。
    """
    # 提取 %%{init: ... }%% 块
    init_match = re.search(r'%%\{init:\s*(.*?)\}%%', code, re.DOTALL)
    if not init_match:
        return code

    json_str = init_match.group(1).strip()

    # 单引号 → 双引号
    json_str = json_str.replace("'", '"')

    # 移除尾逗号（JSON 不允许）
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

    # 尝试解析验证
    try:
        parsed = json.loads(json_str)
        # 重新序列化为规范 JSON
        clean_json = json.dumps(parsed, ensure_ascii=False, indent=2)
        # 注意: Mermaid init 通常使用单引号，但双引号也可以
        return code[:init_match.start(1)] + clean_json + code[init_match.end(1):]
    except json.JSONDecodeError:
        # 无法修复，返回原始代码
        return code


def auto_quote_chinese(code: str) -> str:
    """自动为未加引号的中文节点标签包裹双引号。

    匹配模式: `ID[中文文本]` → `ID["中文文本"]`
    仅处理方括号内的中文，不处理已有引号的。
    """
    # 匹配 [未引号中文] 但排除已引号的 ["..."]
    def quote_if_chinese(match):
        content = match.group(1)
        # 已有引号，跳过
        if content.startswith('"') and content.endswith('"'):
            return f'[{content}]'
        # 包含中文字符，添加引号
        if re.search(r'[\u4e00-\u9fff]', content):
            return f'["{content}"]'
        return f'[{content}]'

    return re.sub(r'\[([^\]]+)\]', quote_if_chinese, code)


# ── Pre-render L1 预扫描：plotColorPalette 嵌套检查 ──
_XY_KEYS = {'plotColorPalette', 'backgroundColor', 'titleColor'}


def _fix_palette_nesting(code: str) -> str:
    """检测并修复 plotColorPalette 未嵌套在 xyChart 内的问题。

    采用 JSON AST 合并策略（非正则拼接），安全处理以下边界条件：
    - themeVariables 顶层存在 plotColorPalette（需迁移至 xyChart 内）
    - xyChart 对象已存在但为空或部分配置（合并而非覆盖）
    - xyChart 对象已正确配置（跳过）
    """
    if 'xychart-beta' not in code:
        return code
    if 'plotColorPalette' not in code:
        return code

    # 提取 %%{init: ... }%% 块
    init_match = re.search(r'%%\{init:\s*(.*?)\}%%', code, re.DOTALL)
    if not init_match:
        return code

    json_str = init_match.group(1).strip().replace("'", '"')
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)  # 移除尾逗号

    try:
        config = json.loads(json_str)
    except json.JSONDecodeError:
        return code  # 无法解析则不修复，交给 fix_init_json 处理

    tv = config.get('themeVariables', {})
    if not tv:
        return code

    # 检查 plotColorPalette 是否已在 xyChart 内
    xy = tv.get('xyChart', {})
    if 'plotColorPalette' in xy:
        return code  # 已正确嵌套，跳过

    # 从顶层收集需要迁移的 xychart 属性
    migrated = {}
    for key in _XY_KEYS:
        if key in tv:
            migrated[key] = tv.pop(key)

    if not migrated:
        return code  # 顶层无需迁移的属性

    # 合并到 xyChart（保留已有属性，仅补充缺失的）
    if 'xyChart' not in tv:
        tv['xyChart'] = {}
    for k, v in migrated.items():
        if k not in tv['xyChart']:  # 不覆盖已有值
            tv['xyChart'][k] = v

    config['themeVariables'] = tv
    clean_json = json.dumps(config, ensure_ascii=False, indent=2)

    # 回写到代码中（保持单引号风格以兼容 Mermaid）
    clean_json = clean_json.replace('"', "'")
    return code[:init_match.start(1)] + clean_json + code[init_match.end(1):]


# ─────────────────────────────────────────────────────────────────────
# Phase 2: L1 静态修复 — 错误分类与统一入口
# ─────────────────────────────────────────────────────────────────────

ERROR_FIXES = {
    'xychart_label': {
        'pattern': r"Expecting 'NUMBER_WITH_DECIMAL'.*got 'STR'",
        'fix': lambda code: re.sub(r'(bar|line)\s+\[.*?\]\s+\[', r'\1 [', code),
    },
    'timeline_colon': {
        'pattern': r'INVALID.*timeline',
        'fix': lambda code: fix_timeline_colons(code),
    },
    'json_format': {
        'pattern': r'%%{init.*Error|JSON',
        'fix': lambda code: fix_init_json(code),
    },
    'reserved_keyword': {
        'pattern': r'Unexpected token.*end|classDef end',
        'fix': lambda code: code.replace('classDef end', 'classDef endpoint'),
    },
    'chinese_unquoted': {
        'pattern': r'Parse error.*[\u4e00-\u9fff]',
        'fix': lambda code: auto_quote_chinese(code),
    },
    'sankey_newline': {
        'pattern': r'sankey.*error',
        'fix': lambda code: code.replace('sankey-beta\n', 'sankey-beta\n\n'),
    },
    'markdown_list_label': {
        'pattern': r'Unsupported markdown.*list',
        'fix': lambda code: re.sub(
            r'\["\s*(?:[\d\.]+[\.)\]]|[-*+])\s+',
            r'["',
            code
        ),
    },
}


def classify_error(stderr: str) -> str | None:
    """根据 mmdc stderr 输出分类错误类型。"""
    for name, rule in ERROR_FIXES.items():
        if re.search(rule['pattern'], stderr, re.IGNORECASE):
            return name
    return None


def apply_static_fix(code: str, error_type: str | None) -> str | None:
    """根据错误类型应用静态修复规则。返回修复后代码或 None。"""
    if error_type and error_type in ERROR_FIXES:
        return ERROR_FIXES[error_type]['fix'](code)
    return None


def l1_sanitize(code: str) -> str:
    """L1 统一清洗入口 — 每次渲染前和 Gemini fix 接收后各调一次。

    合并所有确定性修复规则，顺序执行：
    1. _fix_palette_nesting  (xychart 配色嵌套)
    2. fix_init_json         (%%{init}%% JSON 格式)
    3. fix_timeline_colons   (timeline 冒号)
    4. auto_quote_chinese    (中文标签引号)
    5. 其他 ERROR_FIXES 规则 (保留字、sankey 空行、列表标签)
    """
    code = _fix_palette_nesting(code)
    for error_type in ERROR_FIXES:
        fixed = apply_static_fix(code, error_type)
        if fixed and fixed != code:
            code = fixed
    return code


# ─────────────────────────────────────────────────────────────────────
# Phase 3: mmdc 逐块渲染
# ─────────────────────────────────────────────────────────────────────

def render_mermaid_block(code: str, index: int, work_dir: str = '.build_chart',
                        file_stem: str = '') -> dict:
    """渲染单个 Mermaid 代码块，返回渲染结果。"""
    # 确保工作目录隔离（避免并行执行时文件冲突）
    os.makedirs(work_dir, exist_ok=True)
    # v4.1: 目录隔离后不再需要 file_stem 前缀
    mmd_path = os.path.join(work_dir, f'chart_{index}.mmd')
    png_path = os.path.join(work_dir, f'chart_{index}.png')

    # CJK 字体 CSS 注入（确保中文标签不渲染为豆腐块）
    # 字体优先级：macOS 原生 PingFang SC 最高优先（锐利 + 零安装），
    # 其次 Noto Sans SC（跨平台保底），最后 Microsoft YaHei（Windows 回退）
    css_path = os.path.join(work_dir, 'mermaid-font.css')
    if not os.path.exists(css_path):
        with open(css_path, 'w', encoding='utf-8') as f:
            f.write(
                "* { font-family: 'PingFang SC', 'Noto Sans SC', "
                "'Microsoft YaHei', sans-serif !important; }\n"
            )

    with open(mmd_path, 'w', encoding='utf-8') as f:
        f.write(code)

    try:
        result = subprocess.run(
            ['mmdc', '-i', mmd_path, '-o', png_path,
             '--outputFormat', 'png', '--scale', '2',
             '--backgroundColor', '#FAFAFA',
             '--width', '1200',
             '--cssFile', css_path],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'png_path': None,
            'stderr': 'mmdc render timeout (>30s)',
            'returncode': -1,
            'error_type': None,
        }

    success = result.returncode == 0 and os.path.exists(png_path)

    # L2: 检查空白/错误图（Mermaid 有时输出 "Syntax error in graph" 图片）
    if success and os.path.getsize(png_path) < 5000:
        success = False

    return {
        'success': success,
        'png_path': png_path if success else None,
        'stderr': result.stderr,
        'returncode': result.returncode,
        'error_type': classify_error(result.stderr) if not success else None,
    }


# ─────────────────────────────────────────────────────────────────────
# Phase 4: Gemini Vision 审查
# ─────────────────────────────────────────────────────────────────────

def _build_gemini_client() -> "genai.Client":
    """构建带代理、超时和重试配置的 Gemini Client（单例复用）。

    代理: 读取 http_proxy 环境变量 (设 'none' 禁用)
    重试: 网络层 3 次指数退避重试 (ConnectError / ReadError 等)
    超时: connect 15s / read 120s / write 15s / pool 15s
    """
    import httpx
    from google import genai
    from google.genai import types

    timeout = httpx.Timeout(connect=15.0, read=120.0, write=15.0, pool=15.0)

    transport_kwargs = {
        'retries': 3,  # httpcore 层重试：覆盖 ConnectError/ConnectTimeout
    }

    if PROXY_URL and PROXY_URL.lower() != 'none':
        http_client = httpx.Client(
            proxy=PROXY_URL,
            timeout=timeout,
            transport=httpx.HTTPTransport(**transport_kwargs),
        )
    else:
        http_client = httpx.Client(
            timeout=timeout,
            transport=httpx.HTTPTransport(**transport_kwargs),
        )

    return genai.Client(
        api_key=GOOGLE_API_KEY,
        http_options=types.HttpOptions(httpx_client=http_client),
    )


# 延迟初始化的全局 Client
_gemini_client = None


def _get_gemini_client() -> "genai.Client":
    """获取或创建全局 Gemini Client。"""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = _build_gemini_client()
    return _gemini_client


def _safe_response_text(response) -> str:
    """安全提取 Gemini 非流式 response 的文本（遵循 Script-Coder 标准模式）。

    逐层检查 candidates → content → parts → text，
    每层提供诊断信息。

    Raises:
        APIError: 任何层级校验失败
    """
    candidates = getattr(response, 'candidates', None)
    if not candidates:
        raise APIError(
            f"Empty candidates "
            f"(prompt_feedback={getattr(response, 'prompt_feedback', '?')})"
        )
    candidate = candidates[0]
    finish = getattr(candidate, 'finish_reason', None)

    if not getattr(candidate, 'content', None):
        raise APIError(f"No content (finish_reason={finish})")

    parts = candidate.content.parts
    if not parts:
        raise APIError(f"Empty parts (finish_reason={finish})")

    for part in parts:
        if hasattr(part, 'text') and part.text:
            return part.text

    raise APIError(f"All {len(parts)} parts have no text (finish_reason={finish})")


def review_with_gemini(png_path: str, mermaid_code: str,
                      retry_history: list[dict] | None = None,
                      chart_type: str = '') -> dict:
    """使用 Gemini Vision 审查渲染后的 Mermaid 图表。

    注意：本函数**不**自带 API 重试装饰器，重试由上层 check_and_fix_block 循环控制，
    避免双层重试 N×M 放大（导致单图表等待 >10 分钟）。

    容错：
    - L0 Transport: httpcore 层 3 次重试 (ConnectError / ReadError)
    - 代理: 读取 http_proxy 环境变量 (设 'none' 禁用)
    - 超时: connect 15s / read 120s → 整个请求必须在 120s 内完成
    - 非流式调用 (generate_content): 单次 HTTP 响应，
      httpx read timeout 直接覆盖全请求，无 orphan thread 风险
    - 历史上下文: 通过 retry_history 注入前几轮修复 issues，
      引导 Gemini 避免重复修复方向、防止振荡
    - 图表模板: 通过 chart_type 加载对应的配色/布局模板，
      作为 fix_code 的参考标准
    """
    from google.genai import types, errors as genai_errors
    import httpx

    client = _get_gemini_client()

    try:
        with open(png_path, 'rb') as f:
            image_bytes = f.read()
    except OSError as e:
        raise APIError(f"无法读取渲染图片 {png_path}: {e}") from e

    # ── SYSTEM INSTRUCTION: 全局规则 (REVIEW_PROMPT) 注入 system_instruction ──
    # ── USER PROMPT:        单次请求的动态上下文（图像 + 历史 + 代码 + 模板） ──

    user_prompt = "请依据系统指令，对附带的 Mermaid 图表渲染结果进行评审。"

    # 注入历史修复记录（仅当存在 gemini_fix 类型历史时）
    gemini_history = [
        h for h in (retry_history or [])
        if h.get('type') == 'gemini_fix'
    ]
    if gemini_history:
        user_prompt += (
            "\n\n# ⚠️ 历史修复记录（本图表已经历多次修复尝试）\n"
            "以下是之前的修复尝试记录。请务必：\n"
            "1. **避免重复**已尝试过但失败的修复方向\n"
            "2. **关注趋势**：评分是否在改善？哪些维度仍然卡住？\n"
            "3. **防止振荡**：如果上一轮修复了 A 但引入了 B，"
            "这一轮必须同时兼顾 A 和 B\n\n"
        )
        for h in gemini_history:
            user_prompt += (
                f"- **第 {h['attempt']} 次** "
                f"(评分 {h.get('score', '?')}/10): "
            )
            issues = h.get('issues', [])
            if issues:
                issue_strs = [
                    f"{i['dimension']}({i['severity']}): "
                    f"{i['description'][:50]}"
                    for i in issues[:3]
                ]
                user_prompt += '; '.join(issue_strs)
            user_prompt += '\n'

    user_prompt += (
        f"\n\n原始 Mermaid 代码（供修复参考）：\n"
        f"```mermaid\n{mermaid_code}\n```"
    )

    # 注入图表类型对应的配色/布局模板
    chart_template = _load_chart_template(chart_type)
    if chart_template:
        user_prompt += (
            f"\n\n# 🎨 本图表类型 ({chart_type}) 的标准配色与布局模板\n"
            f"生成 fix_code 时**必须严格遵循**此模板的 %%{{init}}%% 配置、"
            f"classDef 定义和布局规范：\n\n"
            f"{chart_template}"
        )

    # 内容列表：图像 Part + 用户消息文本
    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
        user_prompt,
    ]
    gen_config = types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type='application/json',
        system_instruction=REVIEW_PROMPT,
        max_output_tokens=8192,
    )

    # 非流式调用：httpx read=120s 直接覆盖全请求，无 orphan thread 风险
    if _build_dir:
        _trace_log(_build_dir, '[Gemini Review] Request', {
            'model': GEMINI_MODEL,
            'png': png_path,
            'code_len': len(mermaid_code),
            'temperature': gen_config.temperature,
            'system_instruction_len': len(REVIEW_PROMPT),
            'user_prompt': user_prompt,
        })
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=gen_config,
        )
    except (genai_errors.APIError, httpx.HTTPError) as e:
        raise APIError(
            f"Gemini API 调用失败 ({type(e).__name__}): {e}"
        ) from e

    # ── C5: 防御式 Response 提取（Script-Coder 标准模式）──
    try:
        full_text = _safe_response_text(response)
    except Exception as e:
        raise APIError(f"从 candidates 提取 text 失败 (结构异常): {e}") from e


    # 清理可能存在的 Markdown 代码块标记并解析 JSON
    clean_text = full_text.strip()
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    if clean_text.startswith("```"):
        clean_text = clean_text[3:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
    clean_text = clean_text.strip()

    try:
        result = json.loads(clean_text, strict=False)
        return result
    except json.JSONDecodeError as e:
        # Heuristic fix for truncated JSON outputs (often truncated inside an issues array element's string value)
        try:
            import re
            repaired_text = clean_text
            
            # The most common failure is truncated text inside the "issues" array.
            # Strategy: Extract the valid top-level fields, and use regex to extract all completely well-formed objects in the issues list.
            
            # 1. Grab `overall_pass` and `overall_score` using regex to be safe
            pass_match = re.search(r'"overall_pass"\s*:\s*(true|false)', repaired_text)
            score_match = re.search(r'"overall_score"\s*:\s*(\d+)', repaired_text)
            
            overall_pass = True if (pass_match and pass_match.group(1) == 'true') else False
            overall_score = int(score_match.group(1)) if score_match else 5
            
            # 2. Extract valid issue objects
            # We look for something that looks like: { "dimension": ..., "severity": ..., "description": ... }
            # As long as there are no nested braces inside description (which Gemini shouldn't generate here), this simple regex works
            issues = []
            valid_issue_blocks = re.findall(r'(\{\s*"dimension"(?:.*?)\})', repaired_text, re.DOTALL)
            for block in valid_issue_blocks:
                try:
                    # We only keep it if it is a completely valid JSON object by itself
                    issues.append(json.loads(block, strict=False))
                except json.JSONDecodeError:
                    pass
            
            # Reconstruct the result manually
            result = {
                "overall_pass": overall_pass,
                "overall_score": overall_score,
                "issues": issues,
                "fix_code": ""
            }
            
            # Attempt to extract fix_code if it was rendered completely
            fix_code_match = re.search(r'"fix_code"\s*:\s*"(.*?)"\s*\}', repaired_text, re.DOTALL)
            if fix_code_match:
                 result["fix_code"] = fix_code_match.group(1).replace('\\"', '"').replace('\\n', '\n')
            
            if _build_dir:
                _trace_log(_build_dir, '[Gemini Review] JSON Autofix (Regex Reconstruct)', {
                     'extracted_issues': len(issues),
                     'original_len': len(clean_text)
                })
            return result
        except Exception as repair_e:
            raise APIError(f"Gemini 返回非法 JSON ({e}): {full_text[:200]}") from repair_e

# ─────────────────────────────────────────────────────────────────────
# Phase 5: 自检修复循环 — 3-Step Pipeline
# ─────────────────────────────────────────────────────────────────────

def _chart_label(block: dict, index: int) -> str:
    """为日志生成可读的图表标识，格式: `#3 「标题」 (pie · 行 125)`。"""
    heading = block.get('heading', '')
    if heading and len(heading) > 40:
        heading = heading[:37] + '…'
    chart_type = block.get('chart_type', 'unknown')
    line = block.get('start_line', '?')
    label = f"#{index+1}"
    if heading:
        label += f" 「{heading}」"
    label += f" ({chart_type} · 行 {line})"
    return label


def _extract_scores(review: dict) -> dict:
    """从 Gemini review 结果中提取评分字段。"""
    return {
        'layout_score': review.get('layout_score'),
        'color_score': review.get('color_score'),
        'readability_score': review.get('readability_score'),
        'chart_type': review.get('chart_type', 'unknown'),
    }


def _print_issues(label: str, review: dict) -> None:
    """输出 Gemini 审查的完整 issues 列表（不截断）。"""
    if review.get('summary'):
        _log(f"  [{label}][总评] {review['summary']}")
    for idx, issue in enumerate(review.get('issues', []), 1):
        severity = issue.get('severity', '?')
        dimension = issue.get('dimension', '?')
        desc = issue.get('description', '')
        icon = '🔴' if severity == 'critical' else '🟡' if severity == 'warning' else 'ℹ️'
        _log(f"  [{label}][问题 {idx}] {icon} [{dimension}] {desc}")
        fix_sug = issue.get('fix_suggestion', '')
        if fix_sug:
            _log(f"  [{label}][建议 {idx}] 💡 {fix_sug}")


def _writeback_block(md_file: str, block: dict, new_code: str) -> None:
    """将修复后的代码立即回写到 Markdown 源文件中。

    基于 block 的 start_pos/end_pos 定位原始代码块，
    用 new_code 替换后写回文件。
    """
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    new_block = f"```mermaid\n{new_code}\n```"
    content = content[:block['start_pos']] + new_block + content[block['end_pos']:]
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(content)


def check_and_fix_block(block: dict, index: int,
                        work_dir: str,
                        max_retries: int = MAX_RETRIES,
                        pass_threshold: int = PASS_THRESHOLD,
                        file_stem: str = '',
                        md_file: str = '',
                        auto_fix: bool = False,
                        chart_dir: str = '') -> dict:
    """单图表自检修复 — 3-Step Pipeline。

    流程:
        for each attempt:
            Step 1: l1_sanitize(code) → mmdc 渲染
            Step 2: Gemini Vision 审查 (PNG + code) → pass/fail
            Step 3: 校验 fix_code → 更新 best → 下一轮

    返回:
        passed             — 审查通过
        failed             — 渲染失败且无法修复
        needs_intervention — 重试耗尽 / API 异常 / 无修复代码
    """
    code = block['code']
    best = {'code': code, 'score': -1}
    prev_score = -1
    history: list[dict] = []
    label = _chart_label(block, index)

    for attempt in range(1, max_retries + 2):  # 首次 + max_retries 次重试

        # ── Step 1: L1 Sanitize + Render ──
        code = l1_sanitize(code)
        _log(f"  [{label}] 第 {attempt} 次渲染...", end=' ')
        render = render_mermaid_block(code, index, work_dir, file_stem=file_stem)

        if not render['success']:
            _log(f"❌ 渲染失败 ({render.get('error_type', 'unknown')})")
            history.append({
                'attempt': attempt, 'type': 'render_error', 'layer': 'L2',
                'error_type': render.get('error_type', 'unknown'),
                'error_detail': render['stderr'][:300],
                'action': '渲染发生语法错误'
            })
            if attempt > 1 and best['score'] >= 0:
                _log(f"  [{label}][回退] 撤销引起语法错误的修复，回滚到历史最佳版本 (score={best['score']})")
                code = best['code']
                continue
            else:
                result = {
                    'status': 'failed', 'reason': 'render_error',
                    'code': best['code'] if best['score'] >= 0 else code,
                    'stderr': render['stderr'][:500], 'history': history,
                }
                if chart_dir:
                    _update_chart_manifest(chart_dir, index, block, result)
                return result

        png_size = os.path.getsize(render['png_path']) if render['png_path'] else 0
        _log(f"✅ ({png_size:,} bytes)")

        # ── Step 2: Gemini Review (PNG + code) ──
        _log(f"  [{label}][审查] Gemini Vision 评估中...", end=' ')
        try:
            review = review_with_gemini(
                render['png_path'], code, retry_history=history,
                chart_type=block.get('chart_type', ''))
        except APIError as e:
            _log(f"❌ API 异常: {e}")
            import traceback
            if _build_dir:
                _trace_log(_build_dir, '[Gemini Review] Exception', {
                    'error_type': type(e).__name__,
                    'error_message': str(e)[:500],
                    'cause': str(e.__cause__)[:300] if e.__cause__ else None,
                    'traceback': traceback.format_exc(),
                })
            history.append({
                'type': 'gemini_error',
                'attempt': attempt,
                'layer': 'L3',
                'action': f'API 调用异常: {type(e).__name__}: {str(e)[:200]}',
                'error_type': type(e).__name__,
            })

            if attempt <= max_retries and _is_retryable(e):
                import time
                wait_secs = 1.0 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                _log(f"  [{label}][重试] 捕获可恢复异常 (JSONDecodeError 等)，等待 {wait_secs:.1f}s 进行第 {attempt+1} 次尝试...")
                time.sleep(wait_secs)
                continue

            result = {
                'status': 'needs_intervention', 'reason': 'gemini_api_error',
                'code': best['code'] if best['score'] >= 0 else code,
                'history': history,
            }
            if chart_dir:
                _update_chart_manifest(chart_dir, index, block, result)
            return result

        score = review.get('overall_score', 0)
        scores = _extract_scores(review)
        layout = scores.get('layout_score', '?')
        color = scores.get('color_score', '?')
        readability = scores.get('readability_score', '?')

        if review.get('overall_pass'):
            status_msg = f"经 {attempt-1} 次修复后通过" if attempt > 1 else "一次通过"
            _log(f"✅ {score}/10 (布局 {layout} · 配色 {color} · 可读性 {readability})")
            _log(f"  [{label}][结果] {status_msg} ✅")
            result = {
                'status': 'passed', 'code': code,
                'score': score, 'history': history, **scores,
            }
            if chart_dir:
                _update_chart_manifest(chart_dir, index, block, result)
            return result

        # 未通过
        issue_count = len(review.get('issues', []))
        _log(f"⚠️ {score}/10 (布局 {layout} · 配色 {color} · 可读性 {readability}) · {issue_count} 个问题")
        _print_issues(label, review)

        # ── Step 3: Validate Fix & Prepare Next ──
        if score > best['score']:
            best = {'code': code, 'score': score}

        # Score Regression Guard: 检测分数下降并回滚
        if prev_score > 0 and score < prev_score:
            _log(
                f'  [{label}][回退] 分数回归: {prev_score} → {score}，'
                f'回滚到历史最佳版本 (score={best["score"]})'
            )
            history.append({
                'type': 'score_regression',
                'attempt': attempt,
                'layer': 'L3',
                'prev_score': prev_score,
                'score': score,
                'best_score': best['score'],
                'action': f'分数回归 {prev_score} → {score}，回滚到最佳版本',
            })
            code = best['code']
            prev_score = score
            continue
        prev_score = score

        fix_code = review.get('fix_code')
        if not fix_code:
            _log(f"  [{label}][终止] Gemini 未生成修复代码 → needs_intervention ⚠️")
            result = {
                'status': 'needs_intervention', 'code': best['code'],
                'score': best['score'], 'issues': review.get('issues', []),
                'history': history, **scores,
            }
            if chart_dir:
                _update_chart_manifest(chart_dir, index, block, result)
            return result

        # L1 校验 Gemini 修复代码
        fix_code = l1_sanitize(fix_code)
        _log(f"  [{label}][L3 修复] Gemini 生成修复代码 ({len(fix_code)} chars)，"
             f"应用第 {attempt} 次修复...")

        # ── 即时回写已禁用 ─────────────────────────────────────────────────
        # 并发模式下即时回写缺少文件级写锁，且与 main_async_single 末尾的
        # 倒序批量回写（apply_fixes_to_markdown）构成双轨竞争：
        # 批量回写基于 read 时快照，会覆盖即时写入的结果。
        # 统一使用 main_async_single 末尾的倒序批量回写作为唯一写路径。
        # ──────────────────────────────────────────────────────────────────
        # if auto_fix and md_file:
        #     if score >= best['score']:
        #         _writeback_block(md_file, block, fix_code)
        #         ...

        history.append({
            'attempt': attempt, 'type': 'gemini_fix', 'layer': 'L3',
            'score': score,
            'issues': [
                {k: i.get(k, '') for k in
                 ('dimension', 'severity', 'description', 'fix_suggestion')}
                for i in review.get('issues', [])
            ],
            'action': f"Gemini 评分 {score}/10，生成修复代码",
        })
        code = fix_code  # 下一轮 Step 1 的 l1_sanitize 会再次清洗

    # 循环耗尽
    _log(f"  [{label}][终止] 已达最大重试 ({max_retries}) → needs_intervention ⚠️")
    result = {
        'status': 'needs_intervention', 'code': best['code'],
        'score': best['score'], 'history': history,
    }
    if chart_dir:
        _update_chart_manifest(chart_dir, index, block, result)
    return result



async def async_check_and_fix_block(
    block: dict, index: int, work_dir: str,
    semaphore: asyncio.Semaphore, **kwargs,
) -> dict:
    """异步包装 check_and_fix_block()，受 semaphore 限流。

    采用 md2ppt async_process_chapter() 同构模式：
    run_in_executor 将 CPU/IO-bound 同步函数卸载到线程池。
    """
    async with semaphore:
        loop = asyncio.get_running_loop()
        fn = functools.partial(
            check_and_fix_block,
            block, index, work_dir, **kwargs,
        )
        result = await loop.run_in_executor(None, fn)
        result['start_line'] = block['start_line']
        result['heading'] = block.get('heading', '')
        return result


# ─────────────────────────────────────────────────────────────────────
# Phase 6: 结果汇报与回写
# ─────────────────────────────────────────────────────────────────────

def apply_fixes_to_markdown(
    md_content: str, blocks: list[dict], results: list[dict],
) -> str:
    """将修复后的代码回写到 Markdown 中（倒序替换，保持偏移正确）。

    回写条件：
    - status == 'passed': 审查通过的修复版本
    - status == 'needs_intervention': 历史最高分版本（best_code），
      即使未完全通过审查，也保留 Gemini 优化过的最佳版本
    """
    for block, result in sorted(
        zip(blocks, results), key=lambda x: x[0]['start_pos'], reverse=True,
    ):
        should_write = (
            result['status'] in ('passed', 'needs_intervention', 'failed')
            and result.get('code', '') != block['code']
        )
        if should_write:
            new_block = f"```mermaid\n{result['code']}\n```"
            md_content = (
                md_content[:block['start_pos']]
                + new_block
                + md_content[block['end_pos']:]
            )
    return md_content


def generate_report(
    results: list[dict], md_file: str,
    gemini_model: str = GEMINI_MODEL, max_retries: int = MAX_RETRIES,
) -> str:
    """生成完整的 SCSH 自检修复报告。包含总览、修复详情和失败报告。"""
    total = len(results)
    passed = sum(1 for r in results if r['status'] == 'passed')
    first_pass = sum(
        1 for r in results if r['status'] == 'passed' and not r.get('history')
    )
    auto_fixed = sum(
        1 for r in results if r['status'] == 'passed' and r.get('history')
    )
    failed = sum(
        1 for r in results if r['status'] in ('failed', 'needs_intervention')
    )
    multi_fix = [
        r for r in results
        if r['status'] == 'passed' and len(r.get('history', [])) >= 2
    ]

    # ── 总览表 ──
    report = f"""
## 📊 Mermaid SCSH 自检报告

| 项目 | 详情 |
| ---- | ---- |
| 文件 | `{md_file}` |
| 审查模型 | `{gemini_model}` |
| 图表总数 | {total} |
| ✅ 一次通过 | {first_pass} |
| 🔧 自动修复后通过 | {auto_fixed} (其中 {len(multi_fix)} 个经 ≥2 次修复) |
| ⚠️ 需人工干预 | {failed} |
"""

    # ── 多次修复图表的修复历程报告 ──
    if multi_fix:
        report += "\n---\n\n### 🔧 多次修复图表详情\n\n"
        report += "> 以下图表经历了 2 次或以上修复才通过审查。\n"
        report += "> 总结修复原因与方案，供后续图表生成时参考。\n\n"

        for r in multi_fix:
            idx = results.index(r) + 1
            report += f"#### 图表 #{idx} (行 {r.get('start_line', '?')}) — "
            report += (
                f"{r.get('chart_type', '未知类型')} · "
                f"最终评分 {r.get('score', '?')}/10\n\n"
            )
            report += f"| 修复次数 | {len(r['history'])} 次 |\n"
            report += "| ---- | ---- |\n"

            # 逐次修复历程
            report += "\n**修复历程**：\n\n"
            report += "| 次数 | 层级 | 类型 | 问题摘要 | 修复动作 |\n"
            report += "| ---- | ---- | ---- | -------- | -------- |\n"

            for h in r['history']:
                attempt = h.get('attempt', '?')
                layer = h.get('layer', '?')
                fix_type = h.get('type', '?')
                if fix_type == 'syntax_fix':
                    issue_summary = h.get('error_type', '语法错误')
                elif fix_type == 'gemini_fix':
                    issues = h.get('issues', [])
                    if issues:
                        issue_summary = '; '.join(
                            f"{i['dimension']}({i['severity']}): "
                            f"{i['description'][:40]}"
                            for i in issues[:2]
                        )
                    else:
                        issue_summary = f"评分 {h.get('score', '?')}/10"
                else:
                    issue_summary = h.get('error_detail', '')[:60]
                action = h.get('action', '自动修复')
                report += (
                    f"| {attempt} | {layer} | {fix_type} "
                    f"| {issue_summary} | {action} |\n"
                )

            # 修复根因总结
            root_causes = set()
            for h in r['history']:
                if h.get('type') == 'syntax_fix':
                    root_causes.add(
                        f"语法问题 ({h.get('error_type', '未知')})"
                    )
                elif h.get('type') == 'gemini_fix':
                    for i in h.get('issues', []):
                        root_causes.add(
                            f"{i['dimension']} — {i['description'][:50]}"
                        )

            report += "\n**根因总结**：\n"
            for cause in root_causes:
                report += f"- {cause}\n"
            report += "\n"

    # ── 失败图表的诊断报告 ──
    failed_results = [
        (i, r) for i, r in enumerate(results)
        if r['status'] in ('failed', 'needs_intervention')
    ]

    if failed_results:
        report += "\n---\n\n### ⚠️ 需人工干预图表详情\n\n"
        report += (
            f"> 以下图表在 {max_retries} 次自动修复后仍未通过审查，"
            "需要人工排查。\n\n"
        )

        for idx, r in failed_results:
            report += f"#### 图表 #{idx + 1} (行 {r.get('start_line', '?')})\n\n"

            if r['status'] == 'failed':
                reason = r.get('reason', '未知')
                if reason == 'gemini_api_error':
                    report += "- **状态**：❌ Gemini Vision 审查失败（渲染成功但 API 调用异常）\n"
                    report += f"- **失败原因**：{reason}\n"
                    report += (
                        f"- **异常信息**：\n"
                        f"```\n{r.get('stderr', '无输出')}\n```\n"
                    )
                else:
                    report += "- **状态**：❌ 渲染失败（无法生成有效 PNG）\n"
                    report += f"- **失败原因**：{reason}\n"
                    report += (
                        f"- **mmdc stderr**：\n"
                        f"```\n{r.get('stderr', '无输出')}\n```\n"
                    )
            else:
                report += (
                    f"- **状态**：⚠️ 审查未通过"
                    f"（已用尽 {max_retries} 次重试）\n"
                )
                report += f"- **最终评分**：{r.get('score', 'N/A')}/10"
                report += f" (布局 {r.get('layout_score', '?')}"
                report += f" / 配色 {r.get('color_score', '?')}"
                report += f" / 可读性 {r.get('readability_score', '?')})\n"
                report += f"- **图表类型**：{r.get('chart_type', '未知')}\n"

            # 残留问题列表
            if r.get('issues'):
                report += "\n**残留问题**：\n\n"
                report += "| 维度 | 严重度 | 描述 | 修复建议 |\n"
                report += "| ---- | ------ | ---- | -------- |\n"
                for issue in r['issues']:
                    report += (
                        f"| {issue.get('dimension', '')} "
                        f"| {issue.get('severity', '')} "
                        f"| {issue.get('description', '')[:60]} "
                        f"| {issue.get('fix_suggestion', '—')[:60]} |\n"
                    )

            # 修复历程回顾
            if r.get('history'):
                report += (
                    f"\n**修复历程** ({len(r['history'])} 次尝试)：\n\n"
                )
                for h in r['history']:
                    report += (
                        f"- **第 {h.get('attempt', '?')} 次** "
                        f"({h.get('layer', '?')}): "
                        f"{h.get('action', '自动修复')}\n"
                    )

            report += "\n**建议行动**：\n"
            if r['status'] == 'failed':
                report += (
                    "1. 检查 Mermaid 语法是否使用了不支持的特性\n"
                    "2. 在 [Mermaid Live Editor](https://mermaid.live) "
                    "中调试源代码\n"
                    "3. 参考 SCSH 技术方案 §6 优化策略库中"
                    "对应图表类型的修复规则\n"
                )
            else:
                report += (
                    "1. 查看上方残留问题表格，手动调整对应参数\n"
                    "2. 重点关注 Critical 级问题\n"
                    "3. 修复后重新运行 SCSH 验证\n"
                )
            report += "\n"

    return report


# ─────────────────────────────────────────────────────────────────────
# CLI 主入口 (v4.1)
# ─────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI 入口：解析参数、环境检查后启动 async 主循环。"""
    parser = argparse.ArgumentParser(
        description='Mermaid SCSH v4.2 — 自检与自修复管线',
    )
    # ── 文件输入（两种方式，互斥但兼容）──
    file_group = parser.add_mutually_exclusive_group(required=True)
    file_group.add_argument('--file', help='单个目标 Markdown 文件路径')
    file_group.add_argument(
        '--files', nargs='+', metavar='FILE',
        help='多个目标 Markdown 文件路径（启用章节级并发）',
    )
    parser.add_argument(
        '--max-retries', type=int, default=MAX_RETRIES,
        help=f'单图表最大重试次数 (default: {MAX_RETRIES})',
    )
    parser.add_argument(
        '--pass-score', type=int, default=PASS_THRESHOLD,
        help=f'通过分数阈值 (default: {PASS_THRESHOLD})',
    )
    parser.add_argument(
        '--auto-fix', action='store_true',
        help='自动回写修复到源文件',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='仅审查不修改',
    )
    parser.add_argument(
        '--model', default=GEMINI_MODEL,
        help=f'Gemini 模型名称 (default: {GEMINI_MODEL})',
    )
    parser.add_argument(
        '--work-dir', default='.build_chart',
        help='构建根目录 (default: .build_chart, 相对于源文件目录)',
    )
    parser.add_argument(
        '--only-charts', type=str, default=None,
        help='仅处理指定图表 (0-based index, 如 "1,3" 或 "1-3"，仅单文件模式)',
    )
    args = parser.parse_args()

    # 统一为列表
    if args.file:
        args.files = [args.file]
    # args.files 现在一定存在

    # ── 环境检查（同步，失败不需要构建目录）──
    if not os.environ.get('GOOGLE_API_KEY'):
        raise ConfigError("环境变量 GOOGLE_API_KEY 未设置")
    if not shutil.which('mmdc'):
        raise ConfigError(
            "mmdc 未安装, 执行: npm install -g @mermaid-js/mermaid-cli"
        )
    for fp in args.files:
        if not os.path.exists(fp):
            raise ConfigError(f"文件不存在: {fp}")

    # ── 启动异步主循环 ──
    asyncio.run(main_async(args))


async def main_async(args: argparse.Namespace) -> None:
    """异步主入口：章节级并发（v4.2）+ 图表级并发（v4.1）。

    v4.2 新增:
    - --files 多文件批量模式，章节级并发 CONCURRENCY_CHAPTER (默认 3)
    - --file 单文件模式向后兼容
    - 两级并发常量均在脚本头部可配置
    """
    chapter_sem = asyncio.Semaphore(CONCURRENCY_CHAPTER)
    total_files = len(args.files)
    if total_files > 1:
        print(f"📚 章节级并发处理 {total_files} 个文件 "
              f"(max {CONCURRENCY_CHAPTER} 章节并发 × max {CONCURRENCY_CHART} 图表并发)",
              flush=True)

    async def _process_one(file_path: str) -> None:
        """处理单个文件，受章节并发信号量限流。"""
        # 工作目录解析：相对路径基于各源文件所在目录
        work_dir = args.work_dir
        if not os.path.isabs(work_dir):
            work_dir = os.path.join(
                os.path.dirname(os.path.abspath(file_path)), work_dir,
            )
        # 为每个文件构造独立的 namespace（不修改主 args 避免竞争）
        file_args = argparse.Namespace(**vars(args))
        file_args.file = file_path
        file_args.work_dir = work_dir
        async with chapter_sem:
            await main_async_single(file_args)

    await asyncio.gather(*[_process_one(fp) for fp in args.files])


async def main_async_single(args: argparse.Namespace) -> None:
    """异步主入口：并发处理单个文件中的多个 Mermaid 图表 (v4.1)。

    v4.1 改进:
    - 按 MD 文件名创建隔离子目录
    - build_manifest.json 持久化评审记录
    - --only-charts 支持单图表重入
    - 条件清理：仅全量运行时清理，重入时跳过
    - asyncio 并发 SCSH (max CONCURRENCY_CHART)
    - 统一倒序回写 (避免并发偏移错乱)
    - debrief.json 复盘报告输出
    """
    # 运行时配置覆盖
    runtime_model = args.model
    runtime_max_retries = args.max_retries
    runtime_pass_threshold = args.pass_score
    is_reentry = args.only_charts is not None

    # ── 初始化构建日志（全局日志在根目录，跨文件共享）──
    os.makedirs(args.work_dir, exist_ok=True)
    _setup_log_tee(args.work_dir)

    # 从源文件名导出 file_stem → 创建隔离子目录
    file_stem = os.path.splitext(os.path.basename(args.file))[0]
    chart_dir = _chart_dir(args.work_dir, file_stem)

    with open(args.file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    blocks = extract_mermaid_blocks(md_content)
    if not blocks:
        _log("ℹ️  未找到 Mermaid 代码块")
        return

    # ── 条件清理：仅全量运行时清理，重入时跳过 ──
    if not is_reentry:
        _cleanup_chart_dir(chart_dir, blocks)

    # ── 加载 manifest ──
    manifest = _load_manifest(chart_dir)

    _log(f"🔍 [{file_stem}] 发现 {len(blocks)} 个 Mermaid 图表，开始自检...")
    _log(f"   模型: {runtime_model}")
    _log(f"   通过阈值: {runtime_pass_threshold}/10")
    _log(f"   最大重试: {runtime_max_retries}")
    _log(f"   图表并发: {CONCURRENCY_CHART} | 章节并发: {CONCURRENCY_CHAPTER}")
    _log(f"   构建目录: {chart_dir}")
    if is_reentry:
        _log(f"   重入模式: --only-charts {args.only_charts}")

    # ── 确定需要处理的图表 ──
    if is_reentry:
        target_indices = _parse_chart_indices(args.only_charts, len(blocks))
    else:
        target_indices = set(range(len(blocks)))

    # ── 过滤：增量跳过 + only-charts ──
    tasks_to_run: list[tuple[int, dict]] = []
    for i, block in enumerate(blocks):
        label = _chart_label(block, i)
        if i not in target_indices:
            _log(f"  ⏩ {label} 不在 --only-charts 范围内，跳过")
            continue
        code_h = _code_hash(block['code'])
        if not is_reentry and not _chart_needs_rebuild(
            manifest, i, code_h, chart_dir
        ):
            _log(f"  ⏩ {label} 已通过审查 (manifest hit)，跳过")
            continue
        tasks_to_run.append((i, block))

    if not tasks_to_run:
        _log("ℹ️  所有图表已通过审查，无需处理")
        return

    _log(f"\n🔄 并发处理 {len(tasks_to_run)} 个图表 (max {CONCURRENCY_CHART} 并发)...")

    # ── asyncio 并发 SCSH（不即时回写，避免偏移错乱）──
    auto_fix_enabled = args.auto_fix and not args.dry_run
    sem = asyncio.Semaphore(CONCURRENCY_CHART)
    async_tasks = [
        async_check_and_fix_block(
            block, idx, chart_dir, sem,
            max_retries=runtime_max_retries,
            pass_threshold=runtime_pass_threshold,
            file_stem=file_stem,
            chart_dir=chart_dir,
            # 并发模式下不即时回写，统一在最后倒序回写
        )
        for idx, block in tasks_to_run
    ]
    concurrent_results = await asyncio.gather(*async_tasks)

    # ── 合并结果（为跳过的图表填充 None）──
    results: list[dict | None] = [None] * len(blocks)
    for r in concurrent_results:
        # async_check_and_fix_block 已注入 start_line
        for i, b in enumerate(blocks):
            if b['start_line'] == r['start_line']:
                results[i] = r
                break

    # ── 统一倒序回写（保持偏移正确）──
    if auto_fix_enabled:
        active_results = [r if r else {'status': 'skipped', 'code': b['code']}
                          for b, r in zip(blocks, results)]
        updated = apply_fixes_to_markdown(md_content, blocks, active_results)
        if updated != md_content:
            with open(args.file, 'w', encoding='utf-8') as f:
                f.write(updated)
            _log(f"\n✏️ 已统一回写修复到源文件")

    # ── 更新 manifest 元数据 ──
    manifest = _load_manifest(chart_dir)
    manifest['source_file'] = os.path.basename(args.file)
    manifest['source_hash'] = _code_hash(md_content)
    manifest['model'] = runtime_model
    manifest['pass_threshold'] = runtime_pass_threshold
    manifest['built_at'] = datetime.datetime.now().isoformat()
    _save_manifest(chart_dir, manifest)

    # ── 输出 Markdown 报告 ──
    active_for_report = [r for r in results if r is not None]
    if active_for_report:
        report = generate_report(
            active_for_report, args.file,
            gemini_model=runtime_model,
            max_retries=runtime_max_retries,
        )
        _log(report)

    # ── 输出复盘 JSON (debrief.json) ──
    debrief = _generate_debrief(chart_dir, results, args.file)
    debrief_path = os.path.join(chart_dir, 'debrief.json')
    with open(debrief_path, 'w', encoding='utf-8') as f:
        json.dump(debrief, f, ensure_ascii=False, indent=2)
    _log(f"\n📋 [{file_stem}] 复盘报告: {debrief_path}")
    if debrief['all_passed']:
        _log(f"✅ [{file_stem}] 所有图表审查通过")
    else:
        _log(f"⚠️ [{file_stem}] {debrief['failed']} 个图表未通过")
        if debrief.get('reentry_command'):
            _log(f"🔄 重入命令: {debrief['reentry_command']}")

    # ── 关闭构建日志 ──
    global _log_file
    if _log_file:
        _log_file.close()
        _log_file = None


if __name__ == '__main__':
    try:
        main()
    except ConfigError as e:
        print(f"❌ {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    except ScriptError as e:
        print(f"❌ 脚本错误: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n中断退出", flush=True)
        sys.exit(130)
