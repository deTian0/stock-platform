# ADR 0010：MarketStrategy 与美港 Vendor

- 状态：Accepted
- 日期：2026-09-13

## 背景

美港不得套用 A 股 T+1 交易限制与涨跌停板。`global-stock-data` 是 **Skill 文档仓**（实现在 `SKILL.md`），不是可安装 Python 包。

## 决策

1. `MarketStrategy` 表驱动：`CN` / `US` / `HK`（时区、会话、settle、limit）。
2. `normalize_symbol(..., market=)` 分市场；CN 路径继续拒绝港美形态；HK 内部统一 5 位。
3. `GlobalReplayProvider` 仅读 fixtures；`global_http` 注册为 pending。
4. 工作台/回测只依赖 `get_market_strategy`，禁止散落 `if market ==`。
5. **吸收边界**：只取符号规则 + daily/realtime 字段语义；不搬期权/SEC/FINRA/整仓 30+ 端点；不把 Skill 当 pip 依赖。

## 后果

- 节假日日历：CN 见 ADR 0015 静态表；US/HK 仍为工作日 stub。
- 完整全球 HTTP 抓取不进本里程碑；日 K live 时港股优先 Yahoo 配方（见 Skill）。
- `datasets.md` 按 market 分支 volume（手 vs 股）与币种。
