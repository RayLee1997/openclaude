# any2md Reference — 排错手册与参数速查

## CLI 参数速查

### any2md.sh（主入口）

```bash
bash any2md.sh <输入文件> [选项]
```

| 参数 | 类型 | 说明 | 适用格式 |
|------|------|------|----------|
| `<输入文件>` | 必须 | 源文件路径 | 所有 |
| `--force_ocr` | 可选 | 强制 OCR（扫描件/图片 PDF） | PDF |
| `--page_range "0-9"` | 可选 | 指定页范围 | PDF |
| `--languages "Chinese,English"` | 可选 | 指定语言 | PDF, 实验格式 |
| `--strip_existing_ocr` | 可选 | 去除已有 OCR 层后重新识别 | PDF, 实验格式 |

## 格式支持矩阵

| 格式 | 引擎 | 路由脚本 | 精度 | 状态 |
|------|------|----------|------|------|
| `.pdf` | Marker + Gemini LLM | `convert_pdf.sh` | ⭐⭐⭐⭐⭐ | **稳定** |
| `.docx` | pandoc | `convert_docx.sh` | ⭐⭐⭐⭐ | **稳定** |
| `.epub` | Marker | `convert_marker.sh` | ⭐⭐⭐ | 🧪 实验 |
| `.pptx` | Marker | `convert_marker.sh` | ⭐⭐ | 🧪 实验 |
| `.xlsx` | Marker | `convert_marker.sh` | ⭐⭐ | 🧪 实验 |
| `.jpg` `.png` `.gif` `.bmp` `.tiff` `.webp` | Marker (OCR) | `convert_marker.sh` | ⭐⭐⭐ | 🧪 实验 |

> [!NOTE]
> 实验格式通过 Marker 的 `PdfConverter` 处理，精度取决于 Marker 对该格式的实际支持程度。
> DOCX 使用 pandoc 而非 Marker，因为 pandoc 对 Word 文档的解析精度更高。

## resources/config.json 配置说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `gemini_model_name` | string | `gemini-3-flash-preview` | Gemini LLM 模型名称 |
| `use_llm` | boolean | `true` | 是否启用 LLM 增强（10-15% 精度提升） |
| `output_format` | string | `markdown` | 输出格式：`markdown` / `json` / `html` / `chunks` |

可选模型值：`gemini-2.0-flash`、`gemini-2.5-flash`、`gemini-3-flash-preview`

> [!TIP]
> 修改 `config.json` 后无需重启，下次转换自动生效。

## 输出协议

子脚本通过 **stdout** 输出 3 行结果（供 `any2md.sh` 解析）：

```
RESULT_MD=/path/to/output.md
RESULT_IMAGES=5
RESULT_ENGINE=Marker + Gemini LLM
```

- 进度信息 → **stderr**（通过 `_log()` 或 `>&2`）
- 结果摘要 → **stdout**（`RESULT_*` 协议）
- 构建日志 → `$BUILD_DIR/build.log`（双通道写入）

## 常见错误排查

| 症状 | 原因 | 修复 |
|------|------|------|
| `❌ Missing: conda` | conda 未安装或不在 PATH | 安装 Miniconda |
| `❌ marker_single not found` | marker-pdf 未安装 | `conda run -n marker pip install marker-pdf` |
| `❌ pandoc not found` | pandoc 未安装 | `conda install -n marker -c conda-forge pandoc` |
| `❌ File not found` | 输入路径错误 | 检查文件路径是否正确 |
| `❌ Unsupported file format` | 格式不在支持列表 | 仅支持上方矩阵中的格式 |
| 首次运行极慢 | Surya OCR 模型下载 (~2GB) | 耐心等待，后续运行正常 |
| 转换超时/OOM | PDF 页数过多或复杂图表 | 使用 `--page_range` 分段处理 |
| API 限流 (429) | Gemini API 调用频繁 | 等待后重试，或换更高配额 Key |
| `⚠️ Config not found` | `resources/config.json` 缺失 | 将使用 Marker 默认配置 |
| macOS `sed -i` 报错 | GNU sed 与 BSD sed 差异 | 脚本已使用兼容写法 |

## 脚本架构

```
any2md/
├── SKILL.md                       # 技能定义
├── reference.md                   # 本文件（排错 + 速查）
├── resources/
│   └── config.json                # Marker 配置（LLM 模型、输出格式）
├── scripts/
│   ├── any2md.sh                  # 主入口：文件类型检测 → 分发
│   ├── convert_pdf.sh             # PDF → MD（Marker + Gemini LLM）
│   ├── convert_docx.sh            # DOCX → MD（pandoc 直转）
│   └── convert_marker.sh          # 实验格式 → MD（Marker 通用转换）
└── tests/
    ├── test_any2md.sh             # 测试套件（94 用例）
    └── fixtures/                  # 测试用真实文档
```
