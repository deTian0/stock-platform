# 现行快照

> 日期：2026-11-05  
> 版本：`v4.13.7`（tag `v4.13.7`；工作区含未提交的 F1 + LLM 提供商改动，**累计后再打 tag**）  
> 工作区：F1（ADR [`0090`](architecture/0090-benchmark-identity-and-sh-fund-prefix.md)）+ T3（ADR [`0091`](architecture/0091-data-quality-scan.md)）+ A1（`debate`/`paper` CLI + [`ops/cli-catalog.md`](ops/cli-catalog.md)）+ LLM 提供商（ADR [`0089`](architecture/0089-llm-provider-selection.md)）；侧车 ADR [`0088`](architecture/0088-llm-sidecar-package-boundary.md)。`local/` 见 [`ops/local-runtime.md`](ops/local-runtime.md)。**累计后再打 tag**。  
> 这是**现在**读仓库的入口。历史里程碑叙事留在 [`ROADMAP.md`](ROADMAP.md) 与 [`plans/trading-system-roadmap.md`](plans/trading-system-roadmap.md) 的修订记录里，不要从那些旧焦点段开工。

## 文档放哪

正式正文只在 `docs/`。按用途分目录，不把 ADR、契约、运维和计划摊成一堆。

| 位置 | 放什么 | 不放什么 |
|------|--------|----------|
| [`docs/`](README.md) | 产品文档 SSOT | 密钥、行情缓存、SQLite |
| 仓库根 `README.md` / `AGENTS.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | 给人、给代理、给发版脚本的入口 | 里程碑正文 |
| `packages/*/README.md`、`apps/workbench/README.md` | 该包怎么装、硬约束 | 全仓路线图 |
| [`archive/`](archive/README.md) | 已经落地的交接，文中「下一块砖」作废 | 现行计划 |

`.cursor/plans` 若出现，只留指向本目录的短链，不写第二份正文。

## 自有线

| 域 | 状态 |
|----|------|
| G / B / S / X / C | 收官 |
| R | R1–R4 done。**R5** ETF 进宇宙未做：`market.db` 的 ETF 日线要生产侧回补，平台只读 |
| T | T1、T2 done。**T3** 代码已落（`data_quality` + CLI + `loop_health.dataQuality`）；发版目标仍 **`v4.14.0`**（累计后再打 tag） |
| Y | Y1 采纳闸门、Y3 负收益归因 done。**Y2** 落档必须等人工签核；没有 `adopt` 证据不改生产默认档 |
| L | L1 立项 `Accepted`（华宝、1 万、Phase 0 纯模拟）。L2/L3 与实盘红线仍关闭 |

下一组里程碑与技术方案：[`plans/next-milestones-t3-cli-y2-fix-r5.md`](plans/next-milestones-t3-cli-y2-fix-r5.md)。

建议顺序：F1 / T3 / A1 代码已落（不打小 tag）→ 累计发版 **`v4.14.0`**；下一刀 **Y2**（须人工签核）或 **R5-P**（ETF 平台侧形状，不写 `market.db`）。

## v4.13 已落地

- **v4.13.0** 简报盘前/盘后分线、②A/②B 双 profile 二次精选、③B 详解
- **v4.13.1–.3** 报告日文件名、同花顺导入块与 txt 对齐
- **v4.13.4–.6** 盘后开/收/涨跌：东财分批重试 → 腾讯/新浪 → westock 第四源
- **v4.13.7** 体检 `briefDue`：修掉每晚「brief 落后 1 日」的假阳性；裁决 `ok` 时报告只留一行结论

## LLM 边界（现行）

- **确定性主链**（默认、无 key）：`research` 日更 / digest / 回测 / attribution / adoption / 绩效；`agents` 研报·复盘·`engine=off|deterministic` 辩论；执行 SIMULATE。
- **LLM 提供商**（ADR [`0089`](architecture/0089-llm-provider-selection.md)，运维 [`ops/llm-providers.md`](ops/llm-providers.md)）：`STOCK_PLATFORM_LLM_PROVIDER` 默认 **`workbuddy`**（进程内不打商业 LLM；数据用 workbuddy bridge）。生产 LLM 选 **`deepseek`**，只用 `DEEPSEEK_*`；或 `openai` 兼容栈。另需 `STOCK_PLATFORM_LLM_DEBATE=1` + `[llm]` extra。
- **可选 LLM 侧车**：`stock_platform_agents.llm`；CLI `--debate-engine llm`；API `engine=llm` / `/api/debate/status` / deep-graph。
- **不变量**：辩论判决不进 brief / picks 账本 / 命中 / 绩效（ADR 0065 测试锁）。

## 已记账缺陷

- （F1 已收口）`exchange_prefix("588080")` → `sh`；基准身份碰撞 → alpha unavailable（ADR 0090）
- （已收口）默认运行时目录改为 `local/`；根 `conftest.py` 扩大守卫，单包 pytest 也不应再写生产 `local/` / `data/`

执行层仍是 SIMULATE，`liveTradingEnabled=false`。空库可跑 `stock-platform-init` 写入可改配置行（不打开实盘）。
