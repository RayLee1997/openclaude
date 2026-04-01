---
date: 2026-04-02
tags: [integration, litellm, provider, openai-compatible]
status: verified
---

# LiteLLM Proxy 接入指南

通过局域网内的 LiteLLM Proxy 将 OpenClaude 接入任意后端模型（Claude, GPT, Gemini, DeepSeek, 本地模型等）。

## 架构概览

```
OpenClaude CLI
      │
      ▼
openaiShim.ts (Anthropic ↔ OpenAI 协议转译)
      │
      ▼  POST /v1/chat/completions
LiteLLM Proxy (192.168.2.154:4000)
      │
      ▼  路由到配置的后端
任意 LLM Provider
```

## 前置条件

| 项目 | 要求 |
|------|------|
| LiteLLM Proxy | 已部署并运行在 `192.168.2.154:4000` |
| API 认证 | LiteLLM 已启用 Master Key 认证（已验证） |
| 网络 | 本机可达 LiteLLM 所在局域网 |

**兼容性验证**（2026-04-02）：

```bash
$ curl -s http://192.168.2.154:4000/v1/models
{"error":{"message":"Authentication Error, No api key passed in.","type":"auth_error","param":"None","code":"401"}}
```

返回标准 OpenAI error response format，确认为 OpenAI-compatible 服务。

## 快速接入

### 方案 A：环境变量（推荐）

```bash
export CLAUDE_CODE_USE_OPENAI=1
export OPENAI_BASE_URL=http://192.168.2.154:4000/v1
export OPENAI_MODEL=<litellm中配置的模型名>
export OPENAI_API_KEY=<你的LiteLLM Master Key>

# 启动
bun run dev
# 或
node dist/cli.mjs
```

### 方案 B：Profile 持久化

```bash
# 1. 初始化 Profile
bun run profile:init -- --provider openai \
  --api-key <你的LiteLLM Master Key> \
  --model <模型名>

# 2. 手动修改 .openclaude-profile.json，将 OPENAI_BASE_URL 改为：
#    "OPENAI_BASE_URL": "http://192.168.2.154:4000/v1"

# 3. 启动
bun run dev:profile
```

> [!TIP]
> Profile 文件 `.openclaude-profile.json` 已在 `.gitignore` 中，不会泄露密钥。

## 源码关键路径

理解接入机制所涉及的核心代码：

| 文件 | 职责 |
|------|------|
| `src/services/api/openaiShim.ts` | Anthropic ↔ OpenAI 协议转译层，发起 `fetch` 请求到 `OPENAI_BASE_URL/chat/completions` |
| `src/services/api/providerConfig.ts` | 解析 `OPENAI_BASE_URL` / `OPENAI_MODEL`，路由 transport 类型 |
| `src/entrypoints/cli.tsx` | 启动校验：检查 API Key 是否存在，`isLocalProviderUrl()` 判断是否为本地 |

## 注意事项

### 1. 局域网 IP 不被视为 "local"

`isLocalProviderUrl()` 仅识别 `localhost` / `127.0.0.1` / `::1`。

`192.168.x.x` 属于 RFC 1918 私网地址，**不在白名单内**，因此 `OPENAI_API_KEY` **必须设置**，否则启动时会报错退出：

```
OPENAI_API_KEY is required when CLAUDE_CODE_USE_OPENAI=1 and OPENAI_BASE_URL is not local.
```

### 2. 模型名映射

`OPENAI_MODEL` 的值必须与 LiteLLM Proxy 配置中的 `model_name` 一致。查询可用模型：

```bash
curl -s http://192.168.2.154:4000/v1/models \
  -H "Authorization: Bearer <你的Key>" | python3 -m json.tool
```

### 3. Codex 别名冲突

避免使用 `codexplan` / `codexspark` 作为模型名——这些会被 `providerConfig.ts` 拦截并路由到 Codex Responses API 而非 Chat Completions。

### 4. 可选优化：扩展私网识别

如果希望局域网 IP 无需 API Key（即 LiteLLM 未设密码认证的场景），可修改 `isLocalProviderUrl()` 增加 RFC 1918 判断：

```typescript
// src/entrypoints/cli.tsx & src/services/api/providerConfig.ts
function isLocalProviderUrl(baseUrl: string | undefined): boolean {
  if (!baseUrl) return false
  try {
    const parsed = new URL(baseUrl)
    const h = parsed.hostname
    return (
      h === 'localhost' || h === '127.0.0.1' || h === '::1' ||
      h.startsWith('192.168.') ||
      h.startsWith('10.') ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(h)
    )
  } catch {
    return false
  }
}
```

> [!WARNING]
> 此修改仅建议在受信任的局域网环境使用，生产环境应始终启用 API Key 认证。

## 故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| `Authentication Error, No api key passed in` | LiteLLM 要求认证 | 设置 `OPENAI_API_KEY` 为 LiteLLM Master Key |
| `OPENAI_API_KEY is required...` | OpenClaude 启动校验拒绝 | 设置任意非空 `OPENAI_API_KEY` |
| `connect ECONNREFUSED` | LiteLLM 服务未运行或网络不通 | 检查 `curl http://192.168.2.154:4000/health` |
| 模型返回 `model not found` | 模型名与 LiteLLM 配置不匹配 | 通过 `/v1/models` 接口确认可用模型名 |
| 工具调用失败 | 后端模型不支持 function calling | 在 LiteLLM 中切换到支持 tool calling 的模型 |
