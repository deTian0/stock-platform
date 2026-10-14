# 0075 — 循环健康度出口与趋势台账（loop-health export & history）

- Status: Accepted
- Date: 2026-10-14
- Supersedes: —
- Related: ADR 0073（循环健康度单点）、ADR 0070（日用循环自足 / 供数守卫）、
  ADR 0058（market.db 只读真相源）、ADR 0050（只读挂载）、ADR 0049（brief 权威）

## 背景

`R3`（`v4.7.0` / ADR 0073）把日用循环六路信号聚成一个裁决（`ok` / `degraded` / `blocked`），
但裁决**只有本地文件出口**，且**只有当下快照**。两个后果都是真实踩过的：

```
① 出口面空白 —— 裁决落在 data/health/*，Workbench 无任何入口；
   人要看必须离开界面去翻文件。
② 时间面空白 —— 没有历史台账 ⇒ 「连续 3 天 degraded」与「偶发一次 degraded」
   在 payload 里长得一模一样，分不清要不要动手。
```

②尤其致命：`2026-10-13` / `10-14` 连续两日无 bar、brief 停在 `10-12` 时，
**排查靠的是人工翻 Windows 任务计划程序**，才发现 18:30 回补任务压根没注册 ——
平台内没有任何地方能把「这次不正常」和「一直不正常」区分开。

同时暴露一处**裁决语义漏洞**：`coverage` 段从 provider 透传的状态里，
`error`（库存在但不可读）与 `unconfigured`（未配置路径）在 ADR 0073 的规则中
**既非 fail 也非 warn** ⇒ 落到 `else` 分支被判 `ok`。也就是「仓库打不开」会被报告成
「供数正常」—— 与 fail-closed 的初衷相反。

## 决定

### 1. 新增只读出口 `GET /api/ops/loop-health`（Workbench）

`apps/workbench/src/stock_platform_workbench/routes/ops.py`：

| 项 | 决定 |
|---|---|
| 职责 | **只读转发** `research.loop_health.collect_loop_health`；自身零业务逻辑、零写库 |
| 200 | 完整 payload（六路信号 + `verdict` + `history`），降级也返回 200 |
| 503 | 供数段落在 `COVERAGE_HARD_FAIL`（`unavailable` / `empty` / `missing_table` / `error` / `unconfigured`）→ `detail.reason="loop_health_no_market_db"` |
| 理由 | 没有供数就没有可判的循环（fail-closed，不用假数据兜底）；但**能跑只是要打折看**的状态不许用 5xx 掩盖，裁决留在 `verdict.status` 里 |
| 契约 | 响应模型 `LoopHealthResponse` 写入 OpenAPI 目录测（`ENDPOINT_HITS` 计数 66 → 67） |

### 2. `loop_health` 新增趋势面（唯一写动作）

`packages/research/src/stock_platform_research/loop_health.py`：

| 函数 | 职责 |
|---|---|
| `read_history(path)` | 读 `history.jsonl`；文件不存在 → `[]`；**读失败向上抛**（调用方 fail-closed）；坏行跳过 |
| `summarize_history(records, asof=…, status=…)` | **纯函数**：按 `asof` 去重 → 并入本次 → 算 `degradedStreak` / `blockedStreak` / `notOkStreak` / `streakSince` / `recent` |
| `append_history(payload, path)` | **追加**一行 `{ts, asof, status, failed, warned}`；**fail-open**（写失败返回 `appended=False` + `reason`，绝不拖垮体检）；超 `HISTORY_MAX_RECORDS`（400）裁剪最旧 |
| `default_loop_health_dir()` / `default_loop_health_history_path()` | `STOCK_PLATFORM_LOOP_HEALTH_DIR` 优先，否则 `./data/health`；文件名固定 `history.jsonl` |

台账是**本模块唯一的写动作**，且只写**平台自有 `data/`**：
`market.db`（ADR 0058 / 0050）与平台库仍严格只读。明细格式与连续段口径见
[`docs/contracts/loop-health.md`](../contracts/loop-health.md) §8。

### 3. `history` **不参与裁决**

裁决仍只看六路信号的**当下快照**；`history` 只回答「持续还是偶发」。
理由：把趋势并入裁决会让「历史遗留的连续降级」污染当天判断，
也会让裁决依赖一个可被外部删改的本地文件。加这一段**不改**任何既有段语义
（`roll_up_verdict` 的输入仍是那六段）。

### 4. Workbench `#health` 面板

主模板加 `#health` 区块（导航「体检」）：裁决徽标（中文 + fail/warn 列表）+ 六段 `kv` 表 +
趋势（近 N 天逐行）+ 原始 JSON 折叠。**手写 HTML/JS，不引前端框架**（对齐 B6 口径）；
失败时中文提示，不静默。

### 5. 修正 `coverage` 硬失败档（同轮）

新增两个常量并用于裁决：

| 常量 | 取值 | 语义 |
|---|---|---|
| `COVERAGE_HARD_FAIL` | `unavailable` / `empty` / `missing_table` / **`error`** / **`unconfigured`** | 无供数 ⇒ 物理上选不出票 ⇒ `blocked` |
| `COVERAGE_WARN` | `stale` / `thin` | 可跑但要打折看 ⇒ `degraded` |

## 后果

- **正面**：裁决从「一个 JSON 文件」变成「界面上一眼可见 + 有时间面」；
  `degradedStreak` 让「一直不正常」自证，不再依赖人工翻任务计划程序；
  `error` / `unconfigured` 不再被误报为「供数正常」。
- **代价**：`research` 包引入**唯一一处文件写**（本地台账）。已用 ADR（本文）+ 契约
  （§2「台账例外」+ §8）双重显式化，并有测试锁定 fail-open、裁剪、坏行容忍与「读失败 → unavailable」。
- **风险**：台账路径依赖运行时 `cwd` / 环境变量；已给 `STOCK_PLATFORM_LOOP_HEALTH_DIR`
  作为唯一覆盖点，并在 payload 里回显 `history.path` 便于自证。
- **测试**：`packages/research/tests/test_loop_health.py` §9（台账/连续段/裁剪/坏行/隔离/渲染/CLI）
  + `apps/workbench/tests/test_ops_loop_health.py`（503 fail-closed / 200 降级 / 趋势）。

## 不做的事

- **不抓数、不回补**：只如实报告供数滞后；成因治理归 `Invoke-MarketDbBackfill.ps1`（T2 再谈执行台账）。
- **不写 `market.db` / 平台库**：除本地台账外无任何写动作。
- **不做告警推送**：通知属 T 域后续里程碑（T2/T3）。
- **不引前端框架**：面板沿用既有手写 HTML/JS + 服务端渲染口径。
- **不替代** ADR 0070 的 ops asof 回落守卫：那是在**写 brief 之前**防伤害，本体检是**事后**认伤害。
