#!/usr/bin/env bash
# =============================================================================
# any2md.sh — 文档 → Markdown 统一入口（自动检测文件类型 + 分发）
#
# 用法: bash any2md.sh <输入文件> [选项]
#
# 参数:
#   $1 - 输入文件路径（必须）
#
# 选项（仅 PDF 有效）:
#   --force_ocr              强制 OCR（扫描件/图片 PDF）
#   --page_range STR         指定页范围（如 "0-9"）
#
# 选项（PDF + 实验格式 有效）:
#   --languages STR          指定语言（如 "Chinese,English"）
#   --strip_existing_ocr     去除已有 OCR 层后重新识别
#
# 输出: 在源文件同级目录生成 {stem}.md 和 images/（如有）
# 工作目录: 源文件所在目录下的 .build_md/（转换完成后自动清理）
#
# 支持格式:
#   .pdf  → Marker + Gemini LLM 增强（最高精度）
#   .docx → pandoc 直转（表格/列表/图片完整保留）
#   .epub .pptx .xlsx → Marker [实验]
#   .jpg .jpeg .png .gif .bmp .tiff .tif .webp → Marker [实验]
#
# 依赖: conda 环境 marker（含 marker-pdf, pandoc）
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# -- 参数解析 --
INPUT_FILE="${1:?Usage: bash any2md.sh <input_file> [--force_ocr] [--page_range \"0-9\"] [--languages \"Chinese,English\"]}"

# 解析为绝对路径
INPUT_FILE="$(cd "$(dirname "$INPUT_FILE")" && pwd)/$(basename "$INPUT_FILE")"

if [ ! -f "$INPUT_FILE" ]; then
    echo "❌ File not found: $INPUT_FILE" >&2
    exit 1
fi

INPUT_DIR="$(dirname "$INPUT_FILE")"
INPUT_NAME="$(basename "$INPUT_FILE")"
INPUT_EXT="${INPUT_NAME##*.}"
INPUT_EXT_LOWER="$(echo "$INPUT_EXT" | tr '[:upper:]' '[:lower:]')"

BUILD_DIR="$INPUT_DIR/.build_md"

# 收集额外选项（传递给子脚本）
shift
EXTRA_ARGS=("$@")

# -- 清理函数 --
cleanup() {
    if [ -d "$BUILD_DIR" ]; then
        rm -rf "$BUILD_DIR"
    fi
}
trap cleanup EXIT

echo "============================================"
echo "  any2md — 文档 → Markdown 转换"
echo "============================================"
echo "  输入: $INPUT_NAME"
echo "  目录: $INPUT_DIR"
echo "  格式: .$INPUT_EXT_LOWER"
echo "  构建: $BUILD_DIR"
echo "============================================"
echo ""

# -- 文件类型检测 + 分发 --
case "$INPUT_EXT_LOWER" in
    pdf)
        echo "📄 Detected: PDF → dispatching to convert_pdf.sh"
        echo ""
        RESULT="$(bash "$SCRIPT_DIR/convert_pdf.sh" "$INPUT_FILE" "$BUILD_DIR" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")"
        ;;
    docx)
        echo "📝 Detected: DOCX → dispatching to convert_docx.sh"
        echo ""
        if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
            echo "⚠️  Options ${EXTRA_ARGS[*]} are PDF-only, ignored for DOCX" >&2
        fi
        RESULT="$(bash "$SCRIPT_DIR/convert_docx.sh" "$INPUT_FILE" "$BUILD_DIR")"
        ;;
    epub)
        echo "🧪 Detected: EPUB → dispatching to convert_marker.sh [实验]"
        echo ""
        RESULT="$(bash "$SCRIPT_DIR/convert_marker.sh" "$INPUT_FILE" "$BUILD_DIR" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")"
        ;;
    pptx)
        echo "🧪 Detected: PPTX → dispatching to convert_marker.sh [实验]"
        echo ""
        RESULT="$(bash "$SCRIPT_DIR/convert_marker.sh" "$INPUT_FILE" "$BUILD_DIR" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")"
        ;;
    xlsx)
        echo "🧪 Detected: XLSX → dispatching to convert_marker.sh [实验]"
        echo ""
        RESULT="$(bash "$SCRIPT_DIR/convert_marker.sh" "$INPUT_FILE" "$BUILD_DIR" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")"
        ;;
    jpg|jpeg|png|gif|bmp|tiff|tif|webp)
        echo "🧪 Detected: Image → dispatching to convert_marker.sh [实验]"
        echo ""
        RESULT="$(bash "$SCRIPT_DIR/convert_marker.sh" "$INPUT_FILE" "$BUILD_DIR" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")"
        ;;
    *)
        echo "❌ Unsupported file format: .$INPUT_EXT_LOWER" >&2
        echo "   Supported: .pdf, .docx, .epub, .pptx, .xlsx, .jpg, .jpeg, .png, .gif, .bmp, .tiff, .webp" >&2
        exit 1
        ;;
esac

# -- 解析子脚本结果 --
RESULT_MD="$(echo "$RESULT" | grep '^RESULT_MD=' | cut -d= -f2-)"
RESULT_IMAGES="$(echo "$RESULT" | grep '^RESULT_IMAGES=' | cut -d= -f2-)"
RESULT_ENGINE="$(echo "$RESULT" | grep '^RESULT_ENGINE=' | cut -d= -f2-)"

# -- 汇报结果 --
echo ""
echo "============================================"
echo "  ✅ 转换完成!"
echo "============================================"
echo "  源文件: $INPUT_NAME"
echo "  引擎:   $RESULT_ENGINE"
echo "  图片:   $RESULT_IMAGES 张"
echo "  输出:   $RESULT_MD"
echo "============================================"
