# 契约：能力矩阵

> 状态：**Accepted（M0.2）** · 语义对齐 tick-stock-panel `CAPABILITY_REGISTRY`  
> 运行时：能力矩阵是路由 **唯一权威**；UI 不硬编码能力清单。

## 能力清单（顺序即设置页/文档展示序）

| id | 中文 | 数据集 | 说明 | TSP 默认源（参考） | TickFlow 档位门槛（参考） |
|----|------|--------|------|-------------------|---------------------------|
| `daily` | 日K | daily | 历史 K 与实时覆写 | tickflow | none（免费通道可有日K） |
| `adj_factor` | 除权因子 | adj_factor | 前复权计算基准 | tickflow | starter |
| `realtime` | 实时行情 | realtime | 全市场快照 | tickflow | starter |
| `minute` | 分钟K | minute | 分时与分钟回测 | tickflow | pro |
| `depth5` | 五档盘口 | depth5 | 封单/深度 | tickflow | pro |
| `financial` | 财务数据 | financial | 指标与三表 | tickflow | expert |
| `full_minute` | 全量分钟 | full_minute | 盘中全市场当日落盘 | tickflow | expert |
| `fund_flow` | 日级资金流 | fund_flow | 个股主力/大小单日级净流入（**元**） | —（平台扩展，ADR 0020） | — |
| `lhb` | 龙虎榜 | lhb | 个股上榜记录 + 买卖席位 TOP5 + 机构动向（**元**） | —（平台扩展，ADR 0021） | — |
| `unlock` | 限售解禁 | unlock | 个股历史解禁 + 未来待解禁（**万股**） | —（平台扩展，ADR 0022） | — |
| `sector_fund_flow` | 板块资金流 | sector_fund_flow | 板块/概念日级主力净流入（**元**） | —（平台扩展，ADR 0042） | — |
| `news` | 轻量新闻 | news | 个股/板块轻量新闻特征（非 LLM 摘要） | —（平台扩展，ADR 0042） | — |
| `concept_blocks` | 概念板块归属 | concept_blocks | 个股所属行业/概念/地域（BK 码） | —（平台扩展，ADR 0051） | — |

前七项对齐 TSP `CAPABILITY_REGISTRY`；`fund_flow` / `lhb` / `unlock` / `sector_fund_flow` / `news` / `concept_blocks` 为本仓平台扩展，不绑定 TickFlow 套餐文案。

本仓 **不绑定** TickFlow 套餐文案；上表档位仅作迁入 TSP 时的对照。新 Provider（如 `astock_http`）用自身 `usable` 探测，不继承套餐词。

## 路由规则（与 TSP 一致）

1. **每能力独立选源**：禁止 `same_as_daily` 隐式跟随（复权与日 K 一致性靠校验告警，不做路由耦合）。
2. **candidates**：只含「当前确实可提供该能力」的源；未就绪源进 `pending` 并带原因。
3. **usable**：生效源是否真能提供该能力。页面门控只看 `usable`，不看供应商营销档位。
4. **fail-closed**：缺能力 → 明确错误/引导配置；禁止静默换错源。
5. **通用路径禁止硬编码品牌**；专属能力在矩阵标注 `exclusive: true`。
6. **指数特例（产品级）**：核心宽基指数可作为固定合约，**不强制**进入用户可改的路由矩阵；自定义源可另实现 `get_realtime_indices`。细节在 M2 工作台 ADR 敲定。

## `usable` 探测形状（M0.2 冻结文字契约）

运行时（M1/M2）实现须满足：

```text
CapabilityStatus {
  id: string           # 七项之一
  preferred: string    # 用户选择的 provider id
  effective: string | null
  usable: bool
  candidates: [{ name, display, kind, available, status, note? }]
  pending:    [{ name, display, reason }]
}
```

- 同步库：`build_capability_matrix(preferences) -> list[CapabilityStatus]`
- HTTP（工作台）：`GET /api/settings/capability-matrix` 返回同上（字段名稳定）

## Provider 槽位（规划）

| Provider ID | 来源 | 阶段 | 预期 datasets |
|-------------|------|------|----------------|
| `replay` | fixtures | **M1.2 已实现**；**M15–M23** + **M41** + **M-D3**（含套价 `apply_adjust`） | daily, realtime, adj_factor, minute, depth5, financial, full_minute, fund_flow, lhb, unlock, sector_fund_flow, news, concept_blocks（CN） |
| `astock_http` | a-stock-data 配方 | **M8.1 已实现**；**M15–M23** + **M41** + **M-D3**（`full_minute`/板块资金流/新闻/概念板块经 `em_get`；adj_factor/financial 新浪；套价纯函数） | daily, realtime, adj_factor, minute, depth5, financial, full_minute, fund_flow, lhb, unlock, sector_fund_flow, news, concept_blocks |
| `tushare_http` | Tushare 兼容 HTTP | **v3.10.0**（ADR 0048）；补充源，非生产默认 | daily（首切片）；`trade_cal` helper |
| `global_replay` | fixtures | **M5.3 已实现** | daily, realtime（US/HK） |
| `global_http` | Yahoo + 新浪（Skill 配方） | **M9.1 已实现**；美港 `financial` 等见 [M-D5](../ops/m-d5-global-thin-gap.md)（暂缓） | daily, realtime（US/HK） |
| `tickflow` | TSP 内置 | M2 | 按档位 |
| `yaml_custom` | 用户 YAML | M2 | 声明集 |

运行时：`stock_platform_providers.build_capability_matrix` / `register_builtin_providers`。

## 全市场按日截面方法（S2-P1，非路由能力）

`astock_http` 另有三个**全市场**按日方法，供影子链 S2 快照（[`../plans/s2-event-theme-data.md`](../plans/s2-event-theme-data.md) §S2-P1、ADR [0093](../architecture/0093-multi-strategy-shadow-board.md) 增补）使用。它们**不**进入上表能力清单与 `build_capability_matrix` 路由，不影响 `usable` 探测；调用方直接持有 `AStockHttpProvider`。

| 方法 | 对应数据集口径 | 端点（均经 `em_get`） | 单位 | PIT 可回放性 |
|------|----------------|------------------------|------|--------------|
| `get_lhb_daily(trade_date)` | `lhb`（全市场日榜） | datacenter-web `RPT_DAILYBILLBOARD_DETAILSNEW`，`TRADE_DATE=asof`，分页（默认 500×4） | 金额**元**；`change_pct`/`turnover_rate` **小数** | **可回放**：按交易日过滤；盘后公布，只能用于 asof 次日入场 |
| `get_unlock_calendar(start, end)` | `unlock`（全市场日程） | datacenter-web `RPT_LIFT_STAGE`，`start ≤ FREE_DATE ≤ end`，分页 | 股数**万股**；`ratio` **小数**（占流通股） | **有前视风险**：取当前公告日程，日程修订后不可严格回放；**仅作软排除** |
| `get_board_rank(kind)` | `sector_fund_flow`（排名截面） | push2 `clist`，`fs=m:90+t:3`（概念）/ `m:90+t:2`（行业），按 `f62` 排序，单页 ≤100 | `main_net` **元**；`change_pct` **小数** | **不可回放**：vendor 当前快照，无日期参数；仅当 `updated_at` 日期 == asof 时有效（`pitOk`），否则 `stale` 不用 |

返回含 `truncated`（分页上限截断）/ `updated_at`（板块排名）供调用方判定；fail-closed 由调用方处理（S2 快照 fail-soft 记 `sources.*.status`）。

## 补充行情库（ADR 0095，非路由能力）

`stock_platform_providers.aux_market` 经 `em_get` 拉 push2his `kline/get`（`klt=101`、`fqt=0`），写平台自有 `local/aux_market/aux_market.db`。**不**进入上表能力清单与 `build_capability_matrix` 路由，不影响 `usable` 探测。

| 方法 | 内容 | secid | 校验 | 单位 |
|------|------|-------|------|------|
| 指数日线 | `000300` / `000905` / `000852` / `000016` / `399006` | 指数表：`1.000xxx`、`0.399xxx`（**不**用个股 `em_secid`） | `data.code` 一致 + `data.name` 命中指数别名，否则拒写 | OHLC 原始价；`vol` 手；`amount` 元；`pct_chg` 小数 |
| 个股 OHLC | 调用方传入代码列表（默认不全市场） | `em_secid` | `data.code` 一致 | 同上 |

每日逻辑请求预算 `STOCK_PLATFORM_AUX_MARKET_EM_BUDGET`（默认 60）；单代码失败 fail-soft。

## 插件失败隔离

加载失败不得拖垮未启用插件的主流程；失败源不得出现在该能力的 `candidates` 正向列表（可进 `pending`）。

## 已关闭的原 TBD

| 原问题 | 决定 |
|--------|------|
| `usable` 形状 | 上文 `CapabilityStatus`；双入口（库函数 + HTTP）字段一致 |
| 指数是否出矩阵 | 核心指数可为产品固定合约；其余走 `asset_type=index` + 能力路由 |

## 参考

- tick-stock-panel：`backend/app/data_providers/capabilities.py`
- tick-stock-panel：`CONTRIBUTING.md` 数据源插件化章节
