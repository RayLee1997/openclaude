# 流程图 / 概念图 — 治愈系流转

## 配色模板

```mermaid
%%{init: {
  'theme':'base',
  'themeVariables': {
    'primaryColor': '#A2D2FF',
    'primaryTextColor': '#2B2D42',
    'primaryBorderColor': '#A2D2FF',
    'lineColor': '#9D8EC7',
    'secondaryColor': '#FFC8DD',
    'tertiaryColor': '#CDB4DB',
    'clusterBkg': '#F8FAFC',
    'clusterBorder': '#CBD5E1',
    'fontSize': 11,
    'background': '#FAFAFA'
  },
  'flowchart': {
    'padding': 15,
    'nodeSpacing': 40,
    'rankSpacing': 40,
    'fontSize': 12,
    'subGraphTitleMargin': { 'top': 20, 'bottom': 20 },
    'htmlLabels': true,
    'useMaxWidth': true
  }
}}%%
graph TD
    A["[起始节点]"] --> B{"[决策节点]"}
    B --> C["[流程A]"]
    B --> D["[流程B]"]
    C --> E["[结果节点]"]
    D --> E

    classDef start fill:#A2D2FF,stroke:#89C2F8,stroke-width:1px,color:#4A4E69,rx:10,ry:10
    classDef process fill:#CDB4DB,stroke:#B59BC5,stroke-width:1px,color:#4A4E69,rx:10,ry:10
    classDef result fill:#FFC8DD,stroke:#FFB7C5,stroke-width:1px,color:#4A4E69,rx:10,ry:10
    classDef decision fill:#E2F0CB,stroke:#D4E5B5,stroke-width:1px,color:#4A4E69,rx:10,ry:10
    classDef accent fill:#FFAFCC,stroke:#FF9FBF,stroke-width:1px,color:#4A4E69,rx:10,ry:10

    class A start
    class E result
    class B decision
```

## 规范

- **节点数** ≤12，**文本换行** 每 15-20 字符 `<br/>`
- **连线色** `#CDB4DB`
- **子图**：必须设置 `clusterBkg: '#F8FAFC'` + `clusterBorder: '#CBD5E1'`，否则子图背景继承节点色
- **子图标题被遮挡**：设置 `padding: 30` + `rankSpacing: 40` + `subGraphTitleMargin: { top: 10, bottom: 10 }`

## 复杂矩阵布局 (Matrix Layout)

全局横向排列 + 局部纵向堆叠 + 隐形支撑线 `~~~`：

```mermaid
%%{init: { ... 同上配色，padding: 30 ... }}%%
flowchart LR
    subgraph A["模块 A (并排左)"]
        direction TB
        A1["极长节点1"] ~~~ A2["极长节点2"]
    end
    subgraph B["模块 B (并排右)"]
        direction TB
        B1["极长节点3"] ~~~ B2["极长节点4"]
    end
    A ~~~ B %% 强制子图之间保持横向距离
```
