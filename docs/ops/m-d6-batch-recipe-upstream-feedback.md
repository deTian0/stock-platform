# 批量端点配方回馈上游说明（M-D6）

> **状态**：done（2026-09-22）  
> **权威运行时**：`stock-platform` `packages/providers`  
> **禁止**：平行 HTTP 运行时、`pip install` Skill/兄弟仓进产品依赖。

## 目的

当平台从 `a-stock-data` / `global-stock-data` **吸收**东财 / 新浪等端点配方后，
可选把「已验证字段、节流、备胎」**文档级**回馈上游 Skill，避免双写漂移。
本文件是双写说明模板；勾选清单见 [`skill-recipe-feedback-checklist.md`](skill-recipe-feedback-checklist.md)。

## 流程（先平台，后上游文档）

```
1. 缺口对照（M-D1）→ 选端点
2. 契约 / ADR（如有）→ 扩能力矩阵
3. packages/providers 实现 + em_get + 单测（权威）
4. Workbench 路由接线（缺能力 409）
5. （可选）回馈上游 Skill 文档：字段表 / 限流 / 备胎 URL 语义
6. 在 PR 描述链到本说明 + upstream-archive
```

## 双写模板（复制到上游 PR / Issue）

```markdown
## 配方回馈（来自 stock-platform）

- 平台版本 / commit：
- 能力矩阵 id：
- 端点（主机+路径，无 token）：
- 字段变更（增/改/弃用）：
- 限流：`em_get` 间隔 / 抖动 / Session（仅东财）
- 备胎：有 / 无（说明触发条件）
- 测试：平台单测路径；上游仅文档时注明「无运行时变更」
- 红线确认：未引入平行抓取；未 pip 依赖平台
```

## 批量端点注意

| 项 | 要求 |
|----|------|
| 全市场 / 列表类 | 平台侧软上限 + fail-closed；勿在 Skill 文档鼓励无节流扫全市场 |
| 东财 | 一律 `em_get`；上游文档同步「勿裸 requests」 |
| 美港 | 不得套用 A 股 T+1 / 涨跌停叙述 |
| 密钥 | 永不写入配方正文或计划 |

## 交叉链

- [`upstream-archive.md`](../upstream-archive.md)
- [`skills-governance.md`](skills-governance.md)
- [`skill-recipe-feedback-checklist.md`](skill-recipe-feedback-checklist.md)
- 能力域路线图 M-D6
