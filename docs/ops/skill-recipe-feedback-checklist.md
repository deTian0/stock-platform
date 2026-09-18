# Skills / 配方回馈检查清单（M-S2）

> **状态**：done（2026-09-18）  
> PR 合并前可选勾选；**禁止**把 Skill 仓 `pip install` 进产品依赖。

## 勾选

- [ ] 本次改动是否触及东财 / 新浪 / 腾讯 / Yahoo 配方字段或限流？  
- [ ] 若是：平台 `packages/providers` 是否已先改（权威）？  
- [ ] 是否需要回馈 `a-stock-data` / `global-stock-data` Skill **文档**（可选双写）？  
- [ ] `pyproject` / lock **未**新增 Skill / engine / TradingAgents dataflows 运行时依赖？  
- [ ] 新东财调用是否走 `em_get`（非裸 `requests.get`）？  
- [ ] US/HK 是否误套用 A 股 T+1 / 涨跌停？  
- [ ] 缺能力路径是否 fail-closed（409/显式错误）？

## 交叉链

- [`skills-governance.md`](skills-governance.md)  
- [`upstream-archive.md`](../upstream-archive.md)
