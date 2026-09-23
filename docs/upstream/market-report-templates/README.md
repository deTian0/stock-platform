# market-report-dashboard 模板归档（只读配方）

> **来源**：`../market-report-dashboard/templates/`（Skill 仓；典型本地路径 `D:\workspace\git\market-report-dashboard`）  
> **形态**：只读 HTML 配方副本；**不是**运行时数据主链  
> **权威扫描**：[market-report-dashboard-capability-report.md](../market-report-dashboard-capability-report.md)  
> **治理**：[skills-governance.md](../../ops/skills-governance.md)  
> **里程碑**：[market-report-dashboard-merge-milestones.md](../../plans/market-report-dashboard-merge-milestones.md)

## 三类模板

| 文件 | 报告类型 | 说明 |
|------|----------|------|
| `a-share-preopen.html` | A 股盘前 | 昨日指数/板块、隔夜美股、机会/风险卡 |
| `a-share-intraday.html` | A 股盘中 | 实时指数/量能/情绪、节奏建议 |
| `us-preopen.html` | 美股盘前 | 期货/日历/财报、北京时间节点 |

占位符为 `{{...}}` 自然语言字段；由助手（Skill）手工替换后产出单文件 HTML。

## 如何使用（助手侧 Skill，非 pip）

1. 软链或打开源仓 `SKILL.md`（见 skills-governance）。  
2. 自然语言触发：「生成今天的 A 股盘前报告」等。  
3. **数据**：平台产品路径仍走 `packages/providers`；本 Skill 默认靠助手 WebSearch——**禁止**把 WebSearch 写成发行依赖或第二行情主链。  
4. 预览：浏览器打开生成的 `.html`，或 Workbench「情报报告」区链接的静态副本（占位符未填时仅看布局）。

## 与 brief 的关系

- 平台 `build_premarket_brief` / 今日推荐 = **lvrev 截面 + 闸门 TopN**（结构化）。  
- 本模板 = **情报看板叙事**（机会/风险 HTML）。同属「盘前」语义，**产物与数据链不同**；联动见里程碑 MR-3（可选，未强制本轮）。

## 禁止

- `pip install` 本 Skill 进产品依赖  
- 在 agents / workbench 内平行抓取冒充 live  
- UI 宣称「已接入 market-report-dashboard 运行时」
