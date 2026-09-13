# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循本仓 [`docs/versioning.md`](docs/versioning.md)。

## [Unreleased]

### Added

- （无）

## [0.4.2] - 2026-09-13

### Added

- M4.2 验收：workbench 个股研报 / 复盘槽位经能力矩阵 `resolve("daily")`
- 路由测试覆盖 historical asof 告警与港股拒绝

## [0.4.1] - 2026-09-13

### Added

- `packages/agents`：`ResearchAgentPlugin` / `ReviewAgentPlugin`（仅经 providers）
- 历史 `asof` 跳过 realtime 护栏；ADR 0009；CI `agents` job
- workbench 预挂 `/api/research/report`、`/api/review/report`（M4.2 验收于 `0.4.2`）

### Notes

- TradingAgents 完整辩论图仍作参考；平台槽位以本插件为准

## [0.4.0] - 2026-09-13

### Added

- **大里程碑 M3 完成**：`packages/research` 选股/回测内核
  - lvrev 评分与入场闸门（迁自 a-stock-engine）
  - PIT long-only（T 信号 / T+1 open）+ 防未来函数
  - 盘前截面批处理 CLI `stock-platform-score`

### Notes

- a-stock-engine 视为参考实现；平台权威评分路径为本包
- 下一步 M4：TradingAgents 研报插件化（去内嵌抓取）

## [0.3.3] - 2026-09-13

### Added

- `score_cross_section_csv` + 控制台入口 `stock-platform-score`（盘前批处理）

## [0.3.2] - 2026-09-13

### Added

- `run_pit_long_only` + `assert_no_lookahead_columns`（信号日/成交日分离）

## [0.3.1] - 2026-09-13

### Added

- `packages/research`：`score_lvrev` / `apply_entry_gates` / `apply_risk_gates`（迁自 a-stock-engine）
- ADR 0008；CI `research` job

## [0.3.0] - 2026-09-13

### Added

- **大里程碑 M2 完成**：工作台最小壳经能力矩阵消费 Provider
  - FastAPI health / matrix / daily / realtime
  - 缺能力 409 fail-closed；禁品牌硬编码
  - API 与 replay 同标的同日口径对齐

### Notes

- 下一步 M3：迁入选股 / PIT 回测内核（lvrev）

## [0.2.3] - 2026-09-13

### Added

- M2.3 验收：同标的同日 API daily 与 `ReplayProvider` 批处理字段对齐测试

## [0.2.2] - 2026-09-13

### Added

- `PUT /api/settings/preferences`；minute/缺能力 **409** fail-closed 护栏
- 路由源码禁止品牌字面量扫描；ADR 0007

## [0.2.1] - 2026-09-13

### Added

- `apps/workbench`：FastAPI 最小壳（health / capability-matrix / daily / realtime）
- minute 缺能力时 409 fail-closed；ADR 0006；CI `workbench` job

## [0.2.0] - 2026-09-13

### Added

- **大里程碑 M1 完成**：可安装 `stock-platform-providers`
  - ticker 归一化与港美拒绝
  - daily/realtime 录制回放契约测试
  - 东财 `em_get` 限流单点 + 能力矩阵注册
  - 文档禁止裸东财 URL

### Notes

- Live HTTP 行情适配仍为 pending（`astock_http`）；下一阶段 M2 接入工作台壳

## [0.1.3] - 2026-09-13

### Added

- `em_get` / `EastmoneyClient`：东财串行限流单点（禁非 EM URL）
- `build_capability_matrix` / `register_builtin_providers`
- `docs/contracts/eastmoney-http.md`、ADR 0005

## [0.1.2] - 2026-09-13

### Added

- `ReplayTransport` / `ReplayProvider`：daily + realtime 录制回放
- `normalize_daily_row` / `normalize_realtime_row` 契约归一化
- ADR 0004；fixtures 与 pytest 覆盖

## [0.1.1] - 2026-09-13

### Added

- `packages/providers`：可安装包 `stock-platform-providers`
- `normalize_symbol` / `exchange_prefix` / `is_bse_symbol` + pytest
- ADR 0003；CI `providers` job（含与根 `VERSION` 对齐校验）

## [0.1.0] - 2026-09-13

### Added

- **大里程碑 M0 完成**：工程架子、契约 Accepted、CI/文档自检、SemVer tag 流程可协作

### Notes

- 仍无可运行行情/选股业务；下一阶段 M1（`v0.2.0`）开始 `packages/providers` 可安装实现

## [0.0.3] - 2026-09-13

### Added

- `scripts/check_docs.ps1`：必选文件、VERSION↔CHANGELOG、Markdown 相对链接检查
- CI：docs 自检 + `release_tag.ps1 -DryRun`

### Changed

- `release_tag.ps1`：`-DryRun` 不再因 tag 已存在或脏工作区失败
- README / versioning：补充 DryRun 与自检示例

## [0.0.2] - 2026-09-13

### Added

- ADR 0002：M0.2 数据集与市场口径冻结
- 契约定稿：`datasets` / `capability-matrix` / `market-strategy`（对齐 TSP）

### Changed

- 关闭 M0.2 关键 TBD（amount 元、ex_factor、asset_type、asof_ts、usable 形状、CN 规则表）

## [0.0.1] - 2026-09-13

### Added

- 仓库骨架：`apps/`、`packages/`、`docs/`、`scripts/`
- 目标架构 ADR、契约草稿、里程碑 ROADMAP、tag 升级规则
- `VERSION` 单一版本源与 `scripts/release_tag.ps1`
- Git 初始化（`main`）与首个工程 tag `v0.0.1`

[Unreleased]: https://github.com/local/stock-platform/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/local/stock-platform/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/local/stock-platform/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/local/stock-platform/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/local/stock-platform/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/local/stock-platform/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/local/stock-platform/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/local/stock-platform/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/local/stock-platform/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/local/stock-platform/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/local/stock-platform/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/local/stock-platform/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/local/stock-platform/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/local/stock-platform/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/local/stock-platform/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/local/stock-platform/compare/v0.0.3...v0.1.0
[0.0.3]: https://github.com/local/stock-platform/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/local/stock-platform/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/local/stock-platform/releases/tag/v0.0.1
