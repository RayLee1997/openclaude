# 通用图表兜底规范 (Common Chart Template Fallback)

此模板适用于所有未单独定义模板的图表类型（如罕见类型、或无法精确解析的 unknown 图表），以确保获得最基础的 "Healing Dream" 视觉体验。

## 基础配色模板 (Base Color Palette)

> ⚠️ 所有无法识别的图表，**必须**在头部注入以下基础的 `%%{init}%%` 配置参数，确保主配色方案不会偏离。

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#A2D2FF',
    'primaryTextColor': '#2B2D42',
    'primaryBorderColor': '#A2D2FF',
    'lineColor': '#FFC8DD',
    'secondaryColor': '#FFC8DD',
    'tertiaryColor': '#CDB4DB',
    'background': '#FAFAFA',
    'fontSize': 12
  }
}}%%
[您的图表代码类型]
    [您的图表代码正文]
```

## 通用布局与可读性规则 (General Layout & Readability Rules)

1. **背景颜色约束**：画布背景必须始终保持为 `#FAFAFA`。
2. **文字对比度**：禁止在浅色背景上使用浅色文字（如黄色、浅灰）；主文本或轴线文字推荐使用深色 `#2B2D42` 或 `#4A4E69`。
3. **防截断措施**：无论何种图表结构，必须注意边缘元素的留白。
   - 如果节点或标题过长，主动增加 `<br/>` 换行或使用换行语法。
   - 如果是流程图等带有 `padding` 或 `margin` 设置的图表，必须留出足够的边距（例如 10~20 像素）。
4. **精简要素**：避免过于庞杂的堆叠。同类型的实体、连线，其视觉粗细不应失衡，遵循"重点突出、次干淡化"的排版原则。
