# 下一组里程碑与技术方案

> **状态**：planned（2026-11-05）  
> **版本基线**：`v4.14.0`（F1/T3/A1/R5-P 已随本版发布；Y2 / 全量 R5 仍开放）  
> **范围**：T3 · CLI/Agent 可调用面 · 符号/基准修正 · Y2 · R5（平台侧）  
> **不改写**：`trading-system-roadmap.md` 已 done 叙事；本文件是现行开放项的**可执行展开**。  
> **红线**：`market.db` 只读；执行层 SIMULATE；不解禁实盘；不默认开 LLM。

现行快照仍以 [`../STATUS.md`](../STATUS.md) 为准。本计划落地后勾选 STATUS / 路线图修订记录。

---

## 0. 目标与排序

把「日用可信 + agent 可编排 + 研究能落档 + 数字不撒谎 + ETF 形状就绪」收成**五块砖**，按依赖顺序推进：

```text
F1 符号/基准修正  ──┐
                    ├──→  T3 数据质量  ──→  （可信度底座）
A1 CLI 可调用面  ──┘         │
                             ├──→  Y2 采纳落地（须签核）
R5-P 平台侧 ETF 形状 ────────┘（生产侧回补仍门禁；不阻塞前四项）
```

| 优先级 | ID | 名称 | 量级 | 建议 tag | 门禁 |
|--------|----|------|------|----------|------|
| P0 | **F1** | 符号前缀 + 基准身份修正 | S | `v4.13.8`（patch） | 无 |
| P0 | **T3** | 数据质量体检单点 | M | `v4.14.0`（minor） | 无 |
| P0 | **A1** | CLI / agent 可调用面 | M | `v4.14.1`（patch） | 无 |
| P1 | **Y2** | 采纳落地 | M | `v4.14.2` 或沿用 `v4.10.1` 语义 | **人工签核** |
| P1 | **R5-P** | ETF 进宇宙·平台侧 | M | `v4.15.0`（minor；原 R5 `v4.8.0` 顺延） | 生产侧 ETF 日线回补 |

**建议实施顺序**：`F1 → T3 → A1` 连续做完；`Y2` 等有 `adopt` 证据再开；`R5-P` 可与 A1 并行做「形状与标注」，**全开 ETF 宇宙**等生产侧回补完成。

---

## 1. F1 — 符号前缀 + 基准身份（「数字在撒谎」）

### 1.1 问题

| 现象 | 根因 | 后果 |
|------|------|------|
| `exchange_prefix("588080")` → `sz` | `symbol.py` 只把 `6`/`9` 当沪市；`5` 开头基金未进沪市规则 | 东财/腾讯/新浪/westock 四源对沪市 ETF 取不到（`em_secid` 错） |
| 绩效/归因基准 `000905` | 引擎库裸码 + 前缀规则推成 `sz000905`（厦门港务），不是中证 500 `sh000905` | `avgAlpha` / `dayAlpha` **不是指数超额**；报告虽有 `benchmarkWarning`，口径仍脏 |

### 1.2 技术方案

**单点仍在** `packages/providers/.../symbol.py` 的 `exchange_prefix`：

1. 扩展沪市规则：在既有 `6`/`9` 之外，纳入明确的**沪市基金/ETF 段**（至少 `5` 开头六位；以契约表为准，补参数化测试：`510xxx`/`511xxx`/`512xxx`/`513xxx`/`515xxx`/`518xxx`/`588xxx` 等）。
2. **北交所 / 深市规则不变**（`92`/`4`/`8` → bj；其余默认 sz 的语义写进契约，避免「凡 5 都沪」误伤）。
3. 基准身份：
   - 新增只读解析：`resolve_benchmark_identity(symbol, engine_db)`（或扩展现有 `resolve_benchmark_symbol`）——用 `fundamentals.name` / 指数表（以引擎实际表为准）核对「声明指数 vs 库内名称」。
   - 默认基准改为**带交易所语义的权威键**（方案 A：存 `000905.SH` 并在读库时归一；方案 B：保持裸码但 **强制** `exchange_prefix` 对指数码走沪市规则 + 名称断言）。实施时二选一写进 ADR，**禁止** silent 用个股当指数。
   - 不匹配 → fail-closed 警告（已有 `benchmarkWarning`）升级为：绩效 alpha 段标 `unavailable`，**不编造**超额。
4. 回归：providers 单测锁死前缀表；research 增加「基准名 ≠ 厦门港务」守卫；westock/day_quote 相关用例用 `588080` 冒烟。

### 1.3 验收

- [x] `exchange_prefix("588080") == "sh"`；深市股票样本不变
- [x] 默认基准解析后名称可识别为中证 500（或配置项显式覆盖）；个股碰撞 → alpha 段 unavailable
- [x] ADR + `docs/contracts` 符号/基准节；`check_docs` 登记
- [x] 相关 pytest 全绿；不改选股默认权重

### 1.4 非目标

不迁基准到别的指数品种（如强行改 000300）；不写 `market.db`；不在本里程碑扩全球市场前缀。

---

## 2. T3 — 数据质量体检（`v4.14.0`）

### 2.1 目标

`research.data_quality` 单点 + CLI `stock-platform-data-quality`：**零网络、只读**扫 `market.db`，产出 JSON + Markdown（+ 可选 HTML），并作为 `loop_health` **又一路**信号。严重项 → `degraded`；**永不阻断**选股 / 日更。

### 2.2 检查项（契约化阈值，事前登记）

| 检查 | 方法 | 严重度建议 |
|------|------|------------|
| 单位口径 | 复用 `pct_scale` 拟合投票；标出疑似小数/百分点混用的码 | warn → 比例过高升 degraded |
| 停牌 / 零成交 | 近窗零成交占比、连续停牌天数 | warn |
| 除权跳变 | `close` 单日跳变超阈值且无对应复权因子/说明 | warn / degraded |
| 脏码 | 非 6 位、ETF 前缀表外、与 F1 前缀表不一致 | warn |
| 指数 · ETF 覆盖缺口 | 声明基准与常用 ETF 列表在 `daily_price` 的缺日/缺码 | degraded（缺基准）/ warn（缺可选 ETF） |

实现约束（对齐 `loop-health`）：

- `market.db`：`mode=ro`；方法段级 try/except，**永不抛**
- providers **函数内懒导入**
- 报告写入平台自有 `local/health/`（或现 `STOCK_PLATFORM_LOOP_HEALTH_DIR`），**不写行情库**
- CLI 退出码恒 0；裁决在 payload

### 2.3 与 loop_health 接线

1. `collect_loop_health` 增段 `dataQuality`（形状与其它段一致：`status` / `reason` / 摘要计数）。
2. 裁决表：仅 `degraded` 档进入 `warned`；**不**进 `COVERAGE_HARD_FAIL` / `blocked`。
3. 契约 `loop-health.md` 扩一节；新契约 `docs/contracts/data-quality.md`；ADR `0091`（`0090` 已用于 F1）。

### 2.4 CLI / API

```text
stock-platform-data-quality [--asof] [--market-db] [--out-dir] [--json|--md]
```

可选：Workbench `GET /api/ops/data-quality` 只读转发（对齐 T1 零业务逻辑）。

### 2.5 验收

- [x] 五项检查均有单测（fixture SQLite，不碰生产库）
- [ ] 真机对当前 `STOCK_PLATFORM_ENGINE_MARKET_DB` 跑通一趟，报告落盘
- [x] `loop_health` 出现 `dataQuality`；严重项只降级
- [ ] 全量或 research+providers 相关 pytest 绿

### 2.6 依赖

**F1 宜先做**：脏码 / ETF 前缀检查应消费修正后的 `exchange_prefix`，避免体检用错误规则「合法化」错前缀。

---

## 3. A1 — CLI / Agent 可调用面

### 3.1 目标

让 workbuddy / 其它 agent **不必进 Workbench UI** 即可编排：辩论侧车、纸面最小闭环、以及一份 SSOT 命令一览。

### 3.2 交付物

| 交付 | 说明 |
|------|------|
| **`stock-platform-debate`** | 独立 CLI：`--engine off\|deterministic\|llm`、`--symbol` / `--from-brief`、`--provider workbuddy\|...`、预算与 `LLM_PROVIDER` 走现有单点；输出 JSON；**不写** picks/绩效（`excludedFromPerformance`） |
| **纸面最小 CLI** | 例如 `stock-platform-paper`：`status` / `ensure-default` / `draft` / `execute` 子集，封装现有 execution API 语义；默认 SIMULATE；无 live 开关 |
| **`docs/ops/cli-catalog.md`** | 全仓 `stock-platform-*` 一览表：包、用途、是否读 `local/.env`、典型 agent 调用例；`dotenv-loading` 改链到此表 |
| README / STATUS | 日用路径指向 catalog；注明「仅 API」的残余能力（intel-report、分钟行情等） |

### 3.3 技术方案要点

- `debate` CLI 放 `packages/agents` 或 `research` 薄包装：若放 research，继续 **DI / 可选依赖 agents**，避免 research 硬依赖 openai。
- 纸面 CLI 放 `packages/execution` 的 console script，复用 `PaperBroker` / ledger，不复制状态机。
- catalog 由 `check_docs` 登记；建议加轻量测试：`pyproject.toml` 的 scripts 集合 ⊆ catalog 表格（防再漂移）。

### 3.4 验收

- [x] `stock-platform-debate --help`；deterministic/off 单测；llm 冒烟依赖本机 key（可选）
- [x] 纸面 CLI `demo`：确保默认策略 → 建草稿 → 模拟执行且 `liveTradingEnabled=false`
- [x] `cli-catalog.md` 覆盖 research 全部 scripts + 新 CLI
- [x] 文档声明仍仅 API 的能力清单

### 3.5 非目标

不把全部 `/api/market/*` 都做成 CLI；不做第二套调度器；不把 deep-graph 默认打开。

---

## 4. Y2 — 采纳落地（须人工签核）

### 4.1 目标

把 Y1 判为 **`adopt`** 的候选，经**显式签核**写入命名策略档案 / 出厂闸门常量；无证据、无签核不落档。

### 4.2 前置条件（硬）

1. 最新 `stock-platform-strategy-adoption` 报告中存在候选 `decision=adopt`（全窗通过）。
2. 负责人书面/会话确认签核（记录进 ADR 或 `local/` 外的签核笔记——**不要**把秘密写进 git）。
3. F1 基准修正已合并（避免用脏 alpha 当签核依据）。

若长期只有 `reject` / `insufficient`：**Y2 不开工**，只保持 Y1 可复跑。

### 4.3 技术方案

1. **输入**：Y1 JSON 报告路径 + 候选 `name`。
2. **动作**（签核后）：
   - 在 `local/strategy/` 或仓库内 `configs/strategies/`（若适合版本管理）写入命名档案（`StrategyConfig` 单点形状）；
   - 若改出厂默认：更新**唯一**常量定义处 + ADR + 契约；**禁止**多处抄写权重。
3. CLI 建议：`stock-platform-strategy-adopt --report ... --candidate ... --yes`（无 `--yes` 只打印 diff；CI 默认不改档）。
4. 回归：采纳前后 A/B 或 adoption 复跑，确认生产默认指针切换可逆（保留上一档档案）。

### 4.4 验收

- [ ] 无 `adopt` / 无 `--yes` → 不改生产默认
- [ ] 有签核 → 档案落盘 + 文档同步 + 测试锁默认 id
- [ ] 仍 SIMULATE；不写 brief/picks 账本

### 4.5 版本

路线图原写 `v4.10.1`；按完成顺序也可落在 `v4.14.2`。**以 STATUS 与本文件 tag 列为准**，避免回填旧号造成误解。

---

## 5. R5-P — ETF 进宇宙（平台侧）

### 5.1 拆分

| 子项 | 谁做 | 本计划 |
|------|------|--------|
| ETF 日线写入 `market.db` | **生产侧 / 引擎回补** | **不做**（ADR 0058） |
| universe / ③A 形状支持 ETF、缺口 fail-closed 标注 | 平台 | **做（R5-P）** |
| 默认日用宇宙改为含 ETF | 平台 | 仅当回补达标后打开 |

### 5.2 平台侧技术方案

1. 复用 B4 `asset_class`；universe 解析支持 `stock|etf|all`（若尚未在日用路径贯通，补齐）。
2. ③A 持仓榜：ETF 行展示与 T+1 文案差异（ETF 无股票式 T+1 冻结句 —— 与简报已有口径对齐）。
3. 覆盖守卫：ETF 池在 `coverage_snapshot` / T3 缺口检查中**显式**列出缺码；未回补 → `degraded` + 中文原因，**不**静默当股票池。
4. 与 F1 联动：沪市 ETF 前缀正确后，westock/东财补数路径才有意义。

### 5.3 验收（R5-P）

- [x] 文档写明「缺 ETF 日线时行为」；CLI/榜单有显式标注
- [x] 单测：无 ETF bar 时 fail-closed 文案稳定
- [x] **不**宣称 R5 全 done，直到生产侧回补 + 全市场 ETF 宇宙验收另开刀

### 5.4 全量 R5（后续）

生产侧回补完成后：打开 `universe=etf|all` 日用选项、补基准与费用（ETF 免税已有 B4）、真机跑一轮 rankings/③A。目标 tag 建议 `v4.15.0`。

---

## 6. 版本与文档同步清单

每块砖收口时：

1. 勾选本文件验收框  
2. `CHANGELOG` `[Unreleased]` → 发布节  
3. `VERSION` / 各包版本（大里程碑）  
4. `docs/STATUS.md` 开放项  
5. `trading-system-roadmap.md` 修订记录一行  
6. `check_docs` + `check_versions` + pytest  

| Tag | 内容 |
|-----|------|
| `v4.13.8` | F1 |
| `v4.14.0` | T3 |
| `v4.14.1` | A1 |
| `v4.14.2` | Y2（若签核发生） |
| `v4.15.0` | R5 全量（回补后）或仅 R5-P 视完成度 |

---

## 7. 风险与决策点

| 风险 | 缓解 |
|------|------|
| 改 `exchange_prefix` 影响面广 | 参数化金样例 + 能力矩阵冒烟；先 patch 后 T3 |
| 基准改为 `.SH` 与引擎存盘后缀不一致 | ADR 写清归一规则；一处转换 |
| Y2 长期无 adopt | 保持 Y1 复跑；不人为放宽 AdoptionRule |
| agent 误开 llm 打爆配额 | debate CLI 默认 `engine=deterministic`；llm 需显式 + `DEEPSEEK_*` |
| 把 R5-P 当成 R5 完成 | STATUS 文案区分「形状就绪」vs「宇宙已开」 |

**需要你拍板的点（实施前）**：

1. F1 基准方案 A（权威键带交易所）还是 B（裸码 + 名称断言）？  
2. Y2 策略档案进 **git 跟踪的 configs/** 还是只进 **`local/strategy/`**？  
3. A1 纸面 CLI 是否本轮就要，还是先做 debate + catalog？

---

## 8. 非目标（本组明确不做）

- 实盘 L2/L3、开源许可证、默认开启 LLM  
- 平台写 `market.db` / 代替生产侧 ETF 回补  
- React 第二前端、平行行情链  
- 无签核改出厂 `min_pick_score` / 中性化默认开  
- **多策略五校 Final Board**（并行影子链；见 [`multi-strategy-final-board.md`](multi-strategy-final-board.md) / ADR 0093 MVP；本组 F1–R5-P 不替代）  
