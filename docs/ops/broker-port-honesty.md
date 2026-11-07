# BrokerPort / ths_sim 诚实性说明（M-E3）

> **状态**：done（2026-09-22）  
> **默认**：`STOCK_PLATFORM_BROKER=paper` + **SIMULATE**；`liveTradingEnabled=false`。  
> **M-E4（实盘 / 真实券商 HTTP）**：路线图门禁，**未立项，禁止开工**。

## 三档语义（勿混用）

| 档位 | 含义 | 如何开启 | 是否生产就绪 |
|------|------|----------|--------------|
| **paper（默认）** | 内部 `PaperLedger` 纸面 | 无需配置 / `STOCK_PLATFORM_BROKER=paper` | 日用纸面路径 |
| **ths_sim + mock** | 同花顺模拟**适配器**的内存/fixtures 传输 | `STOCK_PLATFORM_BROKER=ths_sim`（`THS_MODE` 默认 mock） | CI / 演示 E2E；**非**真实券商 |
| **ths_sim + experimental** | HTTP 扩展点；缺 URL/TOKEN **fail-closed** | `STOCK_PLATFORM_THS_MODE=experimental` + BASE_URL + TOKEN | **未接真实零售模拟盘 API**；不宣称可用 |

## 明确未接

- 同花顺零售「模拟盘」稳定公开 HTTP API（调研结论：无；见 ADR 0037）。
- 任何实盘券商 SDK / OpenD / Futu。
- UI「一键实盘」开关（禁止）。
- 桌面客户端 UI 自动化 / 本地同花顺进程钩子（本仓**无** pywinauto / uiautomation 等实现；SIMULATE 边界内也不伪造成交）。

## mock 路径（可跑通、非真实成交）

```powershell
$env:STOCK_PLATFORM_BROKER = "ths_sim"
$env:STOCK_PLATFORM_THS_MODE = "mock"   # 可省略，默认即 mock
# 不要设 BASE_URL / TOKEN（mock 不读）
# 走 workbench / Phase D E2E：authenticate → build_draft → execute → positions / account
```

预期：`liveTradingEnabled=false`；成交来自 `MockThsTransport` 内存/fixtures。试跑日志可落 `local/ths_sim_trial/`（**不入库**）。

## 接真实模拟盘还缺什么（无新凭据则停）

| 缺项 | 说明 |
|------|------|
| `STOCK_PLATFORM_THS_BASE_URL` | 稳定、文档化的同花顺**模拟盘** HTTP 根地址（目前无公开零售 API） |
| `STOCK_PLATFORM_THS_TOKEN`（或等价鉴权） | 可注入 transport 的凭证；禁止提交 git |
| `STOCK_PLATFORM_THS_MODE=experimental` | 缺 URL/TOKEN → **fail-closed**，不静默降级 mock |
| 可实现的 place / positions 契约 | `ExperimentalThsHttpTransport` 对下单等仍 `pending`（注入测试替身除外） |

在以上齐备之前：**只宣称 mock 成功**；不得把 experimental 写成「已接通同花顺」。无凭据时不要伪造 fill。

## 文档与代码须一致的用词

- 写 **mock**：仅 fixtures / 内存。
- 写 **experimental**：扩展点，pending，非生产。
- 写 **未接真实**：不要写成「已支持同花顺交易」。
- `ExternalSimBroker` / `ThsSimBroker` = 模拟路径端口，**≠** 实盘。

## 交叉链

- ADR [0036 BrokerPort](../architecture/0036-broker-port.md)
- ADR [0037 ths_sim](../architecture/0037-ths-sim-broker.md)
- ADR [0038 ths_sim gates](../architecture/0038-ths-sim-gates.md)
- [`packages/execution/README.md`](../../packages/execution/README.md)
- 能力域路线图 **M-E4 仍 Later 门禁**
