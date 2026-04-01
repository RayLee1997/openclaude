---
name: any2md
description: >-
  将多种文档格式转换为高精度 Markdown。
  PDF 使用 Marker + Gemini LLM 增强模式，精度最高；
  DOCX 使用 pandoc 直转，表格/列表/图片完整保留；
  EPUB/PPTX/XLSX/Image 通过 Marker 实验性支持。
  工作目录为源文件所在目录下的 .build_md/，转换完成后自动清理。
  当用户提及"PDF 转换、Word 转换、DOCX 转换、文档解析、提取内容、转 Markdown、
  读取 PDF、解析论文、导入报告、Word 转 Markdown"时触发。
---

# Any to Markdown (多格式支持)

## 功能概述

将多种文档格式转换为高精度 Markdown，根据文件类型自动选择最优转换引擎：

| 格式 | 引擎 | 特点 | 状态 |
|------|------|------|------|
| PDF | Marker + Gemini LLM | 开源最高精度，LLM 增强 10-15% | **稳定** |
| DOCX | pandoc | 一步直转，表格/列表/图片完整保留 | **稳定** |
| EPUB | Marker + Gemini LLM | 电子书转换 | 🧪 实验 |
| PPTX | Marker + Gemini LLM | 演示文稿转换 | 🧪 实验 |
| XLSX | Marker + Gemini LLM | 电子表格转换 | 🧪 实验 |
| Image | Marker + Gemini LLM (OCR) | JPG/PNG/GIF/BMP/TIFF/WebP | 🧪 实验 |

## 使用时机

- **PDF 导入知识库**：投资研报、财报、白皮书、学术论文
- **Word 文档转换**：会议纪要、合同、报告等 .docx 文件
- **复杂文档解析**：含表格、公式、多栏排版、图片的文档
- **批量文档转换**：将一组文档转为 Markdown 存入 Obsidian
- **扫描件/图片 PDF**：需要 OCR 识别的文档（加 `--force_ocr`）
- **电子书转换**：将 EPUB 电子书转为 Markdown
- **图片文字提取**：通过 OCR 从图片中提取文字

**不要使用**：

- 纯文本 PDF 或已有 Markdown 格式的内容
- 用户明确要求使用其他工具（如 MarkItDown）
- 旧版 .doc 格式（仅支持 .docx）

## 前置条件

- **conda 环境**: `marker`（含 marker-pdf ≥1.10.2、pandoc 3.9）
- **Gemini API Key**: 环境变量 `GOOGLE_API_KEY` 已配置（PDF/实验格式转换需要）
- **配置文件**: `resources/config.json`（默认 LLM 模型: `gemini-3-flash-preview`）

## 执行流程

### Step 1: 分析用户意图

从用户消息中确定：

| 信息 | 来源 | 默认值 |
|------|------|--------|
| 文件路径 | 用户提供 | 无（必须） |
| 文件类型 | **自动检测**: 由脚本根据扩展名判断 | — |
| 输出目录 | **强制**: 与源文件同目录 | 源文件所在目录 |
| 工作目录 | **强制**: `.build_md/`（源文件目录下） | 自动创建和清理 |
| LLM 模式 | **强制**: 始终启用（PDF + 实验格式） | `--use_llm` |
| LLM 模型 | `resources/config.json` | `gemini-3-flash-preview` |
| 页范围 | 用户指定（仅 PDF） | 全部页 |
| 强制 OCR | 扫描件/图片 PDF | `false` |
| 语言 | 用户指定 | 自动检测 |

### Step 2: 执行转换

通过 `run_command` 调用主入口脚本 `any2md.sh`：

```bash
# 获取脚本路径（技能目录下的 scripts/）
SKILL_DIR="这里填写实际的 any2md 技能目录路径"

# === PDF 转换 ===
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/input.pdf

# 扫描件 PDF（额外加 --force_ocr）
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/scan.pdf --force_ocr

# 指定页范围
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/input.pdf --page_range "0-9"

# 指定语言
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/input.pdf --languages "Chinese,English"

# === DOCX 转换 ===
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/document.docx

# === 实验格式 ===
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/book.epub
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/slides.pptx
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/data.xlsx
bash "$SKILL_DIR/scripts/any2md.sh" /path/to/photo.jpg
```

> **关键规则**:
>
> - 脚本会**自动检测**文件类型并分发到对应转换器
> - PDF 转换**必须**带 `--use_llm`（脚本内已强制）
> - 工作目录 `.build_md/` 在源文件目录下自动创建，转换完成后自动清理
> - 输出的 `.md` 文件与源文件**同级**
> - LLM 模型配置在 `resources/config.json` 中集中管理

### Step 3: 确认输出

脚本执行完毕后，目标结构为：

```
源文件所在目录/
├── input.pdf / document.docx    # 原始文件（保持不变）
├── input.md / document.md       # ← 转换结果（与源文件同级）
└── images/                      # ← 图片子文件夹（如有）
    ├── img_0.png
    └── img_1.png
```

**不需要手动整理** — 脚本已自动完成文件移动和路径修正。

### Step 4: 向用户汇报结果

```markdown
✅ **文档转换完成**

| 项目 | 详情 |
|------|------|
| 源文件 | `{filename}` |
| 格式 | PDF / DOCX / EPUB / ... |
| 引擎 | Marker + Gemini LLM / pandoc / Marker [实验] |
| 图片 | Y 张 → `images/` |
| 输出 | `{同目录}/{stem}.md` |
```

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| conda 环境不存在 | 提示: `conda create -n marker python=3.12 -y && conda run -n marker pip install marker-pdf` |
| Marker 未安装 | 提示: `conda run -n marker pip install marker-pdf` |
| pandoc 未安装 | 提示: `conda install -n marker -c conda-forge pandoc` |
| 不支持的文件格式 | 告知用户支持的格式列表，旧版 `.doc` 需先转为 `.docx` |
| 转换超时/OOM（PDF） | 1. 减少页范围 `--page_range` 2. 建议分段处理 |
| 首次运行慢（PDF） | 告知用户 Surya 模型约 2GB 需下载，请耐心等待 |
| 文件路径含空格 | 脚本已处理引号包裹，无需额外操作 |
| config.json 不存在 | 脚本会发出警告并使用 Marker 默认配置 |

## 脚本架构

```
any2md/
├── SKILL.md                      # 技能定义（本文件）
├── reference.md                  # 排错手册 + CLI 速查
├── resources/
│   └── config.json               # Marker 配置（LLM 模型、输出格式）
├── scripts/
│   ├── any2md.sh                 # 主入口：文件类型检测 → 分发
│   ├── convert_pdf.sh            # PDF → MD（Marker + Gemini LLM）
│   ├── convert_docx.sh           # DOCX → MD（pandoc 直转）
│   └── convert_marker.sh         # 实验格式 → MD（Marker 通用转换）
└── tests/
    ├── test_any2md.sh            # 测试套件（94 用例）
    └── fixtures/                 # 测试用真实文档
```

| 脚本 | 职责 | 依赖 |
|------|------|------|
| `any2md.sh` | 参数解析、类型检测、工作目录管理、结果汇报 | bash |
| `convert_pdf.sh` | Marker 调用、LLM 增强、输出整理、双通道日志 | conda marker, marker-pdf |
| `convert_docx.sh` | pandoc 调用、图片提取、路径修正 | conda marker (pandoc) |
| `convert_marker.sh` | 通用 Marker 转换（实验格式）、双通道日志 | conda marker, marker-pdf |
