---
title: Mermaid SCSH 深度参考
date: 2026-03-01
tags:
  - mermaid
  - scsh
  - reference
---

# Mermaid SCSH 深度参考

> 本文档为 `mermaid_scsh.py` 自检修复管线的深度参考手册。
> 核心定义与使用说明见 [SKILL.md](SKILL.md)。

---

## §1 审查规则细则（L1 静态修复）

L1 层在 mmdc 渲染失败时自动触发，根据 stderr 错误签名分类并应用确定性修复规则。零 API 成本。

### 规则 1: `xychart_label`

| 项目 | 详情 |
| ---- | ---- |
| **Error Signature** | `Expecting 'NUMBER_WITH_DECIMAL', got 'STR'` |
| **根因** | `xychart-beta` 的 `bar`/`line` 数据行包含了标签字符串 |
| **修复逻辑** | 移除 `bar`/`line` 后方括号内的非数值内容 |
| **代码** | `re.sub(r'(bar\|line)\s+\[.*?\]\s+\[', r'\1 [', code)` |

**示例**：

```diff
- bar ["Q1", "Q2"] [100, 200]
+ bar [100, 200]
```

### 规则 2: `timeline_colon`

| 项目 | 详情 |
| ---- | ---- |
| **Error Signature** | `INVALID` + 含 `timeline` |
| **根因** | timeline 事件文本中含冒号（`:` 或 `：`），被解析器识别为分隔符 |
| **修复逻辑** | 仅替换事件文本部分（分隔符 `:` 之后）的冒号为 `—` |
| **函数** | `fix_timeline_colons()` |

**示例**：

```diff
- 2024 : 议会 221:0 通过
+ 2024 : 议会 221—0 通过
```

### 规则 3: `json_format`

| 项目 | 详情 |
| ---- | ---- |
| **Error Signature** | `%%{init` + `Error` 或 `JSON` |
| **根因** | `%%{init}%%` 块中 JSON 格式非法（单引号、尾逗号、多行断裂） |
| **修复逻辑** | 单引号→双引号、移除尾逗号、尝试 `json.loads` 验证 |
| **函数** | `fix_init_json()` |

### 规则 4: `reserved_keyword`

| 项目 | 详情 |
| ---- | ---- |
| **Error Signature** | `Unexpected token` + `end` 或 `classDef end` |
| **根因** | `end` 是 Mermaid 保留字，不可用作 class 名或 ID |
| **修复逻辑** | `classDef end` → `classDef endpoint` |

### 规则 5: `chinese_unquoted`

| 项目 | 详情 |
| ---- | ---- |
| **Error Signature** | `Parse error` + 中文字符 |
| **根因** | 中文节点标签未用引号包裹 |
| **修复逻辑** | 自动为含中文的 `[...]` 标签添加双引号 → `["..."]` |
| **函数** | `auto_quote_chinese()` |

**示例**：

```diff
- A[数据处理] --> B[分析结果]
+ A["数据处理"] --> B["分析结果"]
```

### 规则 6: `sankey_newline`

| 项目 | 详情 |
| ---- | ---- |
| **Error Signature** | `sankey` + `error` |
| **根因** | `sankey-beta` 关键字后缺少空行 |
| **修复逻辑** | 在 `sankey-beta\n` 后插入额外空行 |

---

### 规则 7: `markdown_list_label`

| 项目 | 详情 |
| ---- | ---- |
| **Error Signature** | `Unsupported markdown: list` |
| **根因** | flowchart 节点标签以列表符开头（`数字.` / `-` / `*` / `+`），被解析为 Markdown list |
| **修复逻辑** | 移除标签内 `["` 之后的所有列表前缀符 |
| **覆盖范围** | 有序 (`1.`, `1.2.`)、无序 (`-`, `*`, `+`) |

**示例**：

```diff
- A["1. 数据采集"] --> B["2. 数据分析"]
+ A["数据采集"] --> B["数据分析"]
- C["- 测试项"] --> D["* 验证项"]
+ C["测试项"] --> D["验证项"]
```

### 规则 8: `plotColorPalette_nesting`

| 项目 | 详情 |
| ---- | ---- |
| **Error Signature** | 无（静默退化，图表变为浅黄色默认配色） |
| **触发方式** | 非 stderr 驱动，在 `check_and_fix_block()` 渲染前预扫描触发 |
| **根因** | `plotColorPalette` 等 xychart 属性放在 `themeVariables` 顶层而非 `xyChart: {}` 对象内 |
| **修复逻辑** | JSON AST 解析 → 将顶层的 `plotColorPalette`/`backgroundColor`/`titleColor` 迁移到 `xyChart` 对象内（字典合并，不覆盖已有值） |
| **安全特性** | 如果 `xyChart` 已存在且已有正确配置则跳过；如果 JSON 无法解析则不修复 |

---

## §2 L3 Gemini 审查评分标准

### 通用评分矩阵

| 分数区间 | 级别 | 含义 | 操作 |
| -------- | ---- | ---- | ---- |
| **8-10** | Pass | 质量优秀 | `overall_pass = true`，不生成 fix_code |
| **5-7** | Warning | 存在可优化项，不阻断 | `overall_pass = false`，生成 fix_code |
| **1-4** | Critical | 严重视觉问题 | `overall_pass = false`，必须修复 |

**通过条件**：`overall_pass = true` 当且仅当 `overall_score >= PASS_THRESHOLD`（默认 7）且无 `severity=critical` 的 issue。

### 按图表类型细则

#### Flowchart 布局评分

| 检查项 | 权重 | 评分标准 |
| ------ | ---- | -------- |
| 节点重叠 | 高 | 任何重叠 → -3 |
| subgraph 标题可见性 | 高 | 被遮挡 → -2 |
| 方向合理性 (TD/LR) | 中 | 不适合当前密度 → -1 |
| classDef 完整性 | 中 | 缺少 classDef → -1 |
| clusterBkg/clusterBorder 设置 | 中 | 缺失 → -1 |

#### XYChart 配色评分

| 检查项 | 权重 | 评分标准 |
| ------ | ---- | -------- |
| 柱状图首色深度 | 高 | 浅色（如 #A2D2FF）作柱状图 → -3 |
| plotColorPalette 嵌套位置 | 高 | 在 themeVariables 顶层 → -2 |
| Y 轴留白 | 中 | 数据贴顶 → -1 |
| 多系列遮挡 | 高 | ≥2 bar 系列 → -2 |

#### Timeline 密度评分

| 检查项 | 权重 | 评分标准 |
| ------ | ---- | -------- |
| 节点数 | 中 | >8 → -2 |
| 文字重叠 | 高 | 相邻节点文字重叠 → -3 |
| 条目长度 | 中 | 单条目 >12 汉字 → -1 |
| 冒号残留 | 高 | 事件文本含冒号 → -2（语法级风险） |

---

## §3 SCSH 错误码映射

| `status` | 含义 | Agent 行动 |
| -------- | ---- | ---------- |
| `passed` | 图表通过审查（score ≥ PASS_THRESHOLD 且无 critical） | 如使用 `--auto-fix`，自动回写修复代码到源文件 |
| `failed` | 渲染失败，无法生成有效 PNG，且静态修复无效 | 检查 mmdc stderr，在 Mermaid Live Editor 调试 |
| `needs_intervention` | 渲染成功但审查未通过，已用尽重试次数 | `--auto-fix` 模式会回写历史最高分版本；查看残留问题表格，手动调整后重新运行 |

### history 记录中的修复类型

| `type` | 含义 |
| ------ | ---- |
| `syntax_fix` | L1 静态修复规则自动应用 |
| `gemini_fix` | L3 Gemini Vision 审查后生成 fix_code |
| `rollback` | Gemini fix_code 不可渲染，回退到上一个可渲染版本 |
| `gemini_error` | Gemini API 调用异常（网络/Key/额度） |

---

## §4 排错手册

### 4.1 mmdc 渲染超时 (>30s)

**症状**：`stderr` 为 `mmdc render timeout (>30s)`

**原因**：图表过于复杂，Puppeteer 渲染耗时超限

**解决**：

1. 简化图表，减少节点数至 ≤12
2. 检查是否有无限循环的连线定义
3. 确认 Puppeteer 和 Chrome 正常工作：`mmdc --version`

### 4.2 Gemini 返回非 JSON

**症状**：`json.JSONDecodeError` 异常

**原因**：Gemini 模型输出包含 markdown 围栏或非 JSON 内容

**解决**：

1. 确认使用了 `response_mime_type='application/json'` 配置
2. 尝试切换模型：`MERMAID_SCSH_MODEL=gemini-2.0-flash`
3. 如问题持续，检查 Prompt 是否被截断

### 4.3 fix_code 不可渲染

**症状**：Gemini 生成的修复代码导致 mmdc 渲染失败

**处理流程**（脚本自动）：

1. 检测到渲染失败后，尝试 L1 静态修复
2. 如静态修复无效，自动回退到 `last_good_code`
3. 回退后重新计入重试次数

**预防**：Prompt 中已内嵌 7 条 fix_code 输出护栏，约束 Gemini 生成规范代码

### 4.4 PNG 文件过小误判

**症状**：mmdc 渲染成功（returncode=0），但 PNG < 5KB 被 L2 判为失败

**原因**：极简图表（如仅 2 个节点）生成的 PNG 确实小于 5KB

**解决**：

1. 当前阈值为 5000 bytes，适用于绝大多数场景
2. 如遇极简图表误判，可在脚本中调整 `L2_MIN_SIZE` 常量

### 4.5 GOOGLE_API_KEY 无效

**症状**：`google.api_core.exceptions.PermissionDenied` 或 `InvalidArgument`

**解决**：

1. 确认 `GOOGLE_API_KEY` 已设置：`echo $GOOGLE_API_KEY`
2. 确认 Key 已启用 Gemini API：[Google AI Studio](https://aistudio.google.com/)
3. 确认 Key 未过期或被撤销

---

## §5 环境变量完整说明

| 变量名 | 必须 | 默认值 | 说明 |
| ------ | ---- | ------ | ---- |
| `GOOGLE_API_KEY` | ✅ | — | Gemini API Key，用于 L3 Vision 审查 |
| `MERMAID_SCSH_MODEL` | — | `gemini-3-flash-preview` | 审查模型，可切换为 `gemini-2.0-flash` 等 |
| `MERMAID_SCSH_MAX_RETRIES` | — | `2` | 单图表最大重试次数（含 L1 和 L3 修复） |
| `MERMAID_SCSH_PASS_SCORE` | — | `7` | 通过分数阈值（1-10），≥此分且无 critical 即通过 |
| `http_proxy` | — | `none` | 标准代理环境变量（通常在 `~/.zshrc` 中配置），httpx 自动读取。必须用 `http://` |

### CLI 参数（覆盖环境变量）

```bash
python3 mermaid_scsh.py \
    --file target.md \         # [必须] 目标 Markdown 文件
    --max-retries 3 \          # [可选] 覆盖 MERMAID_SCSH_MAX_RETRIES
    --pass-score 7 \           # [可选] 覆盖 MERMAID_SCSH_PASS_SCORE
    --model gemini-3-flash-preview \ # [可选] 覆盖 MERMAID_SCSH_MODEL
    --auto-fix \               # [可选] 自动回写修复到源文件（含 best-score 回写）
    --dry-run \                # [可选] 仅审查不修改
    --work-dir .build_chart    # [可选] 临时工作目录（默认源文件同级 .build_chart/）
```

> `--auto-fix` 和 `--dry-run` 同时指定时，`--dry-run` 优先，不修改源文件。

---

## §6 快速排障 Checklist

图表不渲染时，按以下顺序排查：

1. ✅ `%%{init}%%` JSON 格式正确？（单/双引号一致、无尾逗号）
2. ✅ CJK 标签已加双引号？（`["中文"]`）
3. ✅ 配色嵌套层级正确？（xychart → `xyChart: {}`，sankey → `sankey: {}`）
4. ✅ 节点标签无列表前缀？（`1.` / `-` 开头 → "Unsupported markdown: list"）
5. ✅ `sankey-beta` 后有空行？
6. ✅ timeline 事件无冒号？（`:` 或 `：` → 用 `—` 替代）
7. ✅ 节点 ID 未使用保留字？（`end`、`graph`、`subgraph` 等）
8. ✅ 容量未超限？（节点 ≤12 / 饼图 ≤8 段 / 时间线 ≤8 节点）

---

## §7 构建目录与日志 (v3.1)

SCSH v3.1 在源文件同级自动创建 `.build_chart/` 目录，集中管理所有构建产物：

### 日志文件

| 文件 | 用途 | 写入时机 |
| ---- | ---- | -------- |
| `build.log` | 完整控制台日志副本（双通道写入） | 每次 `_log()` 调用 |
| `api_trace.log` | Gemini API prompt/response/error 审计 | 每次 API 调用前后 |

### Best-Score 回写机制

当图表未通过审查（`needs_intervention`）时，SCSH 会追踪修复过程中的最高分版本：

1. 每次 Gemini 生成 fix_code 且可渲染时，比较当前分数与历史最高分
2. 若当前版本得分更高，更新 `best_code` 和 `best_score`
3. 用尽重试后，将 `best_code`（而非最后一次尝试的代码）返回
4. `--auto-fix` 模式下，`apply_fixes_to_markdown()` 将 `needs_intervention` 的 `best_code` 回写源文件

### Prompt 架构（v4.3 System Instruction 分离）

**System Instruction**：全局规则存放于 `resources/REVIEW_PROMPT.md`，包含审查人设、绝对约束、评分维度及 JSON Schema。通过 `_load_prompt()` 函数加载后，注入 `types.GenerateContentConfig(system_instruction=...)` 独立通道，与用户请求隔离，确保模型指令遵循稳定性。支持 `{pass_threshold}` 占位符注入，使阈值与代码配置同步。

**User Prompt**：每次调用 `review_with_gemini` 时，动态构建 `user_prompt` 字符串，携带本次请求的变量内容：

- 历史修复记录（`retry_history` 中 `type=gemini_fix` 的条目）
- 原始 Mermaid 源码
- 图表专属配色/布局模板（来自 `chart_templates/`，未匹配时兜底 `common_chart.md`）

**兜底模板（v4.2）**：`chart_templates/common_chart.md` 包含 Healing Dream 基础配色参数与通用防截断规则，当 `detect_chart_type()` 返回 `unknown` 或无专属模板时自动加载，确保 Gemini 修复代码的配色底线安全。
