---
description: 深度工作区初始化 — 扫描结构、生成知识图谱、配置 Agent 生态系统 (合并 /init-agent 功能)
---

# Init: 深度工作区初始化工作流

> 你是一位 **首席知识架构师 (Chief Knowledge Architect)**，负责分析当前工作空间并生成 `GEMINI.md` — Agent 的「上下文大脑」。
> 此文件作为 Agent 在该工作空间中所有会话的持久化记忆基础。

---

## Phase 0: 前置检查

1. 检测当前工作空间的根目录路径
2. 检查是否已存在 `GEMINI.md` 文件
   - **已存在**：以「增量更新」模式执行，保留用户自定义内容，仅补充/刷新自动生成部分
   - **不存在**：以「全新创建」模式执行
3. 确认输出目标路径：`<workspace-root>/GEMINI.md`

---

## Phase 1: 信息架构分析

> 目标：全面理解工作空间的组织逻辑、内容类型与技术栈。

### 1.1 目录结构扫描

// turbo
4. 使用 `list_dir` 扫描根目录（深度 1），记录所有顶层文件夹名称
5. 对每个顶层文件夹，使用 `list_dir` 扫描直接子目录（深度 2），理解层级关系
6. 识别分类体系模式（P.A.R.A. / Johnny Decimal / Zettelkasten / 自由分类）

### 1.2 文件格式与内容分析

// turbo
7. 使用 `find_by_name` 统计各文件类型数量：`.md`, `.json`, `.yaml`, `.py`, `.js`, `.ts` 等
8. 随机抽样 5-8 个 `.md` 文件，分析：

- Frontmatter 格式与常见字段
- 标题层级用法
- 链接风格（标准 Markdown vs Wiki-link）
- 中英文比例
- 内容类型（笔记、研报、教程等）

1. 检查图表工具使用痕迹（Mermaid / PlantUML / Excalidraw / draw.io）

### 1.3 Agent 生态系统盘点

// turbo
10. 扫描 `.agent/` 目录结构：
    - `rules/`：列出所有规则文件，读取摘要
    - `skills/`：读取每个 `SKILL.md` 的 YAML Frontmatter（name, description, 触发场景）
    - `workflows/`：读取每个工作流的 YAML Frontmatter（description）
11. 检查 MCP Server 配置（`mcp_config.json` 等），记录已配置的 Server
12. 检查其他 Agent 上下文文件（`.cursorrules`, `AGENTS.md` 等）

---

## Phase 2: GEMINI.md 内容生成

> 基于 Phase 1 分析结果，生成结构化 `GEMINI.md`。

### 输出规范

- **语言**：与工作空间主要语言一致，技术术语保留英文
- **格式**：标准 Markdown，善用表格展示结构化信息
- **精炼原则**：高信噪比，避免冗余——因为 GEMINI.md 消耗 Context Window Token 预算

### GEMINI.md 必需章节

生成的 `GEMINI.md` 包含 **3 个核心章节 + 1 个元数据段**：

---

#### 核心内容模板 (Ultra-Slim 架构)

```markdown
# GEMINI.md

本核心工作区是 Ray 的**第二大脑与投资研究指挥中心**，完全由 AI Agent (Antigravity) 驱动。

## 1. 空间拓扑 (Taxonomy)

* **主目录**: [将顶层目录名称用反引号括起并以逗号分隔列出，例如 `00_Inbox`, `01_Research` 等，标注出核心区]
* **系统目录**: `agent-sessions/` (上下文快照) 与 `.agent/` (Agent 配置栈)
> 📌 **导航主入口**：所有子目录细节与业务上下文，统一查阅 `10_MOC/Home.md`。

## 2. Agent 武器库 (Ecosystem)

挂载于 `.agent/` 目录下，按需触发：

* **Skills (领域专长)**: [读取 .agent/skills/，将所有技能名称用反引号括起、以逗号分隔列出]
* **Workflows (SOP)**: [读取 .agent/workflows/，将所有工作流命令名称用反引号括起、以逗号分隔列出]
* **MCP Servers**: [读取 MCP 面板配置，将所有 Server 名称用反引号括起、以逗号分隔列出]

## 3. Agent 纪律法典 (Rules)

以下配置为 **Always On**，严格约束 Agent 输出格式与行为逻辑：

1. **[输出门控] `report-rules.md`**: 强制双语策略、5大语调域、思维模型(MECE/第一性原理)、视觉标准(Mermaid Healing Dream)、防截断护栏、起草与润色归档模板。
2. **[行动编排] `workflow-orchestration-rules.md`**: 强制计划先行(Plan Default)、工具并行卸载、零中断除错、验证交付底线(Staff Engineer 标准)。

> ⚠️ **严禁在此文件堆砌行为指令**。任何新的纪律要求、撰写模板、动作指令，必须下沉到 `.agent/rules/` 或封装为具体 Skill。
```

> [!IMPORTANT]
> **分类体系**与 **Agent 武器库**仅保留名称枚举。**必须完全摒弃所有的 Markdown 表格、说明清单和长段落描述**。所有的详细内容（如用例、触发词、协同策略）由各独立的 `SKILL.md` 和 `10_MOC/Home.md` 承载，只为节约 System Prompt 的 Token。

---

#### 元数据段

```markdown
---

*Last initialized: YYYY-MM-DD*
```

---

## Phase 3: 写入与验证

1. 使用 `write_to_file` 将内容写入 `<workspace-root>/GEMINI.md`
   - 更新模式设置 `Overwrite: true`
   - 复杂度评级：8
2. 使用 `view_file` 验证：
   - 3 个核心章节完整
   - 表格格式正确
   - 无 content/report-rules 内容重复
3. 使用 `notify_user` 汇报结果，请求审阅

---

## 最佳实践

> [!IMPORTANT]
> **GEMINI.md 与 report-rules.md 的职责划分**
>
> | 文件 | 职责 | Token 策略 |
> | --- | --- | --- |
> | `GEMINI.md` | 工作区知识图谱 — "这里有什么、怎么组织的" | 加载一次，提供 context |
> | `report-rules.md` | 行为规则引擎 — "每次输出必须怎么做" | Always On，每轮强制执行 |
>
> 两者**互补而非重复**。GEMINI.md 不重复 report-rules.md 中的内容。

> [!TIP]
> **层级上下文系统**
>
> 1. **全局层** (`~/.gemini/GEMINI.md`)：个人偏好，跨项目生效
> 2. **项目层** (根目录 `GEMINI.md`)：项目特定规则和上下文
> 3. **组件层** (子目录 `GEMINI.md`)：模块级别指令
>
> 更具体的文件优先级更高。

> [!NOTE]
> **Agent 文件体系**
>
> - `GEMINI.md`：持久化上下文（每次对话自动注入）
> - `.agent/rules/`：激活规则（Always On 等 4 种模式）
> - `.agent/skills/`：按需技能（相关任务时加载）
> - `.agent/workflows/`：触发式工作流（`/command` 手动触发）
