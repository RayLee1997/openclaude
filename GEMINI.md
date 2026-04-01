# GEMINI.md

本工作区是 **OpenClaude** — 一个 Claude Code 的开源 Fork，通过 OpenAI-compatible API shim 将 Claude Code 的完整工具链（Bash, FileEdit, Grep, Agent, MCP 等）接入任意 LLM（GPT-4o, DeepSeek, Gemini, Ollama, Codex 等）。技术栈为 **TypeScript + Bun + React Ink CLI**，核心架构是 `src/services/api/openaiShim.ts` 实现的 Anthropic ↔ OpenAI 协议转译层。

## 1. 空间拓扑 (Taxonomy)

* **核心区**: `src/` (主源码，35+ 子模块), `scripts/` (构建与 Provider 引导), `bin/` (CLI 入口)
* **文档**: `README.md` (项目说明), `PLAYBOOK.md` (本地 Agent 运维手册)
* **系统目录**: `.agent/` (Agent 配置栈)
* **辅助文件**: `ollama_provider.py`, `smart_router.py` (Python Provider 实验)

## 2. Agent 武器库 (Ecosystem)

挂载于 `.agent/` 目录下，按需触发：

* **Skills (领域专长)**: `any2md`, `mermaid-chart`, `script-coder`, `web-research`
* **Workflows (SOP)**: `/compact`, `/create-agent-skill-plan`, `/create-deep-research-plan`, `/create-moc`, `/create-tech-tutorial`, `/git-push`, `/init`, `/rsync-lenovo`
* **MCP Servers**: `brave-search`, `context7`, `edgartools`, `fred-mcp-server`, `stitch`, `yfinance`

## 3. Agent 纪律法典 (Rules)

以下配置为 **Always On**，严格约束 Agent 输出格式与行为逻辑：

1. **[输出门控] `report-rules.md`**: 强制双语策略、5大语调域、思维模型(MECE/第一性原理)、视觉标准(Mermaid Healing Dream)、防截断护栏、起草与润色归档模板。
2. **[行动编排] `workflow-orchestration-rules.md`**: 强制计划先行(Plan Default)、工具并行卸载、零中断除错、验证交付底线(Staff Engineer 标准)。

> ⚠️ **严禁在此文件堆砌行为指令**。任何新的纪律要求、撰写模板、动作指令，必须下沉到 `.agent/rules/` 或封装为具体 Skill。

---

*Last initialized: 2026-04-02*
