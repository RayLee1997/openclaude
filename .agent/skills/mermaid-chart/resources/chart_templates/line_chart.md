# 折线图 — 柔和趋势

## 配色模板

```mermaid
%%{init: {
  'theme':'base',
  'themeVariables': {
    'xyChart': {
      'plotColorPalette': '#A2D2FF, #CDB4DB, #FFC8DD',
      'backgroundColor': '#FAFAFA',
      'titleColor': '#2B2D42'
    }
  }
}}%%
xychart-beta
    title "[图表标题]"
    x-axis ["Label1", "Label2", "Label3", "Label4"]
    y-axis "[单位]" [最小值] --> [最大值]
    line [val1, val2, val3, val4]
```

## 规范

- **X 轴格式**：`"YYYYQN:Value+Unit"`（如 `"2024Q2:80.2B"`）
- **Y 轴范围**：留 15% 余量，不强制从 0 开始
- **容量**：≤3 条线
