---
name: web-research
description: >-
  使用 Brave Search MCP 进行多模态联网检索（Web/News/Video/Image/Local），
  获取最新信息并引用来源，基于证据推理回答。支持 5 种搜索模式和 L1-L5 渐进式查询优化策略。
  适用于：实时新闻检索、事实核查与多源交叉验证、Earnings Call Transcript 检索、
  管理层/公司治理信息收集、技术产品调研与对比、地缘政治与政策动态追踪。
  在 us-stock-analysis、cn-stock-analysis 等投研技能中承担最后一公里信息补全角色。
  当用户提及搜索、查一下、最新消息、新闻、最近发生、动态、
  时事、热点、评测、对比、事实核查、验证时触发。
license: MIT
allowed-tools:
  - brave_web_search
  - brave_news_search
  - brave_video_search
  - brave_image_search
  - brave_local_search
  - brave_summarizer
metadata:
  version: "2.0.0"
  author: "Digital Ray"
---

# Web Research（联网检索）

## 功能概述

通过 Brave Search MCP 工具进行联网检索，获取最新信息并引用来源，然后基于检索到的证据进行推理回答。

## 使用时机

当用户需要以下内容时使用此技能：

- **时效性信息**：新闻、发布公告、价格、政策、时间线
- **事实核查**：需要引用可信来源验证的信息
- **产品/技术对比**：需要查阅官方文档或评测
- **查找资源**：官方文档、GitHub issues/PRs、RFC、博客文章
- **本地商户**：餐厅、服务、地点查询（需 Pro 计划）
- **人物/公司动态**：名人言论、公司新闻、社交媒体动态

**不要使用**：

- 当用户明确禁止联网，或问题完全基于已有上下文可回答时
- 美国宏观经济数据查询（使用 `fred-data` 技能 - FRED MCP 比搜索更精确）
- 全球货币/汇率/国际收支数据（使用 `imf-data` 技能 - imfp 库直连 API）
- 全球发展指标数据（使用 `worldbank-data` 或 `owid-data` 技能 - 结构化 API）
- 中国官方统计数据（使用 `cn-stats-data` 技能 - akshare 聚合多源数据）
- SEC EDGAR 财务数据（使用 `us-stock-analysis` 中的 EdgarTools MCP）
- A 股财报数据（使用 `cn-stock-analysis` 中的 akshare-one-mcp）

> [!TIP]
> **原则**：优先使用结构化数据 API（MCP 或直连 API），仅在 API 无法覆盖时使用 Web Research 补全。

## 可用工具（Brave MCP）

| 工具 | 用途 | 何时使用 |
|------|------|----------|
| `brave_web_search` | 通用网页搜索 | **默认首选**，大多数查询 |
| `brave_news_search` | 新闻搜索 | 时事、突发新闻、近期事件、人物动态 |
| `brave_video_search` | 视频搜索 | 查找教程、演示、讲座视频 |
| `brave_image_search` | 图片搜索 | 查找图片、设计参考、图表 |
| `brave_local_search` | 本地商户搜索 | "附近的..."、特定地点查询（需 Pro） |
| `brave_summarizer` | AI 摘要 | 需要快速概览时（需 Pro AI 订阅） |

## 执行流程（必须遵循）

### 第 1 步：需求分析与查询规划

- 分析用户问题，确定：
  - **查询类型**：新闻/技术/事实核查/对比/人物动态
  - **时间范围**：是否需要限定时效性
  - **结果数量**：用户要求的 Top N 条
  - **语言偏好**：中文/英文/混合
- 对于复杂查询，拆分为多个子查询并行执行

### 第 2 步：执行搜索（支持并行）

**基础调用模板**：

```
brave_web_search:
  query: "精准搜索关键词"
  count: 10-20（根据需要调整，建议多取后筛选）
  freshness: 按需设置
    - pd = 24小时内
    - pw = 7天内  
    - pm = 31天内
    - py = 365天内
```

**并行搜索策略**：

- 新闻类查询：同时调用 `brave_web_search` + `brave_news_search`
- 人物动态：多角度查询（姓名+公司、姓名+最新、姓名+争议等）
- 技术调研：官方源+社区评测+基准测试分开查询

**查询优化与迭代策略**：

当首次搜索结果质量不足时，按以下优先级逐步优化：

| 优化级别 | 策略 | 适用场景 |
|----------|------|----------|
| L1 精确化 | 添加引号强制精确匹配，增加 `site:` 限定 | 结果太泛，噪音多 |
| L2 扩展化 | 移除限定词，使用同义词/别名 | 结果太少或为零 |
| L3 语言切换 | 中→英 或 英→中 重试 | 局部语言覆盖不足 |
| L4 时间调整 | 扩大 `freshness` 范围 | 时效性要求可放宽时 |
| L5 工具切换 | 改用 news/video/local 专项工具 | 通用搜索未命中 |

**迭代终止条件**：

- 已获取 ≥ 3 条高质量结果（评分 ≥ 7）
- 或迭代 ≥ 3 轮仍无新增有效结果（应告知用户信息有限）

### 第 3 步：筛选与评估证据

**来源可信度排序**（高到低）：

1. **官方来源**：官网、官方博客、官方社交账号
2. **权威媒体**：Reuters、BBC、WSJ、The Verge、TechCrunch 等
3. **专业社区**：GitHub、Stack Overflow、Hacker News
4. **技术博客**：知名个人博客、Medium 技术文章
5. **其他来源**：需交叉验证

**结果质量评分框架**（每条结果 0-10 分）：

| 维度 | 权重 | 评分标准 |
|------|------|----------|
| **相关性** | 30% | 0=无关, 5=部分相关, 10=精准匹配用户意图 |
| **权威性** | 25% | 基于来源可信度排序，官方=10, 权威媒体=8, 社区=6, 其他=3 |
| **时效性** | 20% | 24h内=10, 7天内=8, 30天内=5, 更早=2 |
| **内容深度** | 15% | 简讯=2, 详细报道=6, 深度分析=10 |
| **独立性** | 10% | 独家信息=10, 有新视角=6, 重复信息=0 |

**综合评分** = Σ(维度得分 × 权重)，优先展示评分 ≥ 7 的结果。

**筛选原则**：

- 重要信息至少 **2 个独立来源** 交叉验证
- 注意发布日期，标注信息时效性
- 来源冲突时，优先信任更权威/更新的来源
- **去重策略**：
  - 内容重复率 > 80% 的结果仅保留评分最高者
  - 同一事件的多篇报道合并为一条，注明覆盖源数量

### 第 4 步：分析与排序

**重要性评估维度**：

- **影响范围**：全球性 > 区域性 > 局部
- **时效性**：突发 > 近期 > 历史
- **相关性**：直接相关 > 间接相关
- **可信度**：多源验证 > 单一来源

当用户要求 "Top N" 或 "前X条" 时，严格按重要性排序输出。

### 第 5 步：结构化输出

---

## 输出格式模板

### 模板 A：Top N 列表型（新闻/动态/要点汇总）

```markdown
## [主题] - Top N 要点

### 1. [要点标题]
**重要性**：[高/中/低] | **时间**：[日期]

[2-3句核心内容描述]

> 关键引用或数据（如有）

**来源**：[来源名称](URL)

---

### 2. [要点标题]
...

---

### 3. [要点标题]
...

---

## 补充说明
[对整体情况的简要分析，指出趋势或需要关注的点]

## 参考来源
| # | 来源 | 类型 | 可信度 |
|---|------|------|--------|
| 1 | [来源名](URL) | 官方/媒体/社区 | 高/中 |
| 2 | [来源名](URL) | ... | ... |
```

### 模板 B：问答型（事实核查/技术问题）

```markdown
## 回答

[直接回答用户问题，1-2段]

## 关键事实
- **事实1**：[内容] ([来源](URL))
- **事实2**：[内容] ([来源](URL))
- ...

## 详细说明
[基于检索证据的深入分析]

## 来源列表
1. [来源标题](URL) - [简要说明]
2. ...
```

### 模板 C：对比型（产品/技术对比）

```markdown
## [A] vs [B] 对比分析

| 维度 | [A] | [B] | 来源 |
|------|-----|-----|------|
| 性能 | ... | ... | [1] |
| 价格 | ... | ... | [2] |
| ... | ... | ... | ... |

## 详细对比

### [维度1]
[详细分析...]

### [维度2]
[详细分析...]

## 结论
[综合建议]

## 参考来源
1. [来源](URL)
2. ...
```

---

## 搜索参数配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| country | US | 如用户指定地区则修改，中国用户可用 CN |
| search_lang | en | 中文查询用 zh-hans，技术查询建议 en |
| ui_lang | en-US | 中文环境可用 zh-CN |
| safesearch | moderate | 过滤成人内容 |
| count | 15 | 建议多取后筛选，提高覆盖率 |
| freshness | (按需) | 时效性查询必须设置 |

## 使用示例

### 示例 1：人物动态（Top N 型）

**用户**：「最近一周 Elon Musk 的核心言论，按重要性列出前3点」

**执行**：

1. 并行搜索：
   - `brave_news_search(query="Elon Musk statements this week", count=15, freshness="pw")`
   - `brave_web_search(query="Elon Musk latest news January 2026", count=15, freshness="pw")`
   - `brave_news_search(query="Elon Musk Tesla SpaceX xAI news", count=10, freshness="pw")`
2. 合并去重，按影响力/时效性/争议性评估
3. 使用 **模板 A** 输出 Top 3

### 示例 2：技术调研

**用户**：「帮我查一下 yt-dlp 最新版本有什么新功能」

**执行**：

1. 搜索：
   - `brave_web_search(query="yt-dlp latest release changelog", count=10, freshness="pm")`
   - `brave_web_search(query="yt-dlp github releases 2026", count=5)`
2. 优先引用 GitHub releases 官方页面
3. 使用 **模板 B** 输出

### 示例 3：事实核查

**用户**：「Python 3.12 是什么时候发布的？」

**执行**：

1. `brave_web_search(query="Python 3.12 release date official site:python.org", count=5)`
2. 交叉验证其他来源
3. 使用 **模板 B** 输出，标注官方来源

### 示例 4：产品对比

**用户**：「对比一下 Whisper 和 faster-whisper 的性能差异」

**执行**：

1. 并行搜索：
   - `brave_web_search(query="whisper vs faster-whisper benchmark comparison", count=10)`
   - `brave_web_search(query="faster-whisper performance speed memory usage", count=8)`
   - `brave_web_search(query="openai whisper accuracy benchmark", count=5)`
2. 综合基准测试数据
3. 使用 **模板 C** 输出对比表格

---

## 与其他技能的数据路由搭配

> Web Research 在投研工作流中的核心定位是**"最后一公里"信息补全**——当结构化数据 API 无法覆盖的定性信息（管理层言论、竞争动态、政策解读）需要补充时使用。

### 搭配场景

| 搭配场景 | Web Research 的作用 | 搭配技能 | 典型查询 |
| --- | --- | --- | --- |
| **个股分析** | Earnings Transcript + 管理层背景 + 竞争格局 | `us-stock-analysis` / `cn-stock-analysis` | `"NVDA Q4 2025 earnings call transcript full"` |
| **宏观分析** | FOMC 纪要解读 + 央行声明 + 政策文本 | `fred-data` / `imf-data` | `"Fed FOMC statement December 2025"` |
| **调查研究** | 最新政策/事件/专家观点 | 各数据 Skill | `"中国出口管制 稀土 2026 政策"` |
| **事实核查** | 多源交叉验证定性信息 | 所有 Skill | `"[公司名] CEO resignation news"` |
| **估值研究** | TAM 数据 + 分析师目标价 + 行业报告 | `create-valuation-model-plan` | `"global cloud computing TAM 2025 Gartner IDC"` |

### 数据交叉验证策略

当 Web Research 作为其他技能的补充时，遵循以下验证原则：

| 数据类型 | 权威来源（基准） | Web Research 角色 | 差异处理 |
| --- | --- | --- | --- |
| **财务数据** | SEC EDGAR / akshare-one-mcp | 不用于获取财务数字 | 以 API 数据为准 |
| **宏观指标** | FRED / IMF / NBS API | 不用于获取统计数字 | 以 API 数据为准 |
| **管理层言论** | Earnings Call Transcript | 唯一来源，交叉多篇 | >=2 篇独立来源验证 |
| **竞争格局** | 行业报告 / 新闻 | 主要来源 | 优先权威媒体 + 官方 |
| **政策/监管** | 政府官网 | 搜索后优先 `site:gov` | 以官方原文为准 |

---

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| 搜索无结果 | 尝试：1. 换关键词 2. 扩大时间范围 3. 用英文重试 |
| 来源冲突 | 明确指出冲突，解释为何选择某来源 |
| 信息过时 | 标注发布日期，提醒用户注意时效 |
| 结果不足 | 告知用户已获取的信息量，建议补充查询方向 |

## 重要原则

1. **核心工作流准则：遵循 Deep Research 引用与数据溯源规范（强制要求）**
   任何由本 Agent 或 MCP 工具产生的数据、事实与外部知识，**必须在每次回答或每章节末尾**提供极其清晰且结构分离的数据来源溯源。**严禁**在正文代码块内直接拼接超长 URL，必须保持 Markdown 原文的极简化（信噪比）。

   **核心引用格式规范必须自我包含且严格遵守：**

   - **招式一：可见内联链接 (Visible Inline Links) [最推荐外部 URL 引用]**
     - **正文语法**: `正如 [《WSJ AI CapEx 报告》](https://www.wsj.com/...) 中显示的...`
     - **文末汇总**: `**wsj_capex**: [WSJ AI CapEx 报告](https://www.wsj.com/...)`
     - **场景**: 所有高频引用的网页、外部数据库、研报链接。
     - **⚠️ 严禁使用**: `[ID]: URL "Title"` 格式（Markdown reference-link definition），该语法在 Obsidian 中**完全不可见**，会导致参考文献渲染为空白 bullet points。

   - **招式二：脚注引用 (Footnotes) [长尾解释与免责声明]**
     - **正文语法**: `Python 3.12 于近期发布[^1]。`
     - **文末定义**: `[^1]: 官方发布说明详见 python.org 发行说明。`

   - **招式三：动态数据伪协议溯源 (MCP/API Sources)**
      - **正文语法**: `根据最新拉取的十年期美债收益率 [fredUS10Y]，...`
      - **文末汇总**: `**fredUS10Y**: \`mcp://fred-mcp-server/fred_get_series\` — "10-Year Treasury Constant Maturity Rate"`
      - **附加脚注**: 在文末必须用脚注补充 MCP 调用的核心参数和时间戳。例如：`[^2]: [fredUS10Y] 查询参数快照 {"series_id": "DGS10"}，抓取时间：2026-02-20。`

   > 💡 **"终极引用区" 模板输出要求**
   > 在每个你回答的关键节点或调查报告章节末尾，必须使用 Callout 风格输出参考文献：
   >
   > ```markdown
   > ## 📚 关联文献与参考资料
   >
   > > [!INFO] 数据溯源
   > > 
   > > **动态接口与数据湖 (Dynamic Data & MCP Sources)**：
   > > - **BraveSearch_Docs**: `mcp://brave-search/brave_web_search` — "Search Query: Python 3.12 release date"
   > > 
   > > **外部数据源 (External Database)**：
   > > - **WSJ**: [WSJ Article Title](https://www.wsj.com/...)
   > 
   > [^1]: [BraveSearch_Docs] 调用参数快照：`{"query": "...", "freshness": "pm"}`，检索于 YYYY-MM-DD。
   > ```
   >
   > > ⚠️ **参考文献格式红线**：
   > > 1. 所有内容必须在 `> [!INFO]` callout 内
   > > 2. 分类名称必须是 **粗体**（如 `**动态接口**：`），**严禁使用 `###` 标题**
   > > 3. `[^N]:` 脚注必须放在 callout 取块**外部**
   > > 4. 严禁在 callout 内使用 Markdown 表格

1. **区分事实与推测**：明确标注「检索事实」vs「分析推断」。
1. **注意时效性**：所有来源标注日期，过时信息明确提醒。
1. **重要性排序**：当用户要求 Top N 时，严格按评估维度排序。
1. **并行高效**：多个独立查询应并行执行，减少等待时间。
1. **语言适配**：中文问题优先中文，技术或国际话题可用英文，混合使用取最优。
1. **链接质量**：必须引用原始出处的链接（不要引用聚合站），对于 GitHub 引用具体 commit/tag 而非长期易变的 main 分支。
