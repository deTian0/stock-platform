"""调度执行台账单点（ops run ledger）—— 「任务到底跑没跑」的只读答案。

背景（T2，v4.9.1）::

    R3 / T1 的 ``loop_health`` 能回答「循环**现在**健不健康」，却回答不了
    「**任务到底跑没跑**」。真机事故（2026-10-13 / 10-14）：``market.db`` 连续两日无 bar、
    brief 停在 ``10-12``；排查**必须离开平台**去翻 Windows 任务计划程序，才发现 18:30 的
    回补任务**压根没注册**。平台内没有任何结构化的「任务执行痕迹」入口
    ⇒「是任务没跑，还是跑了没成」无法自证。

    本模块把**调度执行痕迹**落成一条 append-only 台账（``data/logs/runs.jsonl``），
    并给出一份可机读 / 可人读的汇总：每个任务**最近一次的时刻 / 退出码 / 耗时**、
    **连续失败次数**、以及最近 N 次执行。

写入口（本模块**唯一**的写）

- ``record_run`` —— 由调度包装器 ``scripts/ops/Invoke-ScheduledRun.ps1``
  或 CLI ``stock-platform-ops-ledger --record`` 调用；**fail-open**
  （写不了也绝不拖垮被调度的那个任务）。
- 台账只写平台自有 ``data/``，**绝不写 ``market.db`` 或任何库**（承接 ADR 0058 只读）。

读出口

- ``read_runs`` / ``summarize_runs``（**纯函数**）/ ``collect_ops_ledger``（段形状，
  供 ``loop_health`` 作为一路信号消费）。
- 台账缺失 → ``status="unavailable"``（fail-closed：**不假装有记录**）。

口径（硬约束）

- **零网络**：不发布任何 HTTP 请求。
- **只读行情**：本模块不触碰 ``market.db``。
- **永不抛**（对外入口）：``record_run`` 与 ``collect_ops_ledger`` 都是 total function；
  ``read_runs`` 读失败向上抛（由调用方 fail-closed 降级）。
- **不改口径**：台账只记录事实，不参与选股 / 回测 / 绩效的任何算术。

SIMULATE only. Not investment advice.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

# 台账文件与目录。目录可用 ``STOCK_PLATFORM_OPS_LEDGER_DIR`` 覆盖。
OPS_LEDGER_FILENAME = "runs.jsonl"
ENV_OPS_LEDGER_DIR = "STOCK_PLATFORM_OPS_LEDGER_DIR"
DEFAULT_OPS_LEDGER_OUT_DIR = "./data/logs"
DEFAULT_RUNS_RECENT = 12
RUNS_MAX_RECORDS = 400

# 连续失败到几次算「这个任务坏了」。1 次可能是偶发抖动，2 次就该说出口。
OPERATIONAL_FAILURE_STREAK = 2

# 段 status 词表（与 ``loop_health.SECTION_*`` 同字面量；有测试钉住两者一致，
# 但本模块**不 import loop_health** —— 保持单向依赖，避免循环导入）。
SECTION_OK = "ok"
SECTION_EMPTY = "empty"
SECTION_UNAVAILABLE = "unavailable"

# 已知的调度任务登记表：只用于**展示**（中文名 + 计划时刻），不参与判定。
# 未知任务名不报错 —— 原样展示（台账要能容纳将来新增的任务）。
TASK_SCHEDULES: dict[str, dict[str, str]] = {
    "daily": {"label": "盘前选股", "plannedAt": "08:30"},
    "postmarket": {"label": "盘后台账", "plannedAt": "15:30"},
    "marketdb-backfill": {"label": "行情回补", "plannedAt": "18:30"},
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _error_text(exc: BaseException) -> str:
    cls = type(exc).__name__
    msg = str(exc).strip() or cls
    return f"{cls}: {msg}"[:500]


def default_ops_ledger_dir() -> Path:
    """台账目录：``STOCK_PLATFORM_OPS_LEDGER_DIR`` 优先，否则 ``./data/logs``。"""
    raw = os.environ.get(ENV_OPS_LEDGER_DIR, "").strip()
    return Path(raw) if raw else Path(DEFAULT_OPS_LEDGER_OUT_DIR)


def default_ops_ledger_path() -> Path:
    """默认台账路径（``<dir>/runs.jsonl``）。"""
    return default_ops_ledger_dir() / OPS_LEDGER_FILENAME


def task_label(task: str) -> str:
    """任务的中文展示名；未登记的任务原样返回（不臆造）。"""
    key = str(task or "").strip()
    return TASK_SCHEDULES.get(key, {}).get("label") or key or "—"


def task_planned_at(task: str) -> str | None:
    """登记表里的计划时刻（``HH:MM``）；未登记 → ``None``。"""
    return TASK_SCHEDULES.get(str(task or "").strip(), {}).get("plannedAt")


# --------------------------------------------------------------------------- #
# 写：record_run（唯一写；fail-open）
# --------------------------------------------------------------------------- #
def record_run(
    *,
    task: str,
    exit_code: int,
    started_at: str | None = None,
    ended_at: str | None = None,
    planned_at: str | None = None,
    duration_sec: float | None = None,
    asof: str | None = None,
    note: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """把一次调度执行追加进台账（**fail-open，永不抛**）。

    返回 ``{"recorded": bool, "path": ..., "record": {...}}``；失败时多一个 ``reason``。
    ``task`` 为空 → 直接拒绝（记一条无名记录没有意义），同样以 fail-open 形式返回。
    """
    key = str(task or "").strip()
    p = Path(path) if path is not None else default_ops_ledger_path()
    if not key:
        return {"recorded": False, "path": str(p), "reason": "task 为空，拒绝记录。"}

    try:
        code = int(exit_code)
    except (TypeError, ValueError):
        code = -1

    dur: float | None
    try:
        dur = None if duration_sec is None else round(float(duration_sec), 3)
    except (TypeError, ValueError):
        dur = None

    record: dict[str, Any] = {
        "ts": str(ended_at or _utcnow_iso()),
        "task": key,
        "plannedAt": str(planned_at) if planned_at else task_planned_at(key),
        "startedAt": str(started_at) if started_at else None,
        "endedAt": str(ended_at) if ended_at else None,
        "exitCode": code,
        "durationSec": dur,
        "asof": str(asof)[:10] if asof else None,
        "note": str(note) if note else None,
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        trimmed = _trim(p, RUNS_MAX_RECORDS)
        return {"recorded": True, "path": str(p), "record": record, "trimmed": trimmed}
    except Exception as exc:  # noqa: BLE001 — 台账是锦上添花，绝不拖垮被调度的任务
        return {"recorded": False, "path": str(p), "record": record,
                "reason": _error_text(exc)}


def _trim(path: Path, keep: int) -> int:
    """把台账裁到最近 ``keep`` 行；返回裁掉的行数（失败 → 0）。"""
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) <= keep:
            return 0
        dropped = len(lines) - keep
        path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
        return dropped
    except Exception:  # noqa: BLE001
        return 0


# --------------------------------------------------------------------------- #
# 读：read_runs / summarize_runs（纯函数）
# --------------------------------------------------------------------------- #
def read_runs(path: str | Path | None = None) -> list[dict[str, Any]]:
    """读台账（**文件顺序 = 追加顺序 = 时间序**，最旧在前）。

    文件不存在 → ``[]``；**读失败向上抛**（由调用方 fail-closed 降级）。
    坏行（非 JSON / 缺 ``task``）**跳过而不抛** —— 单行损坏不该让整条台账消失。
    """
    p = Path(path) if path is not None else default_ops_ledger_path()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            rec = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and str(rec.get("task") or "").strip():
            out.append(rec)
    return out


def _has_failed(record: Mapping[str, Any]) -> bool:
    try:
        return int(record.get("exitCode") or 0) != 0
    except (TypeError, ValueError):
        return True


def summarize_runs(
    records: Sequence[Mapping[str, Any]],
    *,
    recent_limit: int = DEFAULT_RUNS_RECENT,
    failure_threshold: int = OPERATIONAL_FAILURE_STREAK,
) -> dict[str, Any]:
    """把台账行卷成汇总（**纯函数**，便于单测与复用）。

    - 每个任务：最近一次的 ``ts`` / ``exitCode`` / ``durationSec`` / ``asof``、
      ``runs`` 次数、**连续失败次数**（从最新往回数）、``lastOk``；
    - ``failingTasks``：连续失败 ≥ ``failure_threshold`` 的任务名（**说出口的那一条**）；
    - ``recent``：最近 ``recent_limit`` 次执行（新→旧）。
    """
    per_task: dict[str, list[Mapping[str, Any]]] = {}
    order: list[str] = []
    for rec in records:
        key = str(rec.get("task") or "").strip()
        if not key:
            continue
        if key not in per_task:
            per_task[key] = []
            order.append(key)
        per_task[key].append(rec)

    tasks: list[dict[str, Any]] = []
    failing: list[str] = []
    for key in order:
        recs = per_task[key]
        streak = 0
        for rec in reversed(recs):
            if _has_failed(rec):
                streak += 1
            else:
                break
        last = recs[-1]
        tasks.append(
            {
                "task": key,
                "label": task_label(key),
                "plannedAt": str(last.get("plannedAt") or task_planned_at(key) or "") or None,
                "runs": len(recs),
                "lastRunAt": str(last.get("ts") or "") or None,
                "lastExitCode": int(last.get("exitCode") or 0),
                "lastOk": not _has_failed(last),
                "lastDurationSec": last.get("durationSec"),
                "lastAsof": str(last.get("asof") or "") or None,
                "failureStreak": streak,
            }
        )
        if streak >= max(1, int(failure_threshold)):
            failing.append(key)

    limit = max(1, int(recent_limit))
    recent: list[dict[str, Any]] = []
    for rec in reversed(records[-limit:]):
        key = str(rec.get("task") or "").strip()
        if not key:
            continue
        recent.append(
            {
                "ts": str(rec.get("ts") or "") or None,
                "task": key,
                "label": task_label(key),
                "exitCode": int(rec.get("exitCode") or 0),
                "ok": not _has_failed(rec),
                "durationSec": rec.get("durationSec"),
                "plannedAt": str(rec.get("plannedAt") or "") or None,
                "asof": str(rec.get("asof") or "") or None,
            }
        )

    last_run_at = max((str(r.get("ts") or "") for r in records), default="") or None
    return {
        "status": SECTION_OK if records else SECTION_EMPTY,
        "totalRuns": len(records),
        "taskCount": len(tasks),
        "tasks": tasks,
        "failingTasks": failing,
        "failureThreshold": max(1, int(failure_threshold)),
        "lastRunAt": last_run_at,
        "recent": recent,
        **({} if records else {"reason": "执行台账为空。"}),
    }


# --------------------------------------------------------------------------- #
# 段形状出口（供 loop_health 消费；永不抛）
# --------------------------------------------------------------------------- #
def collect_ops_ledger(
    *,
    path: str | Path | None = None,
    recent_limit: int = DEFAULT_RUNS_RECENT,
) -> dict[str, Any]:
    """读台账并给出汇总段（**永不抛**）。

    台账缺失 → ``status="unavailable"``（fail-closed：不假装有记录）；
    文件存在但无有效行 → ``status="empty"``；读失败 → ``unavailable`` + ``reason``。
    """
    p = Path(path) if path is not None else default_ops_ledger_path()
    if not p.is_file():
        return {
            "status": SECTION_UNAVAILABLE,
            "path": str(p),
            "reason": "尚无执行台账：首次调度运行（包装器 / CLI --record）后建立。",
        }
    try:
        records = read_runs(p)
    except Exception as exc:  # noqa: BLE001 — 读失败也不抛，交 fail-closed 段
        return {"status": SECTION_UNAVAILABLE, "path": str(p), "reason": _error_text(exc)}
    summary = summarize_runs(records, recent_limit=int(recent_limit))
    summary["path"] = str(p)
    return summary


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
def _cell(value: Any) -> str:
    return "—" if value in (None, "") else str(value)


def _ok_zh(ok: bool) -> str:
    return "✅ 成功" if ok else "⛔ 失败"


def render_ops_ledger_markdown(payload: Mapping[str, Any]) -> str:
    """人读版台账汇总（结论先行、逐任务表格）。"""
    tasks = list(payload.get("tasks") or [])
    failing = list(payload.get("failingTasks") or [])
    lines = [
        "# 调度执行台账（ops ledger）",
        "",
        "- 结论：**{s}**".format(
            s=(
                f"⛔ {len(failing)} 个任务连续失败：{', '.join(failing)}"
                if failing
                else ("✅ 无连续失败" if tasks else "⚠️ 尚无执行记录")
            )
        ),
        "- 台账：`{p}`".format(p=_cell(payload.get("path"))),
        "- 累计：{n} 次执行 · {t} 个任务 · 最近一次 `{ts}`".format(
            n=_cell(payload.get("totalRuns")),
            t=_cell(payload.get("taskCount")),
            ts=_cell(payload.get("lastRunAt")),
        ),
        "",
    ]
    if str(payload.get("status") or "") == SECTION_UNAVAILABLE:
        lines += [f"- ⚠️ 台账不可用：{payload.get('reason')}", ""]
        return "\n".join(lines) + "\n"

    lines += [
        "## 逐任务",
        "",
        "| 任务 | 计划 | 次数 | 最近执行 | 退出码 | 耗时(s) | 连续失败 |",
        "|---|---|---|---|---|---|---|",
    ]
    if not tasks:
        lines.append("| — | — | — | — | — | — | — |")
    for t in tasks:
        streak = int(t.get("failureStreak") or 0)
        lines.append(
            "| {label}（{task}） | {p} | {r} | {ts} | {ec} {z} | {d} | {s} |".format(
                label=_cell(t.get("label")),
                task=_cell(t.get("task")),
                p=_cell(t.get("plannedAt")),
                r=_cell(t.get("runs")),
                ts=_cell(t.get("lastRunAt")),
                ec=_cell(t.get("lastExitCode")),
                z=_ok_zh(bool(t.get("lastOk"))),
                d=_cell(t.get("lastDurationSec")),
                s=(f"**{streak}**" if streak else "0"),
            )
        )
    lines.append("")

    recent = list(payload.get("recent") or [])
    if recent:
        lines += [
            "## 最近执行",
            "",
            "| 时刻 | 任务 | 退出码 | 耗时(s) |",
            "|---|---|---|---|",
        ]
        for r in recent:
            lines.append(
                "| {ts} | {label} | {ec} {z} | {d} |".format(
                    ts=_cell(r.get("ts")),
                    label=_cell(r.get("label")),
                    ec=_cell(r.get("exitCode")),
                    z=_ok_zh(bool(r.get("ok"))),
                    d=_cell(r.get("durationSec")),
                )
            )
        lines.append("")

    lines += [
        "> 说明：台账由调度包装器 `scripts/ops/Invoke-ScheduledRun.ps1`（或 CLI `--record`）"
        "**追加**写入，只记录事实；",
        "> 不参与任何选股 / 回测 / 绩效算术，也不写 `market.db`（T2 / ADR 0076）。",
        "",
    ]
    return "\n".join(lines) + "\n"


__all__ = [
    "DEFAULT_OPS_LEDGER_OUT_DIR",
    "DEFAULT_RUNS_RECENT",
    "ENV_OPS_LEDGER_DIR",
    "OPERATIONAL_FAILURE_STREAK",
    "OPS_LEDGER_FILENAME",
    "RUNS_MAX_RECORDS",
    "SECTION_EMPTY",
    "SECTION_OK",
    "SECTION_UNAVAILABLE",
    "TASK_SCHEDULES",
    "collect_ops_ledger",
    "default_ops_ledger_dir",
    "default_ops_ledger_path",
    "read_runs",
    "record_run",
    "render_ops_ledger_markdown",
    "summarize_runs",
    "task_label",
    "task_planned_at",
]
