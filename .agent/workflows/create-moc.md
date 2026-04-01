---
description: 当用户输入 /create-moc 时触发。用于全盘扫描工作区，生成结构化的内容索引（Map of Content），保存至 10_MOC 目录。
---

# Map of Content (MOC) 生成工作流

> 你是 **首席知识管理员 (Chief Librarian)**，负责为 Obsidian 工作区生成主索引文件 (MOC)。
> MOC 是 GEMINI.md 分类体系的详细展开 — GEMINI.md 仅列顶级目录概览，MOC 提供完整的子目录导航与内容地图。

---

## 1. 分析阶段

1. **读取 `GEMINI.md`**：理解当前分类体系 (P.A.R.A. + JD) 与工作区目标
2. **全盘扫描目录**：
   - 列出根目录确认所有活跃文件夹 (00-99)
   - 递归扫描子目录（深度 2-3），获取完整目录树
   - 统计每个子目录的文件数量与最近修改时间
   - 重点标记 `04_Investments`、`05_Technology`、`07_Investigation` 中的活跃项目

## 2. 生成阶段

输出文件：`{WORKSPACE}/10_MOC/Home.md`

### 文件结构

**Frontmatter**：

```yaml
---
tags:
  - MOC
  - Dashboard
updated: YYYY-MM-DD
---
```

**首先，写入固定的核心理念 Callout**：

```markdown
# Home: The Command Center

> [!NOTE] 核心指南 (Core Philosophy)
> 1. **唯一真实源 (Single Source)**: 聚合所有研究、代码探索与思想碎片的最高指挥中心。
> 2. **AI 驱动生态 (Agent-Driven)**: 依托 AI Agent 与体系化 Skills/Workflows 消除摩擦，实现自动化投研与知识流转。
> 3. **复用与沉淀 (Continuous Accumulation)**: 拒绝一次性消耗，追求知识组件化与长期复利。
```

### Section 1: 🗺️ 区域知识路由表 (Zone Routing Matrix)

> [!IMPORTANT]
> 必须使用 **Markdown 表格** 展示，禁止使用冗长的嵌套列表。
> 表格包含 3 列：`区域 (Zone)` \| `功能定位 (Purpose)` \| `核心路标 (Key Pointers)`

**路由表数据来源提取规则**：

- **区域 (Zone)**: 使用 Emoji + 顶级目录名（如 `📥 00_Inbox`）。可以将逻辑关联的目录合并在一行（如 `🔍 01-03 炼金室` 或 `🕵️‍♂️ 07-09 调查与个人`）。
- **功能定位 (Purpose)**: 紧凑的一句话描述该区域的核心用途。
- **核心路标 (Key Pointers)**: 提取该目录下最活跃的 2-3 个子目录名或文件名（如果是 04_Investments 等核心区，必须包含高频的 Ticker 或专题），使用 `代码块` 或 `[[WikiLink]]` 格式展示，用逗号连接。

### Section 2: 📊 知识地图 (System Architecture)

> 使用 `mermaid flowchart TD` 替代庞杂的 mindmap。

**生成规则**：

1. **必须包含以下 Healing Dream 配置**：

   ```mermaid
   %%{init: {
     'theme':'base',
     'themeVariables': {
       'primaryColor': '#A2D2FF',
       'primaryTextColor': '#2B2D42',
       'primaryBorderColor': '#A2D2FF',
       'lineColor': '#9D8EC7',
       'clusterBkg': '#F8FAFC',
       'clusterBorder': '#CBD5E1',
       'fontSize': 12,
       'background': '#FAFAFA'
     },
     'flowchart': {
       'padding': 15,
       'nodeSpacing': 30,
       'rankSpacing': 30,
       'useMaxWidth': true
     }
   }}%%
   ```

2. **节点逻辑**：使用 `subgraph Data Flow ["信息流系统"]` 包装。设定 4 个核心流转节点：
   - 捕捉与汇聚 (Inbox)
   - 灵感发酵与研究产出 (01-03)
   - 核心金库 (04 / 05)
   - 深度与个人 (07 / 08 / 09)
3. **连线逻辑**：Inbox → 产出层 → 核心金库 & 深度层。
4. **配色应用**：定义 `classDef stage` (蓝色系) 和 `classDef core` (粉色系)，核心金库用 `core`，其余用 `stage`。参考 `%%{init}` 中的色彩。

## 3. 执行阶段

1. 基于实时文件扫描结果，严格按照上述模板生成 Markdown 内容
2. 写入 `{WORKSPACE}/10_MOC/Home.md`（默认覆写）
3. 确保没有任何未闭合的代码块或格式错误

## 规则

- **精简至上**：不要在路由表中列出所有的子文件夹，只需提取最关键的 2-3 个。
- **链接**：需要跳转的文件使用 `[[WikiLink]]` 格式
- **语言**：双语（中英文），遵循 `report-rules.md`
- **严禁重复**：MOC 不应包含基础的 `GEMINI.md` 文本重复
