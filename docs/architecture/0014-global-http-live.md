# ADR 0014：美港 live HTTP（Yahoo + 新浪）

- 状态：Accepted
- 日期：2026-09-14

## 背景

M8 已接线 A 股 `astock_http`（经 `em_get`）。美港仍只有 `global_replay`；`global_http` 在能力矩阵中为 pending。

## 决策

1. 新增 `GlobalHttpProvider`（`name=global_http`），构造需 `market=US|HK`。
2. **日 K**：Yahoo chart `v8`（零 crumb）；港股 Yahoo 符号形如 `00700.HK`。
3. **实时**：新浪 `hq.sinajs.cn` — 美股 `gb_{ticker}`、港股 `rt_hk{code}`。
4. **不走** `em_get` / 东财限流单点（避免与 A 股共享节流槽；东财 push2his 也不返回美港 K 线）。
5. HTTP 经可注入 `get_json` / `get_text`；CI 不访问公网。
6. 能力矩阵 `global_http` 标 usable；workbench 默认偏好仍为 CN `replay`（美港可选切 live）。
7. 吸收边界：仅 daily + realtime；不搬期权 / SEC / FINRA 等 Skill 其余层。

## 后果

- Yahoo / 新浪条款为个人研究向；产品默认仍 replay。
- 工作台用 `GlobalHttpRouter`（同名 `global_http`）按标的推断 US/HK 后分发到对应 Provider 实例。
