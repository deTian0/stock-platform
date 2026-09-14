# ADR 0031：live 偏好模板与东财熔断

- 状态：Accepted
- 日期：2026-09-14

## 背景

M8/M9 已允许 preferences 切到 `astock_http` / `global_http`，但缺少成套模板，
运维容易漏改 `full_minute` 等能力。批量 live 时仅有 `EM_MIN_INTERVAL` 串行节流，
连续 429 仍会打满间隔。

## 决策

1. **预设**（`PREFERENCE_PRESETS`，均非进程启动默认）：
   - `replay`：全部 replay（`is_default=true`）
   - `cn_astock_http`：CN 能力 → `astock_http`（仍经 `em_get`）
   - `us_hk_global_http`：仅 `daily`/`realtime` → `global_http`；CN 专有能力保持 replay
2. workbench：`GET /api/settings/presets` + `POST /api/settings/presets/{id}/apply`
   只改当前进程 preferences；**下次启动仍 replay**；不设 `liveTradingEnabled`。
3. **熔断**：`EastmoneyClient` 连续失败 ≥ `EM_CIRCUIT_FAILURES`（默认 5）后开启
   `EM_CIRCUIT_COOLDOWN`（默认 60s）冷却，抛 `CircuitOpenError`；`snapshot()` 供 ops。
4. 节流文档同步 `docs/contracts/eastmoney-http.md`。批量建议 `EM_MIN_INTERVAL=1.5~2`。

## 后果

- 预设是运维快捷方式，不是第二条数据主链。
- 熔断 fail-closed：冷却期内不再打东财；不自动换源。
