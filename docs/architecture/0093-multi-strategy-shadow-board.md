# 0093 — 多策略 Final Board 影子链（MVP）

- **状态**：Accepted
- **日期**：2026-11-05
- **相关**：计划 [`../plans/multi-strategy-final-board.md`](../plans/multi-strategy-final-board.md) · ADR [`0065`](0065-llm-debate-lane.md) · [`0077`](0077-strategy-adoption-gate.md) · [`0083`](0083-digest-pre-post-and-secondary-pick.md)  
  契约 [`../contracts/multi-strategy-shadow.md`](../contracts/multi-strategy-shadow.md)

---

## 背景

出厂 lvrev（`score_lvrev` + `W_DEFAULT` + 入口闸门 → brief / picks / 命中 / 主绩效）是日用主链。多策略「五校 → Round2 → Final Board」是**并行观察链**，不得静默覆盖出厂产物。升级唯一门：影子证据 → **Y1** 采纳闸门 → 人工签核 → **Y2** 落档。

## 决策

1. **Pipeline**：Round1 五校并行出候选 → Round2 **硬**闸（fail-closed，禁止 pad-to-N）→ Final Board（结构化理由）→ **仅**写影子账本。
2. **五校**：S1 宏观/择时 · S2 事件/主题 · S3 质量/防守（lvrev 谱系）· S4 短线动量 · S5 资金流/流动性。S3/S4 复用二次精选；S1/S5 为薄规则（缺数据 fail-closed 空池 + `reason`）；S2 经 DI 挂 `concept_blocks` / `sector_fund_flow` / `lhb` / `unlock`，未注入则空池。
3. **双轨仲裁**：
   - **集 A（硬）**：合规 / 流动性 / 涨停 / 集中度 / 学校优先级——唯一可收紧过闸的裁决者。
   - **集 B（顾问）**：贝叶斯 + LLM 估计胜率/期望——**advisory only**；不可放行未过硬闸的票；恒 `excludedFromPerformance`。现行可为 `null` / 占位（含学校优先级 `rankHints`）。
4. **影子落盘**：默认 `local/shadow/`（可用 `STOCK_PLATFORM_SHADOW_DIR` / Settings 覆盖）。**禁止**写生产 picks / hits / `recommend_decisions.jsonl` / 主绩效 JSONL。
5. **空板合法**：硬闸后 Final 可为空；不是缺陷。
6. **LLM**：理由须结构化（持有期 / 触发 / 可证伪预期 / 失效条件）；缺字段 degrade；**不能**覆盖硬闸；不进绩效。规则-only 路径由规则填结构化字段。
7. **digest**：允许在绩效台账后追加**只读**影子附录（文件存在才渲染；缺则整段省略）。**禁止**借此改 picks / 同花顺导入语义。

## 非目标

改出厂 `W_DEFAULT` / `min_pick_score`；写生产账本；开 live；默认开 LLM；Workbench UI；主题校绕过 `FACTOR_LIBRARY`。

## 增补（2026-11-06，已签核，随 `v4.14.0`）

以下均在本 ADR 决策范围内，不改出厂 lvrev，不另起 ADR。

1. **生产调度 opt-in**：库与 CLI 出厂默认仍**关**（`run_daily_pipeline(shadow_board=False)`）。开启方式：`--shadow-board` / `STOCK_PLATFORM_SHADOW_BOARD=1`；生产盘前 / 盘后调度预设（`scripts/ops/stock-platform-daily.xml`、`stock-platform-postmarket.xml`、`Invoke-ScheduledRun.ps1` 的 `TASK_PRESETS`）加 `-ShadowBoard`，2026-11-05 起生效，由 `test_scheduler_args_contract.py` 钉住。**回滚**：移除预设里的 `-ShadowBoard`，或单次传 `-NoShadowBoard`（显式关优先）；无需改代码。影子链异常只落 `{ok:false,error}`，不阻断主链。
2. **前向影子账本隔离**：`<shadow_dir>/shadow_decisions.jsonl`（字段见 [`../contracts/datasets.md`](../contracts/datasets.md)「影子链产物」）。与 `recommend_decisions.jsonl` 物理隔离（`FORBIDDEN_BASENAMES` 守卫）；结算复用 `settle_pending_entries`，集 A / 集 B 分开报告，**不**并入主绩效。起算日 `asof=2026-11-04`。
3. **Round2 仲裁实验开关**：`apply_round2_set_a(arbitration="d"|"a"|"b")` 与 CLI `--backtest --arbitration`；出厂默认 **`d`**（学校优先级先于分数），逐位不变，硬闸三模式一致。2021-01~2026-11 离线对照 A / B 夏普均劣于 D（见计划 §11.5），**维持 D**，开关仅供回测，不起新 ADR。
4. **S2-P1 每日快照**：影子链运行时经 `em_get` 拉当日全市场龙虎榜 / 概念与行业板块排名 / 30 日解禁日程（`astock_http` 三个按日方法，登记见 [`../contracts/capability-matrix.md`](../contracts/capability-matrix.md)「全市场按日截面方法」），落 `<shadow_dir>/s2_snapshots/s2_snapshot_{asof}.json`。
   - 开关 `STOCK_PLATFORM_S2_SNAPSHOT`（1/0）；未设时默认开，但 replay 预设 / pytest 下不发网。
   - 预算 `STOCK_PLATFORM_S2_EM_BUDGET`，默认 **300** 逻辑请求/自然日（Asia/Shanghai），记在 `s2_snapshots/_budget.json`；实测 4 次/日，同 asof `ok` 快照复用零网络。
   - **fail-soft**：单源失败 / 超预算只记 `sources.*.status` 与 note，永不抛出、不阻断；`loop_health.shadowBoard.s2` 最多 warn。
   - PIT：龙虎榜按交易日可回放；板块排名仅 `updatedAt` 日期 == asof 才用；解禁日程有修订前视，仅作软排除。回测不读快照，S2 在回测恒空池。

## 增补 2（2026-11-06，用户签核：S4 / S5 下线）

- **状态**：Accepted（用户 2026-11-06 签核）
- **依据**：[`../plans/shadow-s4-s5-diagnosis.md`](../plans/shadow-s4-s5-diagnosis.md)。S4 现有短动量口径方向反了（A 股短期反转；综合分 IC −0.097，五分位单调递减，入池追高）。S5 有实现缺陷（`min(amount/1e9, 0.8)` 封顶后按代码升序取前 8，入池 100% 为 `000` 开头），且历史库无资金流字段，按真实成交额排序同样为负。

决策：

1. **S4 现有短动量口径下线、S5 下线**。日循环影子链与 walk-forward 回测中，Round1 对两校输出空池，`reason = "retired: see shadow-s4-s5-diagnosis"`，`retired = true`。
2. **可回退**：学校启用表 `schools.DEFAULT_ENABLED_SCHOOLS = (S1, S2, S3)`；`run_round1(enabled_schools=...)` 显式传参优先，否则读 `STOCK_PLATFORM_SHADOW_SCHOOLS`（逗号列表，如 `S1,S2,S3,S4,S5`），都未设则用出厂表。原实现 `school_s4_short` / `school_s5_flow` 保留不删，诊断模块直接调用，便于以后复测。未知学校 ID 报错，不静默关校。
3. **S3 保留，不升权**；**S2 照旧**（S2-P1 前向快照继续）；**S1 维持 `pick`**（§11.7 复核不通过，`gate` 仅为实验开关）；Round2 仲裁默认 **`d`** 与学校优先级表不变。
4. 多策略整体**仍是影子**，只积累前向证据；不改出厂 lvrev，升级仍走 Y1 → 签核 → Y2。
5. **不在本增补内**：S4「短期反转」新候选（诊断 §6 E1）、S5 PIT 资金流（E3）。二者是后续前向研究，进入出票前须另行签核。
