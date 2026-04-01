#!/usr/bin/env bash
# ============================================================
# OpenClaude × LiteLLM Proxy 快速启动脚本
# 配置: 编辑 .env.litellm 填入 API Key 和模型名
# 用法: ./start-litellm.sh [工作目录] [--add-dir 额外目录...]
# 示例:
#   ./start-litellm.sh                     # 交互式选择或使用当前目录
#   ./start-litellm.sh ~/my-project        # 指定工作目录
#   ./start-litellm.sh ~/proj --add-dir ~/lib  # 指定工作目录 + 额外目录
# ============================================================
set -euo pipefail

# 确保 Homebrew 路径可用（非交互 shell 可能缺失）
export PATH="/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.litellm"

# --- 解析工作目录参数 ---
WORKSPACE=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --add-dir|--model|--system-prompt|--append-system-prompt)
      EXTRA_ARGS+=("$1" "$2"); shift 2 ;;
    --*)
      EXTRA_ARGS+=("$1"); shift ;;
    *)
      if [[ -z "$WORKSPACE" ]]; then
        WORKSPACE="$1"
      else
        EXTRA_ARGS+=("$1")
      fi
      shift ;;
  esac
done

# --- 加载 .env.litellm ---
if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ 未找到配置文件: .env.litellm" >&2
  echo "   请复制模板并填入你的 Key:" >&2
  echo "   cp .env.litellm.example .env.litellm" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

# --- 校验必填项 ---
BASE_URL="${LITELLM_BASE_URL:-http://192.168.2.154:4000/v1}"
API_KEY="${OPENAI_API_KEY:-}"
MODEL="${OPENAI_MODEL:-}"

if [[ -z "$API_KEY" || "$API_KEY" == "sk-你的Key" ]]; then
  echo "❌ 请在 .env.litellm 中填入实际的 OPENAI_API_KEY" >&2
  exit 1
fi

if [[ -z "$MODEL" || "$MODEL" == "模型名" ]]; then
  echo "📡 正在查询 LiteLLM 可用模型..."
  MODELS_JSON=$(curl -sf --connect-timeout 5 \
    -H "Authorization: Bearer ${API_KEY}" \
    "${BASE_URL}/models" 2>/dev/null || echo "")

  if [[ -n "$MODELS_JSON" ]]; then
    echo "$MODELS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = [m['id'] for m in data.get('data', [])]
if models:
    print('可用模型:')
    for i, m in enumerate(models, 1):
        print(f'  {i}. {m}')
else:
    print('未找到模型')
" 2>/dev/null || echo "  (解析失败)"
  fi

  echo ""
  echo "❌ 请在 .env.litellm 中填入 OPENAI_MODEL" >&2
  exit 1
fi

# --- 切换到工作目录 ---
if [[ -n "$WORKSPACE" ]]; then
  WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd)" || {
    echo "❌ 工作目录不存在: $WORKSPACE" >&2
    exit 1
  }
  cd "$WORKSPACE"
fi

# --- 导出环境变量并启动 ---
export CLAUDE_CODE_USE_OPENAI=1
export OPENAI_BASE_URL="$BASE_URL"
export OPENAI_API_KEY="$API_KEY"
export OPENAI_MODEL="$MODEL"

echo ""
echo "🚀 启动 OpenClaude"
echo "   Workspace: $(pwd)"
echo "   Base URL : $OPENAI_BASE_URL"
echo "   Model    : $OPENAI_MODEL"
echo "   Key      : ${OPENAI_API_KEY:0:8}..."
echo ""

exec node "${SCRIPT_DIR}/dist/cli.mjs" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
