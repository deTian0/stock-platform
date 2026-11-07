# 午间休盘简报（midday session）

> 状态：**已落地（ADR [`0096`](../architecture/0096-midday-digest-session.md) Accepted）**  
> 口径：SIMULATE；东财只经 `em_get`；不写 market.db；`local/` 产物不入库。  
> 触发：用户自建 11:30；平台只提供手动 CLI。

## 0. 目标与非目标

### 目标

- 第三份展示会话 `midday`：文件 `{reportDay}-midday.md`。
- 行情列 = 开盘 / **现价** / 涨跌；现价来自当日分钟线最后一根（`em_get`），限候选池。
- ValidateSet：`pre` | `post` | `midday`。

### 非目标

- 不装 schtask / 不改调度 XML。
- 不改评分、picks、命中、绩效、同花顺生产导出语义。
- 不把 midday 当作新的 hit session_type。

## 1. CLI

```powershell
stock-platform-digest --session midday --run-date 2026-11-07
# 可选：--asof <T-1> --out-dir local/digests --no-ths
```

缺 `--run-date` 且 payload 无 `runDate` → 行情列 `—`，备注「未提供运行日」。禁止用 `date.today()` 猜测。

## 1.1 手动触发（推荐；不装 schtask）

平台**不**注册 11:30 计划任务（ADR 0096）。交易日午间休盘由用户自触发：

```powershell
cd <repo-root>
# 优先 .venv
$py = if (Test-Path .\.venv\Scripts\python.exe) { .\.venv\Scripts\python.exe } else { "python" }
# 报告日 = 今天的日历日（与盘前/盘后 digest 的 reportDay 对齐）
$day = Get-Date -Format "yyyy-MM-dd"
stock-platform-digest --session midday --run-date $day
```

若入口脚本不在 PATH，等价：

```powershell
& $py -m stock_platform_research.daily_digest_cli --session midday --run-date $day
```


产物（默认 `data/digests/`，可用 `--out-dir`）：

| 文件 | 说明 |
|------|------|
| `{reportDay}-midday.md` / `.html` | 午间正文 |
| `latest-midday.*` | 最近一次 midday 指针 |
| `{reportDay}.md` / `latest.md` | 「最后一次成功渲染」别名（可能被 midday 覆盖） |

**不删除**同日 `-pre` / `-post`。东财分钟现价只经 `em_get`，仅候选池；失败三列 `—`，digest 仍成功。

可选自建触发（用户侧，非仓库制品）：Windows 任务计划 / 手机闹钟提醒后手跑上述命令。仓库 XML / `Register-ScheduledTasks.ps1` **不含** midday。

## 2. 验收

- [x] ADR 0096 + 本计划登记
- [x] CLI / 库函数接受 `midday`；非法 session 回落 `pre`
- [x] 写出 `{reportDay}-midday.md`，不删 `-pre`/`-post`
- [x] 注入假分钟源时表头为「现价」，涨跌相对 asof 前收规则与盘后同源（`resolve_prev_close`）
- [x] 真实网络失败 fail-soft（三列 —）
- [x] 单测零公网；`check_docs` 含 ADR 0096

## 3. 修订

| 日期 | 说明 |
|------|------|
| 2026-11-07 | 立项 + ADR Accepted；通宵迭代实现 |
| 2026-11-07 | 补 §1.1 手动触发步骤与产物表；明确不装 schtask |
