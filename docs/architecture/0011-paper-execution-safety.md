# ADR 0011：纸面执行安全模型

- 状态：Accepted
- 日期：2026-09-14

## 背景

V2 审查快照暴露信号过期补单、市场态/执行态混淆、草稿误当激活、实盘误开等问题。M6 吸收其**结论与守卫**，不拷贝 Futu SDK。

## 决策

1. 新包 `packages/execution`：broker-free 内核（timing / transactional / profile / lifecycle / paper ledger）。
2. Hard gates：`allowedEnvironment=SIMULATE`，`liveTradingEnabled=False`。
3. 市场字段可推进；执行字段仅在纸面接受订单后 commit。
4. 草稿 → 校验 → **显式**激活；保存草稿 ≠ 激活。
5. `decision_only` 或窗口外 → 订单列表强制清空；已接受 `draftId` 幂等回放。
6. workbench `/api/paper/*` 只暴露纸面路径；禁止 live 开关。

## 不吸收

- 实盘券商、OpenD 凭据、本机账户数据、Futu 费用口径真理化、V3 research 实验入口。

## 后果

- Admission 通过仅表示受控模拟准入，不代表收益已证明。
- CN 交易日历见 ADR 0015；US/HK 见 ADR 0018。纸面默认仍用 CN timing。
