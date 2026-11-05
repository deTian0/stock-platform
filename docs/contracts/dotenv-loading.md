# `.env` 自动加载契约

> 状态：Accepted｜目标 tag：`v4.1.6`（2026-10-10）；`local/` 默认路径与 Settings 收口见开源消毒计划实施轮  
> 关联：`docs/architecture/0066-refresh-throughput-and-env-loading.md` · [`docs/ops/local-runtime.md`](../ops/local-runtime.md)  
> 实现：`packages/research/src/stock_platform_research/dotenv.py` · `settings.py`

本契约锁定「CLI / Workbench 如何读取本机 `.env`」。解决的真机问题是：`schtasks` 调度的进程**不会**替你 `export` 环境变量，而 `daily_cli._build_provider` 直接读 `os.environ["STOCK_PLATFORM_TUSHARE_TOKEN"]` → 每日自动化**必然**以 `requires STOCK_PLATFORM_TUSHARE_TOKEN` 退出 1。

---

## 1. 环境变量

| 变量 | 作用 |
|---|---|
| `STOCK_PLATFORM_DOTENV` | 显式指定 `.env` 路径（优先于向上查找） |
| `STOCK_PLATFORM_DOTENV_DISABLE` | 真值 → **禁用隐式加载**（返回空映射） |

## 2. 路径解析优先级

`find_dotenv_path(explicit=None)`：

1. `explicit` 实参
2. `STOCK_PLATFORM_DOTENV`
3. 从 `Path(__file__).resolve().parents` 与 cwd 逐级向上查找 **`local/.env`**
4. 同批向上查找过渡期仓库根 / cwd **`.env`**

**文件不存在不报错**（`load_dotenv` 返回 `{}`）。复制模板：`.env.example` → `local/.env`。

## 3. 语义

```python
load_dotenv(path=None, *, override=False, env=None, required=None, force=False) -> dict[str, str]
```

- **默认不覆盖**已存在的进程环境变量（`override=False`）—— 调度器 / CI 显式注入的变量**优先**。
- `override=True` 时以文件为准。
- `env=` 可注入目标映射（默认 `os.environ`），便于测试。
- `required=[...]`：缺失的键 → 抛 `DotenvMissingError`；否则静默。
- 返回值 = **实际应用**的键值映射（未覆盖的不计入）。

进程入口应先调用 `get_settings()`（会触发 `load_dotenv()`），再读 `os.environ`。  
`liveTradingEnabled` **不进** Settings。

## 4. 解析规则（`parse_dotenv_text`）

- `KEY=VALUE`；忽略空行与 `#` 注释行。
- 容忍 `export KEY=VALUE` 前缀。
- 引号：`'...'` 原样；`"..."` 支持 `\n` / `\"` 反转义；引号内 `#` 不视为注释。
- 非引号值：剥掉行尾 ` #` 之后的**内联注释**。
- 非法行（无 `=`）跳过，不抛错。

## 5. pytest 守卫（**关键**）

当**任一**成立时，隐式加载**跳过**，`load_dotenv()` 返回 `{}`：

- `PYTEST_CURRENT_TEST` 非空
- `PYTEST_VERSION` 非空
- `STOCK_PLATFORM_DOTENV_DISABLE` 为真值

判定实现为 `is_disabled(env=None)` —— 默认读取**真实进程环境** `os.environ`。

**理由**：否则开发者本机真实 `.env`（真实 token / 真实 `market.db` 路径）会泄漏进测试，造成"本机过、CI 挂"或反之。

加载器**自身的测试**用 `force=True` 绕过守卫。

根 `conftest.py` 还会把 DB / 绩效 / health / logs / holdings / proxy 等默认路径重定向到会话临时目录（ADR 0069 / 0070），避免单包或全量 pytest 写入 `local/`。

## 6. 接入点

`load_dotenv()` / `get_settings()` 是 research 各 console script 与 `stock-platform-workbench` 的入口约定。契约初版写「14 个 CLI」是 `v4.1.6` 数字；其后又增加 symbol-master、adoption、attribution、workbuddy-bridge、sameday、day-quote、loop-health、data-quality、ops-ledger、performance-proxy、digest、init，以及 agents 的 `stock-platform-debate`、execution 的 `stock-platform-paper` 等。**命令一览 SSOT：[`docs/ops/cli-catalog.md`](../ops/cli-catalog.md)**（以各包 `pyproject.toml` 的 `[project.scripts]` 为准）。

特别约定：

- `stock-platform-digest` 与 `stock-platform-workbench` 的 `main()` **必须**调用 `get_settings()`，不依赖 bat 注入。
- `stock-platform-score` / `stock-platform-report-html` 只吃文件参数，可不加载。

## 7. 明确不做

- **不下沉到 `providers` 包**：providers 只做 I/O，不碰开发环境约定。
- **不覆盖已存在的进程变量**：保证 `STOCK_PLATFORM_*` 由调度器显式注入时不被文件改写。
- **不**把 `liveTradingEnabled` 做成 `.env` 开关。
