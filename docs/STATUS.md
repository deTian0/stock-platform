# 现行快照

> 日期：2026-11-04  
> 版本：`v4.13.7`（`main` = `origin/main`，tag `v4.13.7`）  
> 工作区：干净。`CHANGELOG` 的 `[Unreleased]` 只记录本次文档整理，没有半截功能。  
> 这是**现在**读仓库的入口。历史里程碑叙事留在 [`ROADMAP.md`](ROADMAP.md) 与 [`plans/trading-system-roadmap.md`](plans/trading-system-roadmap.md) 的修订记录里，不要从那些旧焦点段开工。

## 文档放哪

正式正文只在 `docs/`。按用途分目录，不把 ADR、契约、运维和计划摊成一堆。

| 位置 | 放什么 | 不放什么 |
|------|--------|----------|
| [`docs/`](README.md) | 产品文档 SSOT | 密钥、行情缓存、SQLite |
| 仓库根 `README.md` / `AGENTS.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | 给人、给代理、给发版脚本的入口 | 里程碑正文 |
| `packages/*/README.md`、`apps/workbench/README.md` | 该包怎么装、硬约束 | 全仓路线图 |
| [`archive/`](archive/README.md) | 已经落地的交接，文中「下一块砖」作废 | 现行计划 |

`.cursor/plans` 若出现，只留指向本目录的短链，不写第二份正文。

## 自有线

| 域 | 状态 |
|----|------|
| G / B / S / X / C | 收官 |
| R | R1–R4 done。**R5** ETF 进宇宙未做：`market.db` 的 ETF 日线要生产侧回补，平台只读 |
| T | T1、T2 done。**T3** 数据质量体检未开工，目标 tag **`v4.14.0`** |
| Y | Y1 采纳闸门、Y3 负收益归因 done。**Y2** 落档必须等人工签核；没有 `adopt` 证据不改生产默认档 |
| L | L1 立项 `Accepted`（华宝、1 万、Phase 0 纯模拟）。L2/L3 与实盘红线仍关闭 |

下一刀按路线图是 **T3**：零网络只读扫 `market.db`（单位口径、停牌与零成交、除权跳变、脏码、指数/ETF 覆盖缺口），结果并进 `loop_health`。严重项只降级，不阻断选股。代码里还没有 `research.data_quality`。

## v4.13 已落地

- **v4.13.0** 简报盘前/盘后分线、②A/②B 双 profile 二次精选、③B 详解
- **v4.13.1–.3** 报告日文件名、同花顺导入块与 txt 对齐
- **v4.13.4–.6** 盘后开/收/涨跌：东财分批重试 → 腾讯/新浪 → westock 第四源
- **v4.13.7** 体检 `briefDue`：修掉每晚「brief 落后 1 日」的假阳性；裁决 `ok` 时报告只留一行结论

## 已记账、另立版本的缺陷

- `exchange_prefix("588080")` 把 `5` 开头的沪市基金判成 `sz`，四源都取不到
- 基准码 `000905` 被前缀规则推成 `sz000905`（厦门港务），不是中证 500 `sh000905`
- 单包跑 `pytest packages/research` 时，个别用例可能写到仓库 `data/`；全量 `pytest packages apps` 才有会话隔离

执行层仍是 SIMULATE，`liveTradingEnabled=false`。
