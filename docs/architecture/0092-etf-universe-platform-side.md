# 0092 — ETF 进宇宙（平台侧 R5-P）

- **状态**：Accepted
- **日期**：2026-11-05
- **相关**：[`0055`](0055-market-universe.md) · [`0058`](0058-market-db-source-of-truth.md) · [`0090`](0090-benchmark-identity-and-sh-fund-prefix.md) · [`0091`](0091-data-quality-scan.md)  
  契约 [`../contracts/market-universe.md`](../contracts/market-universe.md)

---

## 背景

全量 R5 需要生产侧把 ETF 日线写入 `market.db`。平台只读；在回补达标前，日用默认宇宙仍是股票。R5-P 只补**形状与缺口诚实度**，避免空 ETF 池伪装成选股成功。

## 决策

1. **不写** `market.db`；**不**翻转 `daily` 默认 `asset-type` / `universe-source`。
2. `asset_type=etf` 且滤空 → `UniverseEmptyError`，中文明确「未回补 / 禁止当股票池」。
3. `asset_type=all` 但 `counts.etf==0` → `notes` 警告，股票结果仍可用。
4. T3 `coverageGaps`：观察 ETF **大半整码缺失** → `degraded`（loop_health 仅 warn，不 blocked）。
5. ③A：截面外 ETF 持仓标注 `assetClass=etf`，文案区分无股票式 T+1 冻结句（③B 本已跳过 T+1）。

## 非目标

打开默认含 ETF 的日用宇宙；全市场 ETF 费用/基准验收（留给全量 R5）。
