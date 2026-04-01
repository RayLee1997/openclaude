# 饼状图 — 糖果渐变

## 配色模板

```mermaid
%%{init: {
  'theme':'base',
  'themeVariables': {
    'pie1': '#A2D2FF', 'pie2': '#CDB4DB',
    'pie3': '#FFC8DD', 'pie4': '#BDE0FE',
    'pie5': '#FFAFCC', 'pie6': '#E2F0CB',
    'pie7': '#F8BBD0', 'pie8': '#DCEDC8',
    'pieStrokeWidth': '2px',
    'pieOuterStrokeColor': '#ffffff',
    'pieOpacity': '0.9'
  }
}}%%
pie title [标题]
    "[分段1]" : [数值]
    "[分段2]" : [数值]
    "[分段3]" : [数值]
```

## 规范

- **容量**：≤8 段，超过合并为 "Others"
- **排序**：按数值从大到小
- **标题左侧裁切修复**：如果标题左侧被挤压，则采用将图表标题字体变小的优化方案（例如在 `themeVariables` 中添加 `'pieTitleTextSize': '13px'` 或更小尺寸）。
- **跨平台**：禁止用 `carousel` 展示多张饼图（Obsidian 不支持），使用独立 mermaid 块 + `####` 标题分隔
