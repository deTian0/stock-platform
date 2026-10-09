# 交易系统推进路线图（自有线）

> **状态**：planned（初版 2026-10-09）
> **版本基线**：`v3.12.5`
> **职责**：定义 `stock-platform` 在既有路线图见底之后的**新推进主线**；覆盖 回测 / 策略 / 选股 / 实盘 / 双线收口 五个方向。
> **不改写**：`docs/ROADMAP.md`（M0–M47 / Phase A–E）与 `docs/plans/` 既有 U1–U8、M-D/R/A/U/E/S、MR-1–MR-5 的 done 叙事。
> **上游依据**：本次体检结论见 §7。

---

## 0. 为什么需要这条线

`v3.12.5` 时点的规划余量实测：

| 轨 | 范围 | 状态 |
|----|------|------|
| `docs/ROADMAP.md` | M0–M47 / Phase A–E | 全 done |
| `usable-recommend-review-milestones.md` | U1–U8 | 全 done |
| `capability-domain-merge-roadmap.md` | Now / Next / Later | **除 `M-E4` 全部 done** |
| `market-report-dashboard-merge-milestones.md` | MR-1–MR-5 | 全 done |

**结论**：既有规划体系已执行到尽头，唯一的未开工项是 `M-E4`（实盘），且其原文标注「未立项前禁止开工」。因此「继续完善」不能靠接续旧计划，**必须重开产品目标**——本文件即该目标的可执行展开。

同时存在两个未绑定的工程事实（详见 §7）：

1. **代码写完但跑不起来**（**已于 `G1` 解决**）：体检时 5 个 `stock_platform_*` 包均未安装，`fastapi` / `uvicorn` / `pytest` / `pandas` / `numpy` 全部缺失；`G1` 完成后已全部恢复，全量测试 **526 passed / 0 failed**。
2. **两条日常线并存**：`a-stock-engine`（当前实际在跑 08:30 盘前 / 15:30 盘后自动化）与本仓（自称唯一权威产品仓）职责重叠未收口。

---

## 1. 总目标与排序

**已确认的推进顺序**（用户指定，不跳步）：

```
工程地基 (G)  →  回测 (B, P0)  →  策略深化 (S, P1)  →  选股 (X, P2)  →  实盘 (L, P3 门禁)
                                    ↑
                            双线收口 (C) 贯穿全程
```

**产品目标**：把 `stock-platform` 从「里程碑全绿的研究平台」推进到「回测可信、策略可迭代、选股可日用」的状态；实盘作为门禁项在 `L1` 立项后才启动。

**本轮明确不做**（继承既有红线）：

- React SPA 第二前端主链
- 平行数据抓取链 / 第二套东财客户端
- 把 Skill 仓 `pip install` 进产品依赖
- 默认开启 LLM 辩论 / 默认 `ths_sim`
- 在 G/B/S/X 阶段触碰 `liveTradingEnabled`

---

## 2. 编号与优先级

| 前缀 | 域 | 档 | 与既有编号冲突 |
|------|----|----|----------------|
| **G** | Groundwork 工程地基 | P0 前置 | 无 |
| **B** | Backtest 回测 | **P0** | 无 |
| **S** | Strategy 策略深化 | P1 | 无（既有 `M-S*` 为两段式，不混） |
| **X** | Selector 选股 | P2 | 无 |
| **L** | Live 实盘 | P3 门禁 | 无（既有 `M-E*` 不混） |
| **C** | Consolidation 双线收口 | 贯穿 | 无 |

量级：**S**（≤1–2 人日） / **M**（3–5 人日） / **L**（需拆子项）。

---

## 3. 里程碑明细

### 3.1 G — 工程地基（P0 前置）

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **G1** | 环境恢复与可运行基线 | S | `v3.12.6` | **done（2026-10-09）** 5 个包 editable install 全部成功；`pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）**526 passed / 0 failed / 14.88s**；详见 §7 |
| **G2** | 外部路径与 env 治理 | S | `v3.12.6` | **done（2026-10-09）** `.env` 的 `STOCK_PLATFORM_ENGINE_MARKET_DB` 实测指向 `D:/workspace/stock_trading/a-stock-engine/data_cache/market.db`（3.14 GB 可读）；**全仓 14 个文件**的仓根路径 `D:\workspace\git\` → `D:\workspace\stock_trading\` 迁移；`scripts/ops/stock-platform-daily.xml` 计划任务 `WorkingDirectory` 修正 + 编码声明 `UTF-16`→`UTF-8`（原声明与 UTF-8 实际字节不符）；详见 §7 |
| **G3** | 文档与 CI 一致性 | S | `v3.12.7` | `check_docs.ps1` + `check_versions.ps1` 通过；新路线图挂进 `docs/README.md` 与 `docs/ROADMAP.md` 顶部焦点区；CI `monorepo` job 覆盖范围确认 |

> **G 域不是可选项**：G1 是 B/S/X 的前置。当前状态下任何回测都无法真实执行。

---

### 3.2 B — 回测深化（P0，第一优先）

**背景**：平台现有回测内核是 `packages/research/{pit,walkforward,factor_ic,portfolio}.py`——PIT 无未来函数、滚动样本外摘要、因子 IC/ICIR 都在，**但没有一套能独立跑出完整组合净值曲线的回测**；`walkforward` 目前只出摘要。而 `a-stock-engine/local_backtest.py` 有更完整的引擎（全市场、费用模型、ETF、止损）。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **B1** | 回测基线与复现报告 | M | `v3.13.0` | **done（2026-10-09）** `backtest.py` 组合引擎 + `stock-platform-backtest` CLI；全周期（2020-01～2026-09，**1618 交易日 / 6964 码**）基线：**+90.24% / CAGR 10.53% / MDD -17.14% / 夏普 0.751 / 胜率 46.2% / 630 笔 / 平均持有 35.4 天**；与引擎对照差异逐条归因（持有期 / 区间 / L0 闸门 / ST·生存者 / 复权）；报告 `docs/ops/backtest-baseline.md`。**加载器优化（`v3.13.1`）后全周期 106 s → 65 s** |
| **B2** | 组合级指标补全 | M | `v3.13.1` | `research/portfolio.py` 扩展：年化收益、最大回撤、Calmar、夏普、索提诺、换手率、持仓集中度；口径文档化并入 `docs/contracts/` |
| **B3** | 费用与摩擦模型对齐 | S | `v3.13.2` | 佣金万 0.854 免 5 + 卖出印花税万 5 + 滑点，做成配置项（非硬编码）；与 `local_backtest.py` 常量对齐并互测 |
| **B4** | ETF 与资产类型支持 | M | `v3.13.3` | 回测支持 ETF（免印花税）与股票混池；`_is_etf` 判定规则与上游一致；含 ETF 的净值报告 |
| **B5** | 回测↔在线规则统一层 | M | `v3.13.4` | **吸收 V2 审查第 5 条教训**：冷静期 / 退出条件 / 持仓偏差的判断函数在回测与在线路径中共用同一实现（单点定义 + 双路调用），并有断言测试证明两侧参数一致 |
| **B6** | 回测可视化扩展 | M | `v3.13.5` | `#backtest` 面板扩展：净值曲线 + 回撤带 + 逐日表联动；仍 Jinja + static，不引入新前端依赖 |

---

### 3.3 S — 策略深化（P1）

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **S1** | 因子 A/B 完整版（U7 遗留） | L | `v3.14.0` | 因子 / 闸门变更可带复盘对比；A/B 结果同屏可比；默认关闭旁路，不替换 picks |
| **S2** | 因子库扩展 | M | `v3.14.1` | 在 lvrev（低波 0.5 + 反转 0.5）之外新增至少 2 个正交因子；每个因子过 IC / ICIR 检验，进 `factor_ic` 报告，不达标不启用 |
| **S3** | 闸门参数敏感性 | M | `v3.14.2` | `apply_entry_gates` 关键阈值做敏感性扫描；产出稳健区间结论，避免过拟合单点 |
| **S4** | 行业中性化 / 风险暴露 | L | `v3.14.3` | 打分前做行业中性化与风格暴露约束；回测对照有中性化前后差异 |
| **S5** | LLM 辩论进主路径（可选） | M | `v3.14.4` | 保持默认确定性；可选路径带预算控制与降级；误判不进绩效（对齐 M-A2 口径） |

---

### 3.4 X — 选股（P2）

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **X1** | 全市场选股接入 | L | `v4.0.0` | 从当前 watch 宇宙扩到 `market.db` 全市场（排除 BSE）；耗时与内存有实测数字并写入文档；空宇宙 fail-closed |
| **X2** | 榜单体系对齐 | M | `v4.0.1` | 对齐 `a-stock-engine` 的榜单语义：质量榜 TopN / 短线榜 TopN / 持仓与减仓建议 / 观察名单；口径文档化 |
| **X3** | 命中追踪接入 | M | `v4.0.2` | 10 交易日周期 + 14 天延期 + 同日去重规则落入平台 SQLite；`pre_market` / `post_market` / `pre_market_in_cycle` 三类累计可查 |
| **X4** | 选股↔回测闭环 | M | `v4.0.3` | 每日 picks 自动进回测对照；推荐绩效与回测口径同源（承接 B5） |

---

### 3.5 L — 实盘（P3，门禁）

> **前置**：`L1` 未立项通过前，**禁止开工** `L2` / `L3`。这是对既有红线（`liveTradingEnabled=false`）的显式解禁流程，不是绕过。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **L1** | 实盘立项与券商选型 ADR | S | `v5.0.0` | 产出 ADR：券商选定（候选：富途 / 同花顺 / 其它）、解除红线的影响面清单、失败回滚方案、合规与资金上限；**经显式确认后才置 Accepted** |
| **L2** | 券商适配器实现 | L | `v5.0.1` | 实现 `BrokerPort` 适配器（订单 / 成交 / 持仓 / 账户契约）；全程可注入 transport 做离线测；缺凭据 fail-closed |
| **L3** | 实盘灰度与风控 | L | `v5.0.2` | 小额灰度；订单状态机逐态处理（接受 / 部成 / 全成 / 撤单 / 拒单 / 状态未知，剩余量结合未结订单）；每日对账 |

**承接的既有教训**（来自 `V2-code-review-20260905`，逐条必须在 `L2`/`L3` 验收）：

- 信号新鲜度必须显式校验，不能靠数据更新时间兜底
- 调度判断按窗口而非精确秒
- 跨日复核需「原计划日 / 复核日」双时间轴
- 订单状态机必须逐态处理
- 回测与在线规则共用同一实现（见 `B5`）
- 费用口径与账户实际对齐

---

### 3.6 C — 双线收口（贯穿）

**背景**：`a-stock-engine` 是当前**实际在跑**的日常线（08:30 盘前选股、15:30 盘后复盘），`stock-platform` 是**自称权威**的产品仓。二者选股内核同源（lvrev），但各有一套调度、存储、报告。这构成最大的长期风险：第五套重复实现。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **C1** | 双线职责边界定稿 | S | 随 `G3` | 产出职责表：谁是日常调度主链、谁是数据真相源、什么情况下用哪条；写入 `docs/plans/` 并互相交叉链 |
| **C2** | 数据真相源统一 | M | 随 `B1` | 确认 `market.db` 为唯一历史行情真相源（平台只读已在 ADR 0050 落地）；`selections.db` / `picks.db` 等派生库的归属与同步方式写明 |
| **C3** | 重复实现收敛清单 | M | 随 `S1` | 列出选股引擎 / 回测引擎 / 行情抓取 / 多 Agent 的重复实现，逐项标注「保留 / 降级为参考 / 废弃」；不批量删除，按里程碑渐进收敛 |

**约束**：C 域只做「定边界 + 定归属 + 列清单」，**不在本路线图内执行大规模代码合并**。

---

## 4. 依赖关系

```text
G1（环境恢复）
 ├─→ G2（env 路径）─→ B1（回测基线）─→ B2/B3/B4（指标/费用/ETF）
 │                                      └─→ B5（回测↔在线统一）─→ X4
 ├─→ G3（文档 CI）+ C1（职责边界）
 └─→ B6（可视化，依赖 B2 指标）

S1（因子 A/B）← B1 + B5
S2/S3/S4 ← S1
S5 ← S1

X1（全市场）← B1（回测可信）+ G1
X2 ← X1；X3 ← X1；X4 ← B5 + X3

L1（立项）← B5 + X4（回测与实盘口径已统一，才具备实盘前提）
L2 ← L1 Accepted；L3 ← L2

C2 ← B1；C3 ← S1
```

**关键路径**：`G1 → B1 → B5 → X4 → L1`。这条链上的每一项都是后者不可绕过的前置。

---

## 5. 版本映射建议

| 阶段 | 范围 | 建议 tag | 类型 |
|------|------|----------|------|
| G | G1–G3 | `v3.12.6`（G1+G2 合并） → `v3.12.7`（G3） | patch |
| B | B1–B6 | `v3.13.0` → `v3.13.5` | minor |
| S | S1–S5 | `v3.14.0` → `v3.14.4` | minor |
| X | X1–X4 | `v4.0.0` → `v4.0.3` | **major**（能力边界从 watch 扩到全市场） |
| L | L1–L3 | `v5.0.0` → `v5.0.2` | **major**（解禁实盘红线） |

每个里程碑收口时按既有流程：勾选本文件 → 更新 `CHANGELOG.md` → 更新 `VERSION` → `scripts/release_tag.ps1` → `git push --follow-tags`。

---

## 6. 红线（继承 + 新增）

**继承自 `docs/upstream-archive.md` / `capability-domain-merge-roadmap.md`**：

1. 一条数据链；东财只走 `em_get`；能力矩阵 fail-closed（典型 409）
2. 默认纸面 `SIMULATE`；不静默用 fixtures 冒充 live
3. 禁止 `pip install` Skill 仓进产品依赖；禁止平行抓取第二链
4. `market.db` 只读挂载，与 brief SQLite 分离（ADR 0049 / 0050）
5. 真实 token 不入库、不入文档、不进对话
6. 非整仓 merge；禁止 fork 出第二条产品主链

**本路线图新增**：

7. **`L1` 未立项前，任何人不得用「完善」为由触碰 `liveTradingEnabled` 与实盘券商代码。**
8. **B 域回测结果在 `B5` 完成前，不得作为策略取舍的唯一依据**——因为此时回测与在线规则尚未共用同一实现。
9. **C 域不执行为收敛而做的批量删除**；只定边界、列清单，代码收敛按里程碑渐进。

---

## 7. 实测记录（本次体检，2026-10-09）

| 项 | 实测值 | 备注 |
|----|--------|------|
| `VERSION` | 3.12.5 | 对应提交 `0da5f2d` |
| 最新 tag | `v3.12.5` | 已 push，`main` 与 `origin/main` 同步 |
| 工作树 | 干净 | 仅 untracked `userinput.py` |
| 代码规模 | 131 个 .py（src 81 / tests 50），src 约 17.0k LOC | `packages` + `apps` |
| 文档规模 | 53 个 ADR（0001–0053）+ contracts / ops / plans | — |
| Workbench API | 58 个 path+method | 有全量 API 自动化测 + OpenAPI 契约测 |
| `.venv` 解释器 | Python 3.14.6（`D:\soft\path\miniconda3`） | pyvenv.cfg 的 home 可解析，**能启动** |
| `.venv` 依赖 | **不可用** | 5 个 `stock_platform_*` 包未安装；`fastapi`/`uvicorn`/`pytest`/`pandas`/`numpy`/`mootdx`/`tushare` 全 Missing；仅 `pydantic`/`jinja2`/`httpx`/`requests` 可用（conda base `--system-site-packages`） |
| **G1 执行结果** | **已恢复** | 5 个包 editable install 成功；`pytest packages apps` = **526 passed / 0 failed / 1 warning / 14.88s**（warning 为 fastapi testclient 的 httpx 弃用提示，非阻塞） |
| **B1 执行结果** | **已完成** | 全周期 2020-01-02～2026-09-03（1618 交易日 / 6964 码）**+90.24%**，CAGR 10.53%，MDD -17.14%，夏普 0.751，胜率 46.2%，630 笔，平均持有 35.4 天；加载 **11.5 s** + 回测 **48.6 s**（2026-10-09 加载器优化后；此前为加载 53.7 s + 回测 47.2 s）；报告 `docs/ops/backtest-baseline.md` |
| **G2 执行结果** | **已完成** | 仓根路径全仓迁移 14 文件；`market.db` 冒烟：`resolve_engine_market_db()` → `D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`，`get_daily(['600519'])` = **406 行**（2025-01-02～2026-09-03），`get_fundamentals_pit` 正常；`check_docs`（112 required / 139 md）+ `check_versions`（5 pkg）双绿；全量测试 **526 passed / 14.14s** |

### 7.1 G1 安装明细（2026-10-09）

| 项 | 值 |
|----|-----|
| 实际装到的版本 | numpy 2.5.3 · pandas 3.0.6 · fastapi 0.143.0 · uvicorn 0.54.0 · starlette 1.7.0 · pytest 9.1.1 · httptools 0.8.0 · websockets 17.2 |
| 必须的安装顺序 | `providers → research → agents → execution → workbench` |
| 顺序原因 | `agents` / `execution` / `workbench` 均声明依赖 `stock-platform-providers`，该名字 **PyPI 上不存在**，必须先本地 editable 安装，否则依赖解析直接失败 |
| 失败过的坑 | conda base（`D:\soft\path\miniconda3`）曾有 `stock-platform-providers 3.8.1` 失效残留；venv 为 `--system-site-packages` 故 pip 尝试卸载它 → `WinError 3 系统找不到指定的路径` → 整次安装中止。残留被该次失败卸载动作清掉后（判据：`pip show stock-platform-providers` 返回 `Package(s) not found`），重跑即成功 |
| 噪音（非故障） | 每次 pip 都会打印 `[safe-delete][SAFE_DELETE_FAIL_CLOSED] ... trash-failed`，为本机 safe-delete 拦截缓存清理所致，**不影响安装** |
| 网络 | 清华 + 阿里源，实测约 132 kB/s；numpy 12.7 MB 耗时 1 分 40 秒 |
| 复用 base 的依赖 | `pydantic` 2.46.4 / `jinja2` / `httpx` / `requests` / `anyio` / `packaging` / `pluggy` 直接来自 conda base 的 site-packages，未重复下载 |

> **修正记录**：`WORKBUDDY.md` §「虚拟环境：丢掉重建」称「两个已拷贝的 .venv 不能用」——对 `stock-platform` 而言**只对了一半**：解释器完好，缺的是依赖安装。原文建议「重建」，实测「在原 venv 上装依赖」成本更低（依赖极轻：providers 无硬依赖，research 仅 numpy+pandas，workbench 仅 fastapi+uvicorn+jinja2）。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-10-09 | 初版：体检既有规划见底 → 定义 G/B/S/X/L/C 六域里程碑；确认推进顺序 回测 → 策略 → 选股；`M-E4` 降为 `L1` 门禁项 |
| 2026-10-09 | `G1` 完成：5 个包 editable install 恢复，全量测试 526 passed；回填 §7 实测记录 |
| 2026-10-09 | `B1` 完成：组合回测引擎 + CLI + 基线报告；`apply_entry_gates` 向量化（200 s→106 s）；修 `close` 未复权导致假亏损；发布 `v3.13.0` |
| 2026-10-09 | `B1` 补强：行情库加载器 54.9 s → 12.5 s，全周期回测 106 s → 65 s（指标逐位不变）；新增 `test_backtest_cli.py` 锁定加载语义（8 passed）；发布 `v3.13.1` |
| 2026-10-09 | `G2` 完成：全仓仓根路径迁移 + 计划任务 XML 修正 + `market.db` 挂载冒烟通过；`G1`+`G2` 合并发布 `v3.12.6` |
