# ADR 0087：brief 到期基准与「只在异常时展开」的体检报告

- 状态：已采纳
- 日期：2026-11-04
- 里程碑：`v4.13.7`
- 关联：[0073 日用循环健康度单点](0073-daily-loop-health-single-point.md) ·
  [0075 出口与趋势台账](0075-loop-health-export-and-history.md) ·
  [0076 执行台账与 brief 连续性](0076-ops-run-ledger-and-brief-continuity.md) ·
  [0079 盘前结算](0079-settle-after-on-premarket.md) · 契约 [`loop-health`](../contracts/loop-health.md)

## 1. 背景

`loop_health` 从 2026-10-14 起每晚 18:31 跑一次，到 11-03 累计 **14 条记录、0 次 `ok`、
0 次 `blocked`、14 次 `degraded`**，`warn` 长期只剩两项：`latestBrief` 与 `briefContinuity`。
同一份报告里其余六段（供数 / 命中 / 绩效 / 名称 / 台账）全是 ✅ —— 结论与真实状态矛盾。

根因是**时点错位**，不是故障：

| 时刻 | 发生了什么 | 库里的「最新交易日」 |
|---|---|---|
| `T 日 08:30` | 盘前流水线 `-PrevSession` 写 brief，`asof = T-1` | `T-1` |
| `T 日 15:30` | 盘后复盘再写一次，`asof` 仍为 `T-1`（同日覆盖） | `T-1` |
| `T 日 18:30` | 行情回补入库 | **`T`** |
| `T 日 18:31` | 体检拿 `brief(T-1)` 去比 `coverage(T)` | `T` |

于是每晚固定：`latestBrief` 落后 1 个交易日；`briefContinuity` 窗口末端取 `T`，
而 `T` 日 brief 按设计要等 **`T+1 08:30`** 才生成 → 恒缺 1 日。

**两份 warn 都是结构性假阳性**：只要体检排在回补之后，每晚必现，且永远不会因为任何真实故障而改变。
报告因此退化为常量告警 —— 连续 `degraded` 天数、趋势表全部失去诊断力。

## 2. 决策

### 2.1 引入「brief 到期基准」`briefDue`

`brief(asof=D)` 由**D 之后第一个交易日的 08:30 盘前流水线**写出，故其到期时刻
`due(D) = next_trading_day(D) 08:30`。体检取 `<= supply_day` 中**最大的、且 `due(D) <= now`**
的交易日，作为「此刻应该已经存在的最新 brief」：

```
_brief_due_asof(supply_day, *, now=None, cutoff="08:30") -> str | None
```

该基准**同时替代两处**，保证口径只有一处：

| 位置 | v4.13.5 及以前 | v4.13.7 |
|---|---|---|
| `latestBrief` 落后判定 | 比 `coverage.latestTradeDate` | 比 `briefDue.asof` |
| `briefContinuity` 窗口末端 `endDay` | `coverage.latestTradeDate` | `briefDue.asof` |

各场景的新旧结论：

| 场景 | 旧口径 | 新口径 | 谁对 |
|---|---|---|---|
| `T 18:31` 回补后体检 | 落后 1 日 + 缺 T 日 → warn | 基准 `T-1`，与 brief 一致 → ok | 新 |
| `T+1 09:00` 盘前已跑 | 落后 0 日 → ok | 基准 `T`，brief `T` → ok | 一致 |
| `T+1 09:00` 盘前**没跑** | 落后 1 日 → warn | 基准 `T`，brief 停 `T-1` → **warn** | 一致（真信号保留） |
| 中间某日 brief 断档 | 缺日 → warn | 缺日 → warn | 一致 |
| 交易日历不可用 | 退化为供数日 | `briefDue` 标 `unavailable` + 回落供数日 | 新（如实降级） |

### 2.2 报告只在异常时展开

CLI 新增 `--on-ok {summary,full,skip}`，默认 **`summary`**：

| 裁决 | 行为 |
|---|---|
| `ok` + `summary` | `loop_health.md` 只写 5 行结论；删除上一次的 `loop_health.html`；`loop_health.json` 照写 |
| `ok` + `full` | 旧行为（完整 md + html） |
| `ok` + `skip` | 不写报告，并清掉旧的 md/html（避免把上次结论当成本次） |
| 非 `ok` | **`--on-ok` 不生效**，一律完整 md + html |

`loop_health.json` 与 `history.jsonl` 在**任何**策略下都照写 —— 前者供接口 / 面板 / 审计，
后者是趋势面的连续证据。清掉旧 html 的理由是它只可能来自一次更旧的裁决，留着就是矛盾信息。

## 3. 硬约束

1. **只改比较基准**，不改 `coverage` / `hits` / `performance` / `symbolMaster` / `opsLedger`
   的任何口径，也不新增 fail 档 —— 本 ADR 不扩大阻断面。
2. **零网络 / 只读 / fail-closed 不变**：`briefDue` 算不出就如实 `unavailable`，绝不猜日期；
   `roll_up_verdict` 在缺 `briefDue` 时**回落旧口径**（基准 = 供数最新交易日），
   使历史 payload 与外部调用方行为不变。
3. **趋势台账不受呈现策略影响**：`history.jsonl` 每次追加一行，趋势才有连续性。
4. **时区**：`08:30` 按**本机本地时间**比较（部署在 CST）。跨时区部署须显式注入 `now`
   或改 `brief_due_cutoff`；`now` 带时区时先转本地再比较。
5. **回退上限 15 个交易日**：超出即返回 `None`，避免日历异常导致死循环。

## 4. 为什么不选其它方案

| 方案 | 否决理由 |
|---|---|
| 把体检挪到 `08:35`（盘前之后、回补之前） | 盘前时 coverage 只有 `T-1`，等于放弃 18:30 回补的观测价值；且与 08:30 那条链的时点语义纠缠 |
| 直接把这两项检查删掉 | 真断档（盘前任务没跑、中间缺日）就彻底没人看得见 —— 本 ADR 修的是**基准**，不是删检查 |
| 把 lag 容差全局放宽为 1 | 会同时掩盖真实的补跑延迟，且 `briefContinuity` 的窗口末端仍然错 |
| 停掉报告只留 Workbench 面板 | 面板只在打开时可见，异常不留痕；且定时任务没有可回看的产物 |

## 5. 验证

- 真机 2026-11-04 09:06（`--no-write`）：`warn` 从
  `['latestBrief', 'briefContinuity']` 降为 `['coverage']`；两项 `latestBrief` /
  `briefContinuity` 均转为 ✅，且 `brief 到期基准` 行显示
  `已到期最新 asof 2026-11-03 · 供数最新 2026-11-03 · 08:30 盘前到期`。
- 单测：`packages/research/tests/test_loop_health.py` **58 passed**（新增 12 例），其中
  `test_night_run_does_not_flag_brief_as_missing` 直接锁死「T 日 18:31 不再假阳性」，
  `test_roll_up_lag_when_brief_behind_due_base` 锁死「盘前任务没跑仍要 warn」。

## 6. 遗留

- **`coverage: stale` 在盘前是预期效应**：`expectedTradingDay` 由当天推导，所以 08:30
  手动跑必然 `lag=1`；只要 `latestTradeDate == asof` 就不是数据链断裂。18:31 自动跑不会出现。
  本 ADR 不处理（属 provider 的 `coverage_snapshot` 口径，改动面更大）。
- `data/health/history.jsonl` 里 10-14 ~ 11-03 的 `degraded` 记录由旧口径产生，**不回填**；
  下一次 `ok` 写入后 `degradedStreak` 会自然归零。
- 报告仍无推送出口：异常只有落到磁盘才会被看见。推送属 T 域后续里程碑。
