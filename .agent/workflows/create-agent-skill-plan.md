---
description: 创建经过充分调研的 Agent Skill 最佳实践实现计划 — 通过 Context7 + Brave Search 深度检索官方技术资料，结合本地最佳实践与 SKILL 规范，输出可直接指导 Skill 编写的实现计划
---

# Agent Skill 最佳实践实现计划工作流

将 Skill 需求转化为经过充分调研的最佳实践实现计划：通过 Context7 检索官方文档 + Brave Search 补充社区实践 → 对齐本地最佳实践 → 输出可直接指导 Skill 编写的实现计划。

---

## 调研工具

本工作流使用 **Context7** 和 **Brave Search** 两个 MCP 工具协同完成技术调研。两者互补：

| 工具 | 定位 | 优势 | 局限 |
| --- | --- | --- | --- |
| **Context7** | 官方文档首选检索 | 结构化、权威、API 级精度、直取 library repo 源码文档 | 仅覆盖已索引的库；每次调研限 3 次 query-docs |
| **Brave Search** | 社区实践补充检索 | 覆盖博客、GitHub Issues、Stack Overflow、生产经验 | 需人工筛选质量；结果可能过时 |

**调研顺序**：Context7 先行（获取权威 API 文档）→ Brave Search 补充（填补 Context7 未覆盖的内容）→ 本地最佳实践对齐。

### Context7 使用指南

通过 Context7 MCP Server 检索核心技术栈的官方文档。

**工具调用流程**：

1. **resolve-library-id** — 将库名解析为 Context7 Library ID
   ```
   输入: libraryName="imfp", query="IMF data query Python"
   输出: /promptly-technologies/imfp (Library ID)
   ```

2. **query-docs** — 用 Library ID 查询官方文档（⚠️ 每次调研最多 3 次调用）
   ```
   输入: libraryId="/promptly-technologies/imfp", query="initialize client fetch dataset error handling"
   输出: 相关代码示例与 API 说明
   ```

**优先级分配**（3 次调用额度）：

| 优先级 | 检索对象 | 示例 Query |
| --- | --- | --- |
| P0 | SDK 初始化与核心 API 调用 | `"initialize client API calls"` |
| P1 | 错误处理 / 重试 / Rate Limit | `"error handling retry rate limit"` |
| P2 | 高级特性（流式/并发/批量） | `"streaming async batch examples"` |

**输出要求**：每次调用记录 Library ID、Query、关键发现，汇入技术调研报告。

### Brave Search 使用指南

Context7 未覆盖的内容用 Brave Search 补充检索。

**首选工具**：`brave_web_search`（通用搜索），按需切换 `brave_news_search`（时事）/ `brave_video_search`（教程）。

**关键参数**：

| 参数 | 推荐值 | 说明 |
| --- | --- | --- |
| `search_lang` | `en`（技术查询）/ `zh-hans`（中文语境） | 语言偏好 |
| `freshness` | `py`（一年内）或不设 | 时效控制 |
| `count` | 10-15 | 多取少用，人工过滤 |

**L1-L5 渐进优化策略**：

| 级别 | 策略 | 适用场景 |
| --- | --- | --- |
| L1 精确 | 加引号精确匹配 + `site:` 约束 | 结果太泛、噪声多 |
| L2 扩展 | 去除约束、使用同义词/别名 | 结果太少或为零 |
| L3 换语言 | 中↔英切换重试 | 单一语言覆盖不足 |
| L4 调时间 | 放宽 `freshness` 范围 | 时效要求可松动 |
| L5 换工具 | 切换到 `brave_news_search` / `brave_video_search` | 通用搜索遗漏目标 |

### 交叉验证规范

技术调研的核心质量保障。所有关键技术结论必须经过多源验证，**尤其是直接影响代码实现的 API 细节**。

**强制验证项**（以下内容必须 ≥2 个独立源确认）：

| 验证类别 | 高风险示例 | 验证方法 |
| --- | --- | --- |
| **参数单位** | 超时时间是秒还是毫秒？文件大小是 bytes 还是 KB？ | Context7 官方文档 + Brave Search 查找 API Reference / changelog |
| **参数类型与格式** | 日期参数是 `"2025-01-01"` 还是 Unix 时间戳？数组用逗号分隔还是 JSON？ | 官方文档 + 实际代码示例对照 |
| **默认值与边界** | 默认重试次数？最大并发连接数？Rate Limit 阈值？ | 官方文档 + GitHub Issues/Discussions 中的实测反馈 |
| **认证与权限** | API Key 传递方式（Header/Query/ENV）？OAuth scope 要求？ | 官方 Getting Started + 社区实践验证 |
| **版本兼容性** | SDK v2 vs v3 API 差异？Python 版本要求？依赖冲突？ | PyPI/npm 页面 + GitHub release notes |
| **错误码语义** | HTTP 429 vs 503 的重试策略差异？错误响应体结构？ | 官方错误参考 + Stack Overflow 实战案例 |
| **废弃/变更 API** | 文档中的 API 是否已被 deprecated？替代方案是什么？ | changelog/migration guide + `freshness:py` 搜索近期变更 |

**验证流程**：

```
Context7 query-docs 获取官方说明
        ↓ 记录：参数名、类型、单位、默认值
Brave Search 交叉验证
        ↓ 搜索: "[库名] [参数名] unit seconds milliseconds"
        ↓ 搜索: "[库名] [API名] default value timeout"
比对两源结果
        ↓ 一致 → 采纳，标注 [已验证]
        ↓ 矛盾 → 以官方文档为准，标注 [存疑: 源A=X, 源B=Y]，
                  建议在实现阶段编写单元测试验证
```

**标注规范**：

在技术调研报告中，对每个关键 API 参数使用以下标注：

| 标注 | 含义 | 后续动作 |
| --- | --- | --- |
| `[已验证]` | ≥2 源一致确认 | 可直接用于实现 |
| `[单源]` | 仅 1 个源，未找到第二源 | 实现时编写防御性代码 + 单元测试 |
| `[存疑]` | 多源矛盾 | 实现时必须编写单元测试验证实际行为 |

**反面案例**（调研中常见的高风险遗漏）：

- ❌ 超时参数写了 `timeout=30` 但未确认单位，实际是毫秒导致 30ms 超时
- ❌ 照搬博客代码中的 `max_retries=3`，未查证 SDK 默认值已经是 3，导致重复配置
- ❌ 使用了 v1 API 的参数名，未发现 v2 已改名，运行时报 unknown parameter
- ❌ Rate Limit 文档写 "100 requests per minute" 但实测是 per endpoint 而非 per client

---

## Phase I: 需求拆解与技术侦察

### 0. 需求确认（已提供则跳过）

| 信息          | 必需 | 默认值                              |
| ------------- | ---- | ----------------------------------- |
| Skill 名称    | ✅   | —（kebab-case, ≤64 字符）           |
| 功能描述      | ✅   | —                                   |
| 核心技术栈    | ✅   | —（API/库/MCP Server）              |
| 输入/输出     | ✅   | —                                   |
| 触发关键词    | ❌   | 从描述提取                           |
| 参考 Skill    | ❌   | —                                   |
| 输出位置      | ❌   | `01_Research/{技术栈}/{Skill名}/`    |
| 复杂度        | ❌   | 中等（简单/中等/复杂）               |

### 1. 能力矩阵拆解

对需求拆解 8 个维度：① 核心功能 ② 数据源 ③ 处理管线 ④ 工具链（MCP Server / 外部工具）⑤ 输出格式 ⑥ 容错需求 ⑦ 并发需求 ⑧ 增量/缓存需求。

### 2. Context7 官方文档检索

// turbo

用 Context7 MCP 检索核心技术栈官方文档（详见上方「Context7 使用指南」）：

1. **resolve-library-id**：将核心技术栈名称解析为 Library ID
2. **query-docs**（≤3 次，按 P0→P2 优先级排序）：获取 SDK 初始化、核心 API、错误处理等关键文档

记录 Library ID、Query、关键发现。对获取到的 **API 参数单位、类型、默认值** 逐一标注，待步骤 3 交叉验证。

### 3. Brave Search 补充检索与交叉验证

// turbo

Context7 未覆盖的内容用 Brave Search 补充（详见上方「Brave Search 使用指南」+ 「交叉验证规范」）：

- L1: `"[技术名] Python quickstart 2025"`
- L2: `"[技术名] production error handling retry patterns"`
- L3: `"[技术名] [具体问题] site:github.com OR site:stackoverflow.com"`

**要求**：
- 每个关键技术点 ≥2 个独立源交叉验证，优先官方文档 > GitHub > SO > 博客
- 对步骤 2 中标注的 API 参数细节（单位/类型/默认值/边界）逐项验证，更新标注状态为 `[已验证]` / `[单源]` / `[存疑]`

### 4. 本地最佳实践对齐

// turbo

**按需读取以下文档的相关章节**：

| 文档 | 必读章节 | 触发条件 |
| ---- | -------- | -------- |
| [[Agent Skill 编写规范]] | §3 SKILL.md 规范, §5 最佳实践, §7.4 检查清单 | **所有 Skill** |
| [[Python3 异步编程和异常处理的最佳实践]] | §9 自定义异常, §10 Retry, §13 日志 | 涉及 Python 脚本 |
| [[Python 访问 Gemini API 最佳实践]] | §1 Client, §3 防御式提取, §5 多层容错 | 涉及 Gemini API |

### 5. 现有 Skill 参考分析

// turbo

选取 1-2 个最相关的现有 Skill，分析目录结构、执行流程、容错设计、Prompt 管理。

| Skill 类型                | 推荐参考                            |
| ------------------------- | ----------------------------------- |
| 纯编排型（MCP 工具组合）   | `us-stock-analysis`, `web-research` |
| 脚本驱动型（Shell+Python） | `md2ppt`, `md2epub`, `md2pdf`       |
| 方案生成型                 | `create-valuation-model-plan`       |
| 数据查询型                 | `fred-data`, `imf-data`             |

---

## Phase II: 方案设计

### 6. 架构设计

**6.1 目录结构**（按需裁剪）：

```
.agent/skills/{name}/
├── SKILL.md              # [必须] Skill 定义
├── reference.md          # [可选] 排错指南
├── resources/            # [可选] Prompt 模板（占位符替换）
└── scripts/              # [可选] 可执行脚本
```

**6.2 数据流**：产出 Mermaid 数据流图（输入→处理步骤→输出，标注容错分支）。

**6.3 技术决策记录 (ADR)**：对并发模型、Prompt 管理、错误处理、配置管理等关键决策记录选型理由。

### 7. SKILL.md 骨架设计

设计完整 SKILL.md 结构，**必须通过设计检查清单**（`Agent Skill 编写规范` §7.4）：

- [ ] `name` ≤64 字符、kebab-case
- [ ] `description` 含触发关键词，≤1024 字符
- [ ] 有"使用时机"和"不要使用"
- [ ] 有前置条件/环境检查
- [ ] 执行流程 Step 1-N 结构化，每步有输入/输出/验证
- [ ] 有结构化输出模板 + 错误处理表
- [ ] 可选参数有默认值，利用渐进披露

### 8. 脚本架构设计（如涉及脚本）

> [!IMPORTANT]
> 本步骤仅设计脚本的**架构与函数签名**（不写实现代码）。实际编写脚本时，**必须使用 `script-coder` 技能**，详见下方说明。

**Shell 入口**：环境激活 → 依赖检查 → 调用 Python → 日志 tee 归档。

**Python 核心脚本必须覆盖的工程模式**：

| 模式                 | 来源                 | 实现                                          |
| -------------------- | -------------------- | --------------------------------------------- |
| Singleton Client     | Gemini API §1.5      | `_get_client()` 全局单例                       |
| 防御式 Response 提取  | Gemini API §3        | `_safe_response_text()` / `_safe_stream_text()` |
| 多层容错重试          | Gemini API §5        | SDK→Response 验证→Function 重试→业务重试        |
| 线程安全日志          | Gemini API §4.4      | `Lock()` + `flush=True` + API Trace 分离       |
| Retry Decorator      | Python3 异步 §10     | 指数退避 + 随机抖动                             |
| 自定义异常层级        | Python3 异步 §9      | `SkillError` → 子类                            |
| 异常链保留            | Python3 异步 §8      | `raise X() from e`                            |
| Semaphore 并发控制    | Python3 异步 §5      | `asyncio.Semaphore(N)`                        |
| Prompt 模板分离       | md2ppt resources/    | 从 `resources/*.md` 加载 + 占位符替换           |

**`script-coder` 技能使用要求**：

Skill 涉及 Python/Shell 脚本时，从计划进入编写阶段后，**必须调用 `script-coder` 技能**编写所有脚本代码。禁止跳过 `script-coder` 直接手写脚本。

| 项目 | 说明 |
| --- | --- |
| **触发条件** | 实现计划中包含 `scripts/` 目录设计（Python 或 Shell 脚本） |
| **输入** | 本步骤产出的脚本架构设计（函数签名、职责、工程模式表） |
| **script-coder 职责** | 按架构设计生成生产级代码，自动应用 9 项 Always-On 工程模式 + 按需应用条件模式 (C1-C17) |
| **Quality Gate** | script-coder 内置自审检查清单，代码必须通过后才交付 |

`script-coder` 确保的工程质量底线（Always-On 模式）：

- Shebang + Docstring + Type Hints
- 精确异常捕获（禁止裸 `except`）
- 日志 `flush=True` 防丢失
- Shell 防御性编码 (`set -euo pipefail`)
- 敏感信息环境变量注入（禁止硬编码）

---

## Phase III: 方案输出与审批

### 9. 输出实现计划

整合为 `{Skill名}_实现计划.md`，保存至输出位置。此文档为 Skill 编写创建的**唯一权威参考**。**方案结构**：

```
一、方案概览（Skill名/功能/技术栈/复杂度/参考Skill）
二、需求分析与能力矩阵
三、技术调研报告（Context7 官方文档 + Brave Search 社区实践 + 本地对齐）
    - 含 API 参数验证状态标注表（[已验证]/[单源]/[存疑]）
四、架构设计（目录结构 + Mermaid 数据流 + ADR）
五、SKILL.md 设计草案（Frontmatter + 执行流程 + 错误处理表）
六、脚本架构设计（函数签名+职责，不写实现）
    - 含 script-coder 使用说明（触发条件 + 输入要求 + 适用工程模式清单）
七、Prompt 设计（模板清单+占位符+策略）
八、前置条件与环境配置
九、验证计划（单元测试/集成测试/边界条件）
十、SKILL.md 编写检查清单
参考资料
```

### 10. Quality Gate → 用户审批

方案提交前必须通过：

- [ ] Context7 resolve-library-id + query-docs ≥1 次完成核心 API 调研
- [ ] Brave Search ≥2 个独立源交叉验证，遵循 L1-L5 渐进优化
- [ ] 关键 API 参数（单位/类型/默认值/边界）均标注验证状态 `[已验证]` / `[单源]` / `[存疑]`
- [ ] 本地最佳实践 ≥1 份对齐 + ≥1 个 Skill 参考分析
- [ ] Mermaid 数据流图 + ADR 表格完整
- [ ] SKILL.md 通过 §7.4 检查清单
- [ ] 工程模式表覆盖（如涉及脚本）
- [ ] 脚本编写指定使用 `script-coder` 技能，输入要求（架构设计 + 适用工程模式）已明确
- [ ] YAML Frontmatter + 双语规范 + 参考资料完整

✅ 通过 → 进入 Skill 编写 ∣ ❌ 反馈 → 回 Phase II 迭代

---

## 从计划到实现的衔接

实现计划通过审批后，按以下分工执行：

| 产物 | 执行方式 |
| --- | --- |
| `SKILL.md` | 根据实现计划第五章草案直接编写 |
| `reference.md` | 根据调研报告中的排错经验整理 |
| `scripts/*.py` / `scripts/*.sh` | **必须使用 `script-coder` 技能**，将实现计划第六章（函数签名+工程模式清单）作为输入 |
| `resources/*.md` | 根据实现计划第七章 Prompt 设计编写 |
