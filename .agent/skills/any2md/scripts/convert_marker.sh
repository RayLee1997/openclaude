#!/usr/bin/env bash
# =============================================================================
# convert_marker.sh — 通用文档 → Markdown 转换器（Marker + Gemini LLM 增强）
#
# 用法: bash convert_marker.sh <文件> <工作目录> [选项]
#
# 参数:
#   $1 - 输入文件路径（必须，支持 EPUB/PPTX/XLSX/HTML/Image 等）
#   $2 - 工作目录路径（必须，Marker 输出暂存目录）
#
# 选项:
#   --languages STR          指定语言（如 "Chinese,English"）
#   --strip_existing_ocr     去除已有 OCR 层后重新识别
#
# 输出: 在源文件同级目录生成 {stem}.md 和 images/（如有）
#
# 配置: resources/config.json（LLM 模型、输出格式等默认参数）
# 日志: 双通道 — stderr(console) + $BUILD_DIR/build.log
#
# 支持格式 [实验]: .epub .pptx .xlsx .html .htm .jpg .jpeg .png .gif .bmp .tiff .tif .webp
# 说明: 这些格式通过 Marker PdfConverter 处理，精度可能不及 PDF 原生支持
#
# 依赖: conda 环境 marker（含 marker-pdf ≥1.10.2）
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$SKILL_DIR/resources/config.json"

# -- 日志辅助函数 --
_BUILD_LOG=""
_log() {
    echo "$*" >&2
    [ -n "$_BUILD_LOG" ] && echo "[$(date '+%H:%M:%S')] $*" >> "$_BUILD_LOG" || true
}

# -- 依赖检查 --
command -v conda >/dev/null 2>&1 || { echo "❌ Missing: conda" >&2; exit 1; }

# -- 配置文件检查 --
if [ ! -f "$CONFIG_FILE" ]; then
    _log "⚠️  Config not found: $CONFIG_FILE, using Marker defaults"
fi

# -- 参数解析 --
INPUT_FILE="${1:?Missing argument: input file path}"
BUILD_DIR="${2:?Missing argument: build directory path}"

# 解析为绝对路径
INPUT_FILE="$(cd "$(dirname "$INPUT_FILE")" && pwd)/$(basename "$INPUT_FILE")"

if [ ! -f "$INPUT_FILE" ]; then
    echo "❌ File not found: $INPUT_FILE" >&2
    exit 1
fi

INPUT_DIR="$(dirname "$INPUT_FILE")"
INPUT_NAME="$(basename "$INPUT_FILE")"
# 泛化扩展名去除：支持任意扩展名
INPUT_STEM="${INPUT_NAME%.*}"

# 可选参数
LANGUAGES=""
STRIP_OCR=""
shift 2
while [ $# -gt 0 ]; do
    case "$1" in
        --languages)           LANGUAGES="--languages $2"; shift 2 ;;
        --strip_existing_ocr)  STRIP_OCR="--strip_existing_ocr"; shift ;;
        *)                     echo "⚠️  Unknown option: $1" >&2; shift ;;
    esac
done

# -- 环境激活 --
_log "🔧 Activating conda marker environment..."
eval "$(conda shell.bash hook)"
conda activate marker

if ! command -v marker_single >/dev/null 2>&1; then
    echo "❌ marker_single not found in conda marker env" >&2
    echo "   Fix: conda run -n marker pip install marker-pdf" >&2
    exit 1
fi

# -- 双通道日志初始化 --
mkdir -p "$BUILD_DIR"
_BUILD_LOG="$BUILD_DIR/build.log"
echo "========================================" > "$_BUILD_LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] convert_marker.sh [实验]" >> "$_BUILD_LOG"
echo "  Source: $INPUT_FILE" >> "$_BUILD_LOG"
echo "  Config: $CONFIG_FILE" >> "$_BUILD_LOG"
echo "========================================" >> "$_BUILD_LOG"

# -- 执行转换 --
_log "🧪 Converting → Markdown (Marker [实验] + Gemini LLM)..."
_log "   Source: $INPUT_FILE"
_log "   Build:  $BUILD_DIR"
_log "   Config: $CONFIG_FILE"

# 构建 marker_single 命令
MARKER_ARGS=(
    marker_single "$INPUT_FILE"
    --use_llm
    --output_format markdown
    --output_dir "$BUILD_DIR"
)

# 追加配置文件（如果存在）
[ -f "$CONFIG_FILE" ] && MARKER_ARGS+=(--config_json "$CONFIG_FILE")

# 追加可选参数
[ -n "$LANGUAGES" ]  && MARKER_ARGS+=($LANGUAGES)
[ -n "$STRIP_OCR" ]  && MARKER_ARGS+=($STRIP_OCR)

_log "   Command: ${MARKER_ARGS[*]}"

# 执行 marker_single，输出写入 build.log
PYTHONUNBUFFERED=1 "${MARKER_ARGS[@]}" >> "$_BUILD_LOG" 2>&1

# -- 整理输出 --
# Marker 输出结构: BUILD_DIR/{stem}/{stem}.md + images/
MARKER_OUT="$BUILD_DIR/$INPUT_STEM"

if [ ! -d "$MARKER_OUT" ]; then
    _log "❌ Marker output directory not found: $MARKER_OUT"
    exit 1
fi

# 移动 .md 到源文件同级目录
if [ -f "$MARKER_OUT/${INPUT_STEM}.md" ]; then
    mv "$MARKER_OUT/${INPUT_STEM}.md" "$INPUT_DIR/${INPUT_STEM}.md"
    _log "   ✅ Output: $INPUT_DIR/${INPUT_STEM}.md"
else
    _log "❌ Markdown output not found: $MARKER_OUT/${INPUT_STEM}.md"
    exit 1
fi

# 移动 images/ 到源文件同级目录（如有）
IMG_COUNT=0
if [ -d "$MARKER_OUT/images" ]; then
    IMG_COUNT=$(find "$MARKER_OUT/images" -type f 2>/dev/null | wc -l | tr -d ' ')
    if [ "$IMG_COUNT" -gt 0 ]; then
        mkdir -p "$INPUT_DIR/images"
        cp -r "$MARKER_OUT/images/"* "$INPUT_DIR/images/" 2>/dev/null || true
        _log "   ✅ Images: $IMG_COUNT files → images/"
    fi
fi

# 清理 Marker 临时子目录
rm -rf "$MARKER_OUT"

_log "✅ convert_marker.sh completed"

# -- 输出结果摘要（供 any2md.sh 解析） --
echo "RESULT_MD=$INPUT_DIR/${INPUT_STEM}.md"
echo "RESULT_IMAGES=$IMG_COUNT"
echo "RESULT_ENGINE=Marker [实验] + Gemini LLM"
