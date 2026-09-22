# 真实可用：选股推荐 + 复盘系统（里程碑计划）

> **状态**：in progress（**v3.10.6**：U8 回测↔推荐联通 + 策略对比 engine 面板 + 日批 LiveDay；文档日：2026-09-15）  
> **版本基线**：约 **v3.10.5**（U6/U7）→ **v3.10.6**（联通 / UX / 日批一键）  
> **编号**：`U1`–`U8`（Useable 线，**不改写**已完成的 M0–M47 / Phase A–E / `v3.x` 叙事）  
> **关联总览**：[`docs/ROADMAP.md`](../ROADMAP.md)

---

## 1. 产品目标

做成**真实可用**的「选股推荐 + 复盘」系统：

| 优先级 | 含义 |
|--------|------|
| **P0 先真实可用** | live 数据、交易日能出推荐、结果可落盘、事后能复盘看对错、样本进绩效 |
| **P1 再策略迭代** | 换因子 / 闸门对比 / LLM 辩论 / 回测进主路径 — **明确后置**（U7 完整版） |

### 什么叫「真实可用」（Definition of Done）

1. **每日能出**：CN 交易日，live 日线（`cn_tushare_http` + token）对 **watch** 打出 TopN；结果头可见 asof / 宇宙 / provider / 闸门。  
2. **不假冒 live**：失败 fail-closed；仅显式 `STOCK_PLATFORM_BRIEF_FALLBACK=replay` 才用 fixtures。  
3. **落得住**：brief 持久化（**默认 SQLite**，ADR 0049），可按日回看。  
4. **复得盘**：历史推荐 → 复盘表（T+1 / pending / 方向对错）；口径对齐 `direction_accuracy`。  
5. **绩效闭环**：生成落库后样本进入 performance JSONL；`#performance` 能看到 pending/settled。  
6. **批得动**：日批脚本支持 live provider（默认可仍 replay 保 CI）。  
7. **纸面安全**：默认 SIMULATE；无静默实盘；不泄露 token。  
8. **运维可读**：health 可见 preset / BRIEF_FALLBACK / supplementTokenConfigured（布尔）。

**非 DoD**：全市场扫、策略 A/B 进每日主路径、SPA。

---

## 2. 硬约束（仓库红线）

- 一条数据链；东财只走 `em_get`；capability matrix **fail-closed**。  
- 默认纸面 **SIMULATE**，不默认实盘。  
- **不**静默用 fixtures 冒充 live。  
- 当前可用 live 日线：`cn_tushare_http` + `STOCK_PLATFORM_TUSHARE_TOKEN`。  
- UI：Jinja + static；中文。  
- 禁止把真实 token 写入仓库 / 本计划 / CHANGELOG。  
- **持久化**：现阶段 **SQLite**；PostgreSQL 后续（ADR 0049）。  
- **engine market.db** 只读，与 brief SQLite **分离**。

---

## 3. 诚实现状（2026-09-15 / v3.10.6）

| 项 | 状态 | 说明 |
|----|------|------|
| U2 SQLite brief 落库 + 历史回看 | **done**（v3.10.2） | API + UI 历史表 |
| U3 复盘 UI | **done**（v3.10.3） | 历史「复盘」→ 明细表 + direction_accuracy |
| 推荐→绩效闭环 | **done**（v3.10.3） | 落库后 auto log-brief；`#performance` 见 pending |
| pending 自动结算 | **done**（v3.10.4） | autoSettle / POST settle；engine market.db 优先 |
| U5 health 布尔 | **done**（v3.10.3） | preset / fallback / supplementTokenConfigured |
| U4 日批 live | **done（最小）**（v3.10.3）→ **一键**（v3.10.6） | `-LiveDay` / `--settle-after` |
| U1 推荐 UI / live 路径 | **done（含冒烟）**（v3.10.3） | 本机 live asof=2026-09-14 有 picks；见 §7 |
| U6 更大宇宙可选 | **done（轻量）**（v3.10.5） | UI/API `universeTier` core/watch/full；默认仍 watch |
| U7 回测进 Workbench | **done（最小切片）**（v3.10.5） | `#backtest` 滚动推荐复盘；**不**插入每日推荐主路径 |
| U8 回测↔推荐 / 策略对比真面板 | **done（切片）**（v3.10.6） | 点日看推荐；perf 摘要条；compare 用 engine 面板 |
| 回测 / PIT 完整策略迭代 | 后置 | 因子 A/B、LLM 辩论可选等仍 Later |

---

## 4. Now / Next / Later（商用可用最短路径）

| 档 | 内容 | 一句话 |
|----|------|--------|
| **Now（本轮）** | U8 联通 + 策略对比 engine + LiveDay | **v3.10.6 已交付** |
| **Next** | 日批默认宇宙 watch 文档化一键；推荐页近 N 日 accuracy 迷你图；复盘空态再压 | 商用日用摩擦再降 |
| **Later** | U7 完整 A/B；LLM 辩论可选；全市场扫；PostgreSQL | 策略迭代与规模化 |

---

## 5. 里程碑明细

### U1 — 每日推荐可用（UI + live 默认路径） · **Now（收口）** · 量级 **S–M**

**验收标准**

- [x] `#recommend` / 向导：live 默认 asof = `last_completed_cn_session`；replay 仍用样例日（代码 + 单测）。  
- [x] 结果头：`asof`、`asofMode`、`universeTier`、provider、softGates、条数（代码 + 单测）。  
- [x] 加载态 / 空态中文 tip（含 Tushare 提示）（代码 + 单测）。  
- [x] 可切 `cn_tushare_http`；无 token fail-closed；未设 fallback 时不静默 fixtures（代码 + 单测）。  
- [x] **本机 env 冒烟**：2026-09-15 live 通过（asof=2026-09-14，watch 前 5，有 picks；见 §7）

---

### U2 — 每日 brief 持久化（SQLite） · **done（v3.10.2）**

- [x] 全部验收项（见 CHANGELOG 3.10.2）

---

### U3 — 复盘 UI（接现有 review API） · **done（v3.10.3）**

- [x] API：`GET /api/research/briefs/{asof}/review`  
- [x] UI：历史行「复盘」→ 明细表 + 汇总（settled / pending / directionAccuracy）  
- [x] 汇总口径与 `performance.direction_accuracy` 语义对齐（看多 Buy；缺行情 pending）  
- [x] fixtures / 注入 get_daily 单测 + UI 字段 smoke  

---

### 推荐 → 绩效闭环 · **done（v3.10.3）**

- [x] 落库成功后自动写入 performance JSONL（同 asof+symbol 幂等跳过）  
- [x] 响应标注 `perfLogOk` / `perfLogAppended`  
- [x] `#performance` 展示 `pendingCount` / `settledCount` / `direction_accuracy`  
- [x] 单测覆盖 auto-log + fromStore  

---

### U4 — 日批支持 live provider · **done（最小，v3.10.3）** → **一键（v3.10.6）**

- [x] `Invoke-DailyPipeline.ps1` / `stock-platform-daily` 支持 `tushare`  
- [x] 无 token：非 0 退出 + 可读错误；不自动降级 fixtures  
- [x] 默认仍 `replay`；`daily-pipeline.md`「真实日用」  
- [x] 非交易日 exit 0 保留  
- [x] `-LiveDay` / `--settle-after`：live + 落库 + 记入/结算绩效（v3.10.6）

---

### U5 — 运维可见性轻补 · **done（v3.10.3）**

- [x] `/api/ops/health`、东财熔断、start bat、`.env.example`  
- [x] health：`providerPreset`、`briefFallback`、`supplementTokenConfigured`（仅布尔）  
- [x] UI ops 面板 + `live-startup.md` 日用最小步骤  

---

### U6 — 更大宇宙可选 · **done（轻量，v3.10.5）**

- [x] tier 可切换（core/watch/full）；UI + `/defaults?universeTier=` + brief/wizard  
- [x] 耗时/规模在 hint 中明示；默认仍 watch；CI / 回测有符号上限  
- [ ] 全市场 / 百万级扫 — **刻意不做**

### U7 — 策略 / 回测进主路径 · **done（最小切片，v3.10.5）** / 完整版 Later

- [x] Workbench `#backtest`：滚动推荐复盘汇总 direction_accuracy（复用 `review_stored_brief`）  
- [x] 优先 engine market.db；无 DB fail-closed  
- [x] **不**默认插入每日推荐主路径  
- [ ] 因子/闸门变更带复盘对比（完整 A/B）— Later  
- [ ] LLM 辩论保持可选  

### U8 — 回测↔推荐联通 + 策略对比真面板 · **done（切片，v3.10.6）**

- [x] 回测表点 asof → `#recommend` 加载该日 picks（存档优先，否则重生成）  
- [x] 推荐页 compact 绩效摘要 + 回测/绩效入口  
- [x] 策略对比优先 engine 多日 PIT 面板；`panelSource` / `requireEngine`  
- [x] 日批 `-LiveDay` / `--settle-after`  
- [x] fail-closed / 空态中文统一（轻量）  

---

## 6. 总览表

| ID | 名称 | 档 | 状态 |
|----|------|----|------|
| U2 | brief 持久化（SQLite） | — | **done（v3.10.2）** |
| U3 | 复盘 UI + 口径对齐 | Now | **done（v3.10.3）** |
| 闭环 | 推荐 → log-brief → `#performance` | Now | **done（v3.10.3）** |
| U5 | ops health 布尔字段 | Now | **done（v3.10.3）** |
| U4 | 日批 live provider | Now | **done（最小+一键，v3.10.6）** |
| U1 | live UI 收口 + 本机冒烟 | Now（收口） | **代码 done + 冒烟通过（§7）** |
| 结算 | pending → JSONL autoSettle | Next | **done（v3.10.4）** |
| U6 | 更大宇宙 | Later→轻量 | **done（轻量，v3.10.5）** |
| U7 | 策略/回测进主路径 | Later→切片 | **done（最小切片，v3.10.5）**；完整 A/B Later |
| U8 | 回测↔推荐 / compare engine / LiveDay | Now | **done（v3.10.6）** |

---

## 7. 本机冒烟记录（U1）

| 日期 | 结果 | 说明 |
|------|------|------|
| 2026-09-15 | **live 通过** | 本机 `.env` 已配 TOKEN；`TushareHttpProvider` + watch 前 5 只、asof=`2026-09-14` → `pick_count=1` / `panel=5`；未打印 token |
| 2026-09-15 | **v3.10.4 复验** | defaults/brief/briefs/review/performance + engine settle + live asof=2026-09-14 picks=1；聚焦 pytest 74 passed；未打印 token |
| 2026-09-15 | **v3.10.5** | engine rolling-review：lastN=3、5 码 → settled=4 / direction_accuracy=0.5；聚焦 pytest 19 passed；未打印 token |
| 2026-09-15 | **v3.10.6** | 见本轮 pytest + 有 engine DB 时 strategy/compare + rolling-review 冒烟；未打印 token |

---

## 8. 刻意不做（本阶段）

- 实盘 / 默认 liveTrading  
- SPA  
- 静默 fixtures  
- 全市场 / 大改因子  
- 回测**插入**每日推荐主路径（U7 完整版）  
- 现在就上 PostgreSQL  
