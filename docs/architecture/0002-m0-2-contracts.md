# ADR 0002：M0.2 数据集与市场口径冻结

- 状态：Accepted
- 日期：2026-09-13

## 背景

M0.1 契约多为 TBD。合并期若单位/列名漂移，后续 Provider 与工作台会对不齐。

## 决策

1. `amount` = **元**；`volume` = **手**；realtime 比例字段入口 = **小数制**。
2. 日 K 交易日列名对齐 TSP：`date`；除权因子列名：`ex_factor` + `trade_date`。
3. `asset_type` 区分 stock/etf/index；涨跌停用 `raw_*`。
4. `asof_ts` = Unix 毫秒 UTC；分钟 `datetime` = 北京墙钟 naive。
5. 能力矩阵七项与 TSP `CAPABILITY_REGISTRY` 同 id；`usable`/`candidates`/`pending` 形状写入契约。
6. CN 市场策略表冻结 T+1、涨跌停、时区；美港仅占位禁止套用。

## 后果

- 实现方（M1）按契约写测，不再争论单位。
- 与上游个别脚本若不一致，以本仓契约为准并在适配层转换。
