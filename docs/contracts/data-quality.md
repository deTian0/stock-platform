# 契约：数据质量体检（data quality）

- 里程碑：`T3`（目标发版 `v4.14.0`）
- 单点：`stock_platform_research.data_quality`
- CLI：`stock-platform-data-quality`
- ADR：[0091](../architecture/0091-data-quality-scan.md)
- 状态：生效（SIMULATE / 只读 / 零网络）

## 1. 硬约束

| 约束 | 含义 |
|------|------|
| 零网络 | 不发 HTTP、不触发抓数 |
| 只读 | `market.db` `mode=ro`；不写行情库 |
| 永不抛 | 检查项级 try/except；`collect_data_quality` total function |
| 不阻断 | 严重项 → payload `degraded`；**不**进选股门禁 / loop_health `blocked` |
| 退出码恒 0 | 裁决在 JSON |

## 2. 检查项

| id | 方法 | status |
|----|------|--------|
| `pctScale` | 复用 `detect_pct_scale`；相对资产类先验统计混用比例 | 有混用 → warn；比例 ≥25% → degraded |
| `halts` | 近窗零成交占比；连续 ≥5 日零成交 | 超阈 → warn |
| `closeJumps` | `|Δclose|≥25%` 且无 `adj_factor`/`adjust_factor` 同行 | warn；样本很多 → degraded |
| `dirtyCodes` | 非 6 位；`5xxxxx.SZ` / `1xxxxx.SH` 后缀错配 | warn |
| `coverageGaps` | 声明基准 + 观察 ETF 在窗口缺日 | 缺基准 → degraded；仅 ETF → warn |

## 3. Payload

顶层：`status` / `asof` / `windowStart` / `checks[]` / `benchmark` / `marketDb` / `disclaimer`。  
`loop_health.dataQuality` 经 `data_quality_section` 压缩为 `status` / `summary` / `degradedChecks` / `warnChecks`。

## 4. 非目标

不修库、不回补行情、不做全市场全历史扫描、不引入 live。
