# 柱状图 — 高对比度深色系

## 配色模板

> ⚠️ 柱状图 **必须** 使用深色作为首选 `plotColorPalette`。淡色在白底上消失！

```mermaid
%%{init: {
  'theme':'base',
  'themeVariables': {
    'xyChart': {
      'plotColorPalette': '#4A4E69, #9D8EC7, #64748B',
      'backgroundColor': '#FAFAFA',
      'titleColor': '#2B2D42'
    }
  }
}}%%
xychart-beta
    title "[图表标题]"
    x-axis ["Label1", "Label2", "Label3", "Label4"]
    y-axis "[单位]" [最小值] --> [最大值]
    bar [val1, val2, val3, val4]
```

## 多系列规则

### 规则 1：多系列遮挡防护

Mermaid `xychart-beta` **不支持分组柱状图**（grouped bar），多个 `bar` 系列会堆叠遮挡。

| 场景 | 解决方案 | 示例 |
| ---- | -------- | ---- |
| 2 个对比指标（量级相近） | 一个用 `bar`，一个用 `line` | IaaS (Bar) vs SaaS (Line) |
| 2 条趋势线 | 均用 `line`，通过颜色区分 | Total Revenue vs Cloud Revenue |
| 单一指标逐期变化 | 仅用 `bar` | RPO 季度增长 |

```mermaid
xychart-beta
    title "Metric A (Bar) vs Metric B (Line)"
    x-axis ["Q1", "Q2", "Q3", "Q4"]
    y-axis "Unit" min --> max
    bar [a1, a2, a3, a4]
    line [b1, b2, b3, b4]
```

> ⚠️ **严禁** 在同一图表中使用 2 个以上的 `bar` 系列

### 规则 2：标题内嵌图例标注

`xychart-beta` 无原生图例（legend）支持。**多系列图表必须在标题中标注每个系列的图形类型或颜色**。

| 图表类型 | 标题格式 | 示例 |
| -------- | -------- | ---- |
| Bar + Line 混合 | `"指标A (Bar) vs 指标B (Line)"` | `"IaaS (Bar) vs SaaS (Line) Revenue"` |
| 多条折线 | `"指标A (Color) vs 指标B (Color)"` | `"Total Revenue (Blue) vs Cloud Revenue (Pink)"` |
| 单系列 | 无需标注 | `"RPO Explosive Growth"` |

> 颜色名称取自 `plotColorPalette` 顺序：`#A2D2FF` = Blue, `#CDB4DB` = Purple, `#FFC8DD` = Pink
