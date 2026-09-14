# ADR 0040：日用宇宙分层 + 可读推荐理由

- 状态：Accepted
- 日期：2026-09-14

## 背景

Phase A 的宇宙与简报足以演示，但对日用仍偏 demo：fixture 过小、`reason` 仅内部字段串。
需要可配置分层宇宙与对人可读的推荐理由，且 CI 仍用小 fixture、默认 replay。

## 决策

1. **分层宇宙**：`load_universe_tiers` / `load_universe(..., tier=)` 支持
   `core` / `watch` / `full`。扁平 JSON 三层同值。空宇宙仍 `UniverseEmptyError`。
2. **样例**：`fixtures/universe_cn_daily.json`（日用样例）；CI 继续
   `universe_cn_sample.json`。软上限写入 `universe_size_guidance`（不强制截断）+
   `EM_MIN_INTERVAL` 提示。
3. **可读理由**：`build_reasons_for_row` → `reasons[]`（`key` / `summary` / `value`）+
   `reasonSummary`；保留兼容字段 `reason`。
4. **Workbench**：`#recommend` 表展示 `reasonSummary`；默认仍 replay + SIMULATE。
5. **不做**：全市场自动扩容、默认 live、新闻 LLM 摘要、SPA。

## 后果

- 日流水线（M40）可按 tier 选型；运维文档可引用规模与限流预期。
- 旧客户端读 `reason` 仍可用。
