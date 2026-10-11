# `.env` 自动加载契约

> 状态：Accepted｜目标 tag：`v4.1.6`（2026-10-10）
> 关联：`docs/architecture/0066-refresh-throughput-and-env-loading.md`
> 实现：`packages/research/src/stock_platform_research/dotenv.py`

本契约锁定「CLI 如何读取仓库根 `.env`」。解决的真机问题是：`schtasks` 调度的进程**不会**替你 `export` 环境变量，而 `daily_cli._build_provider` 直接读 `os.environ["STOCK_PLATFORM_TUSHARE_TOKEN"]` → 每日自动化**必然**以 `requires STOCK_PLATFORM_TUSHARE_TOKEN` 退出 1。

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
3. 从 `Path(__file__).resolve().parents` 逐级向上查找 `.env`
4. 当前工作目录

**文件不存在不报错**（`load_dotenv` 返回 `{}`）。

## 3. 语义

```python
load_dotenv(path=None, *, override=False, env=None, required=None, force=False) -> dict[str, str]
```

- **默认不覆盖**已存在的进程环境变量（`override=False`）—— 调度器 / CI 显式注入的变量**优先**。
- `override=True` 时以文件为准。
- `env=` 可注入目标映射（默认 `os.environ`），便于测试。
- `required=[...]`：缺失的键 → 抛 `DotenvMissingError`；否则静默。
- 返回值 = **实际应用**的键值映射（未覆盖的不计入）。

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

## 6. 接入点

`load_dotenv()` 是以下 **14 个 CLI** 的 `main()` 首行（`__init__.py` 导出 `find_dotenv_path` / `load_dotenv` / `parse_dotenv_text`）：

`daily_cli` · `refresh_cli` · `backtest_cli` · `brief_cli` · `factors_cli` · `hit_tracking_cli` · `market_universe_cli` · `neutralization_cli` · `performance_cli` · `picks_backtest_cli` · `position_review_cli` · `rankings_cli` · `sensitivity_cli` · `strategy_ab_cli`

## 7. 明确不做

- **不下沉到 `providers` 包**：providers 只做 I/O，不碰开发环境约定。
- **不覆盖已存在的进程变量**：保证 `STOCK_PLATFORM_*` 由调度器显式注入时不被文件改写。
