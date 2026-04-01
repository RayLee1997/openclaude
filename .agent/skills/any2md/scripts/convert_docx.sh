#!/usr/bin/env bash
# =============================================================================
# convert_docx.sh — DOCX → Markdown 转换器（pandoc 直转）
#
# 用法: bash convert_docx.sh <docx文件> <工作目录>
#
# 参数:
#   $1 - DOCX 文件路径（必须，绝对路径或相对路径）
#   $2 - 工作目录路径（必须，图片提取暂存目录）
#
# 输出: 在 DOCX 同级目录生成 {stem}.md 和 images/（如有）
#
# 依赖: conda 环境 marker（含 pandoc 3.9）
# =============================================================================
set -euo pipefail

# -- 依赖检查 --
command -v conda >/dev/null 2>&1 || { echo "❌ Missing: conda" >&2; exit 1; }

# -- 参数解析 --
DOCX_FILE="${1:?Missing argument: DOCX file path}"
BUILD_DIR="${2:?Missing argument: build directory path}"

# 解析为绝对路径
DOCX_FILE="$(cd "$(dirname "$DOCX_FILE")" && pwd)/$(basename "$DOCX_FILE")"

if [ ! -f "$DOCX_FILE" ]; then
    echo "❌ File not found: $DOCX_FILE" >&2
    exit 1
fi

DOCX_DIR="$(dirname "$DOCX_FILE")"
DOCX_STEM="$(basename "$DOCX_FILE")"
# 去除 .docx 或 .doc 扩展名
DOCX_STEM="${DOCX_STEM%.docx}"
DOCX_STEM="${DOCX_STEM%.DOCX}"

# -- 环境激活 --
echo "🔧 Activating conda marker environment (for pandoc)..." >&2
eval "$(conda shell.bash hook)"
conda activate marker

if ! command -v pandoc >/dev/null 2>&1; then
    echo "❌ pandoc not found in conda marker env" >&2
    echo "   Fix: conda install -n marker -c conda-forge pandoc" >&2
    exit 1
fi

PANDOC_VER="$(pandoc --version | head -1 | awk '{print $2}')"
echo "   pandoc $PANDOC_VER ready" >&2

# -- 执行转换 --
echo "📝 Converting DOCX → Markdown (pandoc)..." >&2
echo "   Source: $DOCX_FILE" >&2
echo "   Build:  $BUILD_DIR" >&2

mkdir -p "$BUILD_DIR"

# pandoc 图片提取目录（media/）
MEDIA_DIR="$BUILD_DIR/media"
OUTPUT_MD="$BUILD_DIR/${DOCX_STEM}.md"

pandoc \
    --from=docx \
    --to=markdown \
    --wrap=none \
    --extract-media="$BUILD_DIR" \
    -o "$OUTPUT_MD" \
    "$DOCX_FILE" 2>&1

if [ ! -f "$OUTPUT_MD" ]; then
    echo "❌ pandoc output not found: $OUTPUT_MD" >&2
    exit 1
fi

# -- 整理输出 --

# 统计提取的图片数量
IMG_COUNT=0
if [ -d "$MEDIA_DIR" ]; then
    IMG_COUNT=$(find "$MEDIA_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
fi

# 处理图片：将 media/ 重命名为 images/ 并修正路径
if [ "$IMG_COUNT" -gt 0 ]; then
    # 在目标目录创建 images/
    mkdir -p "$DOCX_DIR/images"

    # 复制提取的图片到目标目录，扁平化文件名
    IMG_IDX=0
    find "$MEDIA_DIR" -type f | sort | while read -r img; do
        EXT="${img##*.}"
        # 保留原始文件名，避免冲突时加序号
        ORIG_NAME="$(basename "$img")"
        if [ -f "$DOCX_DIR/images/$ORIG_NAME" ]; then
            ORIG_NAME="${IMG_IDX}_${ORIG_NAME}"
        fi
        cp "$img" "$DOCX_DIR/images/$ORIG_NAME"
        IMG_IDX=$((IMG_IDX + 1))
    done

    # 修正 .md 中的图片引用路径
    # pandoc 输出格式: ![alt](BUILD_DIR/media/xxx.png) → ![alt](images/xxx.png)
    # 使用 sed 替换路径（兼容 GNU / BSD macOS）
    ESCAPED_BUILD="$(echo "$BUILD_DIR" | sed 's/[\/&]/\\&/g')"
    if sed --version 2>/dev/null | grep -q GNU; then
        sed -i "s|${ESCAPED_BUILD}/media/|images/|g" "$OUTPUT_MD"
    else
        sed -i '' "s|${ESCAPED_BUILD}/media/|images/|g" "$OUTPUT_MD"
    fi
    echo "   ✅ Images: $IMG_COUNT files → images/" >&2
fi

# 移动 .md 到 DOCX 同级目录
mv "$OUTPUT_MD" "$DOCX_DIR/${DOCX_STEM}.md"
echo "   ✅ Output: $DOCX_DIR/${DOCX_STEM}.md" >&2

# -- 输出结果摘要（供 any2md.sh 解析） --
echo "RESULT_MD=$DOCX_DIR/${DOCX_STEM}.md"
echo "RESULT_IMAGES=$IMG_COUNT"
echo "RESULT_ENGINE=pandoc $PANDOC_VER"
