"""ops_ledger：调度执行台账单点（T2 / v4.9.1）。

锁定五件事：

1. **唯一写 fail-open** —— 台账写不了也绝不拖垮被调度的任务；
2. **读宽容** —— 缺文件 → ``[]``、坏行跳过；读失败向上抛（由段出口降级）；
3. **摘要纯函数** —— ``summarize_runs`` 只吃行，连续失败语义可穷举；
4. **段出口 fail-closed** —— 台账缺失 → ``unavailable``（**不假装有记录**）；
5. **零库 / 零网络** —— 只碰 ``tmp_path``。

"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_platform_research import ops_ledger as ol
from stock_platform_research.ops_ledger import (
    SECTION_EMPTY,
    SECTION_OK,
    SECTION_UNAVAILABLE,
    collect_ops_ledger,
    default_ops_ledger_dir,
    default_ops_ledger_path,
    read_runs,
    record_run,
    render_ops_ledger_markdown,
    summarize_runs,
    task_label,
    task_planned_at,
)

# ---------------------------------------------------------------------------
# 1. 写：record_run
# ---------------------------------------------------------------------------


def _led(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "runs.jsonl"


def test_record_then_read_roundtrip(tmp_path: Path) -> None:
    led = _led(tmp_path)
    result = record_run(
        task="daily",
        exit_code=0,
        started_at="2026-10-14T08:30:00+08:00",
        ended_at="2026-10-14T08:30:12+08:00",
        duration_sec=12.3456,
        asof="2026-10-13",
        path=led,
    )
    assert result["recorded"] is True
    assert result["path"] == str(led)
    assert result["record"]["exitCode"] == 0
    assert result["record"]["durationSec"] == 12.346  # 四舍五入到 3 位
    assert result["record"]["plannedAt"] == "08:30"  # 未给 → 取登记表

    rows = read_runs(led)
    assert len(rows) == 1
    assert rows[0]["task"] == "daily"
    assert rows[0]["asof"] == "2026-10-13"


def test_record_creates_parent_dir(tmp_path: Path) -> None:
    led = tmp_path / "deep" / "nested" / "runs.jsonl"
    assert not led.parent.exists()
    assert record_run(task="daily", exit_code=0, path=led)["recorded"] is True
    assert led.is_file()


def test_record_empty_task_is_refused_but_not_raised(tmp_path: Path) -> None:
    led = _led(tmp_path)
    result = record_run(task="   ", exit_code=0, path=led)
    assert result["recorded"] is False
    assert "task" in result["reason"]
    assert not led.exists()


def test_record_fail_open_when_target_is_a_directory(tmp_path: Path) -> None:
    """台账路径指向目录（不可追加）→ 返回 recorded=False，**绝不抛**。"""
    bad = tmp_path / "logs"
    bad.mkdir(parents=True, exist_ok=True)  # 目录本身当作文件路径
    result = record_run(task="daily", exit_code=0, path=bad)
    assert result["recorded"] is False
    assert "reason" in result


def test_record_coerces_bad_exit_code(tmp_path: Path) -> None:
    led = _led(tmp_path)
    result = record_run(task="daily", exit_code="not-a-number", path=led)  # type: ignore[arg-type]
    assert result["recorded"] is True
    assert result["record"]["exitCode"] == -1  # 明确哨兵，不静默当 0


def test_record_trims_to_max(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ol, "RUNS_MAX_RECORDS", 3)
    led = _led(tmp_path)
    for i in range(6):
        record_run(task="daily", exit_code=0, ended_at=f"2026-10-0{i + 1}T08:30:00+08:00", path=led)
    rows = read_runs(led)
    assert len(rows) == 3
    assert rows[-1]["endedAt"].startswith("2026-10-06")  # 保留最新的


# ---------------------------------------------------------------------------
# 2. 读：read_runs
# ---------------------------------------------------------------------------


def test_read_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_runs(tmp_path / "nope.jsonl") == []


def test_read_tolerates_junk_lines(tmp_path: Path) -> None:
    led = _led(tmp_path)
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text(
        "\n".join(
            [
                '{"ts":"t1","task":"daily","exitCode":0}',
                "{not json at all}",
                "",
                '{"ts":"t2","exitCode":0}',  # 缺 task → 跳过
                '["array", "not", "object"]',
                '{"ts":"t3","task":"postmarket","exitCode":1}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rows = read_runs(led)
    assert [r["task"] for r in rows] == ["daily", "postmarket"]


# ---------------------------------------------------------------------------
# 3. 摘要：summarize_runs（纯函数）
# ---------------------------------------------------------------------------


def test_summarize_empty_table() -> None:
    out = summarize_runs([])
    assert out["status"] == SECTION_EMPTY
    assert out["totalRuns"] == 0
    assert out["taskCount"] == 0
    assert out["failingTasks"] == []
    assert out["recent"] == []
    assert "reason" in out


@pytest.mark.parametrize(
    ("codes", "expect_streak", "expect_failing"),
    [
        ([0], 0, False),
        ([1], 1, False),  # 1 次可能是偶发抖动
        ([1, 1], 2, True),
        ([1, 1, 1], 3, True),
        ([1, 0], 0, False),  # 最新成功 → 断链
        ([1, 1, 0, 1, 1], 2, True),
        ([0, 1], 1, False),
    ],
)
def test_summarize_failure_streak(
    codes: list[int], expect_streak: int, expect_failing: bool
) -> None:
    records = [
        {"ts": f"2026-10-{i + 1:02d}T18:30:00+08:00", "task": "marketdb-backfill",
         "exitCode": c}
        for i, c in enumerate(codes)
    ]
    out = summarize_runs(records)
    task = out["tasks"][0]
    assert task["failureStreak"] == expect_streak
    assert (out["failingTasks"] == ["marketdb-backfill"]) is expect_failing


def test_summarize_is_pure_table() -> None:
    """同一输入 → 同一输出；且不改动输入。"""
    records = [
        {"ts": "2026-10-13T08:30:00+08:00", "task": "daily", "exitCode": 0,
         "durationSec": 9.0},
        {"ts": "2026-10-14T08:30:00+08:00", "task": "daily", "exitCode": 1,
         "durationSec": 4.5},
    ]
    snapshot = json.dumps(records, ensure_ascii=False, sort_keys=True)
    a = summarize_runs(records)
    b = summarize_runs(records)
    assert a == b
    assert json.dumps(records, ensure_ascii=False, sort_keys=True) == snapshot

    task = a["tasks"][0]
    assert task["runs"] == 2
    assert task["lastRunAt"] == "2026-10-14T08:30:00+08:00"
    assert task["lastExitCode"] == 1
    assert task["lastOk"] is False
    assert task["label"] == "盘前选股"
    assert a["recent"][0]["ts"] == "2026-10-14T08:30:00+08:00"  # 新→旧
    assert a["lastRunAt"] == "2026-10-14T08:30:00+08:00"


def test_summarize_recent_limit() -> None:
    records = [
        {"ts": f"2026-10-{i + 1:02d}T08:30:00+08:00", "task": "daily", "exitCode": 0}
        for i in range(10)
    ]
    out = summarize_runs(records, recent_limit=3)
    assert len(out["recent"]) == 3
    assert out["totalRuns"] == 10  # 计数不受 recent 限制


# ---------------------------------------------------------------------------
# 4. 段出口：collect_ops_ledger（永不抛）
# ---------------------------------------------------------------------------


def test_collect_missing_is_unavailable(tmp_path: Path) -> None:
    out = collect_ops_ledger(path=tmp_path / "nope.jsonl")
    assert out["status"] == SECTION_UNAVAILABLE
    assert "尚无执行台账" in out["reason"]


def test_collect_empty_file_is_empty(tmp_path: Path) -> None:
    led = _led(tmp_path)
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text("\n", encoding="utf-8")
    out = collect_ops_ledger(path=led)
    assert out["status"] == SECTION_EMPTY
    assert out["totalRuns"] == 0


def test_collect_read_failure_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    led = _led(tmp_path)
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text('{"ts":"t","task":"daily","exitCode":0}\n', encoding="utf-8")

    def _boom(*_a, **_k):
        raise OSError("disk on fire")

    monkeypatch.setattr(ol, "read_runs", _boom)
    out = collect_ops_ledger(path=led)
    assert out["status"] == SECTION_UNAVAILABLE
    assert "disk on fire" in out["reason"]


def test_collect_ok_and_failing(tmp_path: Path) -> None:
    led = _led(tmp_path)
    record_run(task="daily", exit_code=0, path=led)
    record_run(task="marketdb-backfill", exit_code=3, path=led)
    record_run(task="marketdb-backfill", exit_code=3, path=led)
    out = collect_ops_ledger(path=led)
    assert out["status"] == SECTION_OK
    assert out["path"] == str(led)
    assert out["totalRuns"] == 3
    assert out["failingTasks"] == ["marketdb-backfill"]


# ---------------------------------------------------------------------------
# 5. 目录解析 + 登记表
# ---------------------------------------------------------------------------


def test_default_dir_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_OPS_LEDGER_DIR", str(tmp_path / "custom"))
    assert default_ops_ledger_dir() == tmp_path / "custom"
    assert default_ops_ledger_path() == tmp_path / "custom" / "runs.jsonl"


def test_default_dir_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_OPS_LEDGER_DIR", raising=False)
    assert default_ops_ledger_dir() == Path("./data/logs")


def test_task_label_unknown_passes_through() -> None:
    assert task_label("daily") == "盘前选股"
    assert task_label("brand-new-task") == "brand-new-task"
    assert task_label("") == "—"
    assert task_planned_at("postmarket") == "15:30"
    assert task_planned_at("brand-new-task") is None


# ---------------------------------------------------------------------------
# 6. 渲染
# ---------------------------------------------------------------------------


def test_render_ok_warns_on_failing(tmp_path: Path) -> None:
    led = _led(tmp_path)
    record_run(task="marketdb-backfill", exit_code=1, path=led)
    record_run(task="marketdb-backfill", exit_code=1, path=led)
    md = render_ops_ledger_markdown(collect_ops_ledger(path=led))
    assert "# 调度执行台账" in md
    assert "连续失败" in md
    assert "## 逐任务" in md
    assert "**2**" in md


def test_render_unavailable_branch(tmp_path: Path) -> None:
    md = render_ops_ledger_markdown(collect_ops_ledger(path=tmp_path / "nope.jsonl"))
    assert "台账不可用" in md


def test_render_empty_branch(tmp_path: Path) -> None:
    md = render_ops_ledger_markdown(summarize_runs([]))
    assert "尚无执行记录" in md


# ---------------------------------------------------------------------------
# 7. CLI
# ---------------------------------------------------------------------------


def test_cli_record_returns_zero_and_writes(tmp_path: Path) -> None:
    from stock_platform_research.ops_ledger_cli import main

    led = _led(tmp_path)
    rc = main(["--record", "--task", "daily", "--exit-code", "0", "--ledger", str(led)])
    assert rc == 0
    assert len(read_runs(led)) == 1


def test_cli_record_without_task_is_quiet_zero(tmp_path: Path) -> None:
    from stock_platform_research.ops_ledger_cli import main

    led = _led(tmp_path)
    assert main(["--record", "--ledger", str(led)]) == 0
    assert not led.exists()


def test_cli_read_writes_reports(tmp_path: Path) -> None:
    from stock_platform_research.ops_ledger_cli import main

    led = _led(tmp_path)
    record_run(task="daily", exit_code=0, path=led)
    out_dir = tmp_path / "health"
    rc = main(["--ledger", str(led), "--out-dir", str(out_dir)])
    assert rc == 0
    assert (out_dir / "ops_ledger.json").is_file()
    assert (out_dir / "ops_ledger.md").is_file()
    assert "调度执行台账" in (out_dir / "ops_ledger.md").read_text(encoding="utf-8")


def test_cli_read_no_write(tmp_path: Path) -> None:
    from stock_platform_research.ops_ledger_cli import main

    out_dir = tmp_path / "health"
    rc = main(["--ledger", str(tmp_path / "nope.jsonl"), "--no-write", "--out-dir", str(out_dir)])
    assert rc == 0
    assert not out_dir.exists()
