# ADR 0007：能力矩阵 fail-closed 与口径对齐

- 状态：Accepted
- 日期：2026-09-13

## 背景

M2.2/M2.3 要求缺能力不可静默降级，且 API 与批处理 replay 同口径。

## 决策

1. 任意 `resolve(capability)` 失败 → HTTP **409** + 矩阵细节（usable/candidates/pending）。
2. `PUT /api/settings/preferences` 只改偏好，不绕过 `usable`。
3. 路由源码禁止出现 tickflow/tushare/akshare/eastmoney.com 字面量（测试扫描）。
4. 同标的同日：workbench `/api/market/daily` 与直接 `ReplayProvider.get_daily` 字段一致。

## 后果

- 前端必须以矩阵 `usable` 门控；不可假设 minute 总有数据。
