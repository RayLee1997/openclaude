#!/usr/bin/env bash
# =============================================================================
# convert_pdf.sh — PDF → Markdown 转换器（Marker + Gemini LLM 增强）
#
# 用法: bash convert_pdf.sh <pdf文件> <工作目录> [选项]
#
# 参数:
#   $1 - PDF 文件路径（必须，绝对路径或相对路径）
#   $2 - 工作目录路径（必须，Marker 输出暂存目录）
#
# 选项:
#   --force_ocr              强制 OCR（扫描件/图片 PDF）
#   --page_range STR         指定页范围（如 "0-9"）
#   --languages STR          指定语言（如 "Chinese,English"）
#   --strip_existing_ocr     去除已有 OCR 层后重新识别
#
# 输出: 在 PDF 同级目录生成 {stem}.md 和 images/（如有）
#
# 配置: resources/config.json（LLM 模型、输出格式等默认参数）
# 日志: 双通道 — stderr(console) + $BUILD_DIR/build.log
#
# 依赖: conda 环境 marker（含 marker-pdf, surya-ocr）
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$SKILL_DIR/resources/config.json"

# -- 日志辅助函数 --
# 双通道：stderr(console) + build.log（如已初始化）
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
PDF_FILE="${1:?Missing argument: PDF file path}"
BUILD_DIR="${2:?Missing argument: build directory path}"

# 解析为绝对路径
PDF_FILE="$(cd "$(dirname "$PDF_FILE")" && pwd)/$(basename "$PDF_FILE")"

if [ ! -f "$PDF_FILE" ]; then
    echo "❌ File not found: $PDF_FILE" >&2
    exit 1
fi

PDF_DIR="$(dirname "$PDF_FILE")"
# 大小写不敏感去除 .pdf/.PDF/.Pdf 等扩展名
_pdf_basename="$(basename "$PDF_FILE")"
PDF_STEM="${_pdf_basename%.[pP][dD][fF]}"

# 可选参数
FORCE_OCR=""
PAGE_RANGE=""
LANGUAGES=""
STRIP_OCR=""
shift 2
while [ $# -gt 0 ]; do
    case "$1" in
        --force_ocr)           FORCE_OCR="--force_ocr"; shift ;;
        --page_range)          PAGE_RANGE="--page_range $2"; shift 2 ;;
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
echo "[$(date '+%Y-%m-%d %H:%M:%S')] convert_pdf.sh" >> "$_BUILD_LOG"
echo "  Source: $PDF_FILE" >> "$_BUILD_LOG"
echo "  Config: $CONFIG_FILE" >> "$_BUILD_LOG"
echo "========================================" >> "$_BUILD_LOG"

# -- 执行转换 --
_log "📄 Converting PDF → Markdown (Marker + Gemini LLM)..."
_log "   Source: $PDF_FILE"
_log "   Build:  $BUILD_DIR"
_log "   Config: $CONFIG_FILE"

# 构建 marker_single 命令
MARKER_ARGS=(
    marker_single "$PDF_FILE"
    --use_llm
    --output_format markdown
    --output_dir "$BUILD_DIR"
)

# 追加配置文件（如果存在）
[ -f "$CONFIG_FILE" ] && MARKER_ARGS+=(--config_json "$CONFIG_FILE")

# 追加可选参数
[ -n "$FORCE_OCR" ]  && MARKER_ARGS+=($FORCE_OCR)
[ -n "$PAGE_RANGE" ] && MARKER_ARGS+=($PAGE_RANGE)
[ -n "$LANGUAGES" ]  && MARKER_ARGS+=($LANGUAGES)
[ -n "$STRIP_OCR" ]  && MARKER_ARGS+=($STRIP_OCR)

_log "   Command: ${MARKER_ARGS[*]}"

# 执行 marker_single，输出同时写入 build.log
PYTHONUNBUFFERED=1 "${MARKER_ARGS[@]}" >> "$_BUILD_LOG" 2>&1

# -- 整理输出 --
# Marker 输出结构: BUILD_DIR/{stem}/{stem}.md + images/
MARKER_OUT="$BUILD_DIR/$PDF_STEM"

if [ ! -d "$MARKER_OUT" ]; then
    _log "❌ Marker output directory not found: $MARKER_OUT"
    exit 1
fi

# 移动 .md 到 PDF 同级目录
if [ -f "$MARKER_OUT/${PDF_STEM}.md" ]; then
    mv "$MARKER_OUT/${PDF_STEM}.md" "$PDF_DIR/${PDF_STEM}.md"
    _log "   ✅ Output: $PDF_DIR/${PDF_STEM}.md"
else
    _log "❌ Markdown output not found: $MARKER_OUT/${PDF_STEM}.md"
    exit 1
fi

# 移动 images/ 到 PDF 同级目录（如有）
IMG_COUNT=0
if [ -d "$MARKER_OUT/images" ]; then
    IMG_COUNT=$(find "$MARKER_OUT/images" -type f 2>/dev/null | wc -l | tr -d ' ')
    if [ "$IMG_COUNT" -gt 0 ]; then
        # 如已有 images/ 目录，合并进去
        mkdir -p "$PDF_DIR/images"
        cp -r "$MARKER_OUT/images/"* "$PDF_DIR/images/" 2>/dev/null || true
        _log "   ✅ Images: $IMG_COUNT files → images/"
    fi
fi

# 清理 Marker 临时子目录
rm -rf "$MARKER_OUT"

_log "✅ convert_pdf.sh completed"

# -- 输出结果摘要（供 any2md.sh 解析） --
echo "RESULT_MD=$PDF_DIR/${PDF_STEM}.md"
echo "RESULT_IMAGES=$IMG_COUNT"
echo "RESULT_ENGINE=Marker + Gemini LLM"
