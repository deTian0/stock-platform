# LLM 提供商（workbuddy / DeepSeek / OpenAI 兼容）

> 配套 ADR [`0089`](../architecture/0089-llm-provider-selection.md)。执行层仍是 SIMULATE。

## 选择

| `STOCK_PLATFORM_LLM_PROVIDER` | 含义 |
|-------------------------------|------|
| **`workbuddy`（默认）** | 进程内不调用商业 LLM。行情走 workbuddy；LLM 如需进程内调用请改 `deepseek` 或 `openai`。 |
| `deepseek` | 全部 in-process LLM 走 **`DEEPSEEK_*`** |
| `openai` | OpenAI 兼容 HTTP（`OPENAI_*` / `STOCK_PLATFORM_LLM_*`） |

另需 `STOCK_PLATFORM_LLM_DEBATE=1`，并 `pip install 'stock-platform-agents[llm]'`。

## DeepSeek（推荐生产 LLM）

```powershell
$env:STOCK_PLATFORM_PROVIDER_PRESET = "workbuddy"   # 数据仍用 workbuddy
$env:STOCK_PLATFORM_LLM_PROVIDER = "deepseek"
$env:STOCK_PLATFORM_LLM_DEBATE = "1"
$env:DEEPSEEK_API_KEY = "<key>"
# 可选：
# $env:DEEPSEEK_BASE_URL = "https://api.deepseek.com"
# $env:DEEPSEEK_MODEL = "deepseek-chat"
# $env:DEEPSEEK_VISION_ENABLED = "0"
# $env:DEEPSEEK_VISION_MODEL = "deepseek-vl"
# $env:DEEPSEEK_TIMEOUT = "60"
# $env:DEEPSEEK_MAX_TOKENS = "2048"

stock-platform-workbuddy-bridge --symbols sh600519 --limit 60
stock-platform-daily --provider workbuddy --debate-engine llm --debate-max-picks 1
```

`DEEPSEEK_*` 与 `OPENAI_*` **互不回落**：选了 deepseek 却只配了 `OPENAI_API_KEY` → fail-closed。

## workbuddy 默认

```powershell
# 不设 STOCK_PLATFORM_LLM_PROVIDER 时即为 workbuddy
stock-platform-workbuddy-bridge --symbols sh600519 --limit 60
stock-platform-daily --provider workbuddy --debate-engine off
```

`--debate-engine llm` 在 provider=`workbuddy` 时会按 `STOCK_PLATFORM_LLM_FALLBACK` 降级确定性或 fail-closed，**不会**偷偷打 DeepSeek。

## 状态自检

Workbench：`GET /api/debate/status`（字段含 `provider` / `model` / `baseUrl` / `visionEnabled` / `reasons`，无密钥）。

Python：

```python
from stock_platform_agents.llm import llm_debate_status, llm_provider_status
print(llm_provider_status())
```
