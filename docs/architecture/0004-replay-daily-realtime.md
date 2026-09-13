# ADR 0004：daily/realtime 录制回放适配器

- 状态：Accepted
- 日期：2026-09-13

## 背景

M1 需要在无 live 网络下验证契约字段，并为后续 HTTP 适配器提供同一归一化路径。

## 决策

1. `ReplayTransport` + `ReplayProvider` 只读 fixtures，零网络。
2. 所有 daily/realtime 行经 `normalize_daily_row` / `normalize_realtime_row` 进入契约列。
3. 源字段若为百分数，须显式 `pct_unit=percent`，禁止启发式。
4. Live HTTP 延后到 M1.3，且必须经东财限流单点。

## 后果

- CI 可稳定测口径；换源时只换 transport，不换契约测试。
