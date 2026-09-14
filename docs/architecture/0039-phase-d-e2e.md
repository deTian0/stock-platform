# ADR 0039：Phase D E2E — recommend → ths_sim

- 状态：Accepted
- 日期：2026-09-14

## 背景

Phase D 收口需要推荐 TopN 能进入外部模拟 broker，并在工作台只读展示状态。

## 决策

1. `POST /api/research/brief/to-paper` 与 `.../to-broker` 均经 `PaperRuntime.broker`。
2. `GET /api/broker/status`：只读 broker / positions / account / lastErrors。
3. UI `#broker` 薄面板；文案标明非实盘、仅 env opt-in。
4. 默认仍 paper + replay；mock 完成 E2E；experimental HTTP 不默认。

## 后果

- Phase D 在 `v3.0.0` major 收口。
