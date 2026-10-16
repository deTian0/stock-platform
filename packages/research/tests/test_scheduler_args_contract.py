"""Canonical scheduled-args contract (ADR 0079).

The 2026-10-14 sample loss had a single root cause that is **not** in Python: the
pre-market task's canonical arguments lived in three separate places
(``stock-platform-daily.xml``, ``Invoke-ScheduledRun.ps1``'s ``TASK_PRESETS``,
``Register-ScheduledTasks.ps1``'s header) and only one of them needed the missing
switch for the defect to hide. A pipeline-level fix would not have caught it, and
a human "did you remember?" review did not either.

So the flags are pinned here instead. These tests read the PowerShell/XML
artifacts as text — no PowerShell execution, no scheduler dependency.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

WRAPPER = REPO_ROOT / "scripts" / "ops" / "Invoke-ScheduledRun.ps1"
DAILY_XML = REPO_ROOT / "scripts" / "ops" / "stock-platform-daily.xml"
POSTMARKET_XML = REPO_ROOT / "scripts" / "ops" / "stock-platform-postmarket.xml"
REGISTER = REPO_ROOT / "scripts" / "ops" / "Register-ScheduledTasks.ps1"
OPS_LEDGER_DOC = REPO_ROOT / "docs" / "contracts" / "ops-ledger.md"
SCHEDULER_DOC = REPO_ROOT / "docs" / "ops" / "scheduler.md"
CHECK_DOCS = REPO_ROOT / "scripts" / "check_docs.ps1"
ADR_0079 = REPO_ROOT / "docs" / "architecture" / "0079-settle-after-on-premarket.md"

#: Switches both daily runs must carry. ``-SettleAfter`` is the one that regressed:
#: without it the run never writes the performance JSONL, so a missed post-market
#: run loses that ``asof`` for good (both tasks share the same T-1 ``asof``).
REQUIRED_SWITCHES = ("-MarketDb", "-PrevSession", "-SettleAfter", "-Digest")

#: Pre-ADR-0079 pre-market args. Nowhere in a live artifact may this survive —
#: it is the exact string whose absence-of-a-switch caused the loss. Historical
#: records (CHANGELOG, handoff docs) are allowed to keep it.
STALE_DAILY_ARGS = "-MarketDb -PrevSession -Digest"


def _preset_args(task: str) -> str:
    """Extract ``Args = '...'`` for ``task`` from the wrapper's preset table."""
    text = WRAPPER.read_text(encoding="utf-8")
    block = re.search(rf"'{task}'\s*=\s*@\{{(?P<body>.*?)\}}", text, re.S)
    assert block, f"no TASK_PRESETS block for {task!r} in {WRAPPER.name}"
    args = re.search(r"Args\s*=\s*'([^']*)'", block.group("body"))
    assert args, f"no Args entry in the {task!r} preset"
    return args.group(1).strip()


def _task_arguments(xml_path: Path) -> str:
    """Extract the ``<Arguments>`` payload a scheduled task actually executes."""
    text = xml_path.read_text(encoding="utf-8")
    m = re.search(r"<Arguments>(?P<args>[^<]*)</Arguments>", text)
    assert m, f"no <Arguments> element in {xml_path.name}"
    return m.group("args").strip()


def test_required_switches_present_on_both_runs() -> None:
    for task in ("daily", "postmarket"):
        args = _preset_args(task)
        for switch in REQUIRED_SWITCHES:
            assert switch in args.split(), f"{task} preset is missing {switch}: {args!r}"


def test_xml_matches_wrapper_preset() -> None:
    """The registered task and the ledger wrapper must not drift apart."""
    for task, xml_path in (("daily", DAILY_XML), ("postmarket", POSTMARKET_XML)):
        executed = _task_arguments(xml_path)
        preset = _preset_args(task)
        for switch in preset.split():
            assert switch in executed.split(), (
                f"{xml_path.name} does not execute the {task} preset switch "
                f"{switch!r} (xml={executed!r}, preset={preset!r})"
            )


def test_register_header_documents_the_settle_switch() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    m = re.search(r"stock-platform-daily\.xml.*?\(08:30,\s*(?P<args>[^)]*)\)", text)
    assert m, "Register-ScheduledTasks.ps1 header no longer documents the daily args"
    documented = m.group("args")
    for switch in REQUIRED_SWITCHES:
        assert switch in documented, f"header omits {switch}: {documented!r}"


def test_live_artifacts_carry_no_stale_daily_args() -> None:
    for path in (WRAPPER, DAILY_XML, REGISTER, OPS_LEDGER_DOC, SCHEDULER_DOC):
        text = path.read_text(encoding="utf-8")
        assert STALE_DAILY_ARGS not in text, (
            f"{path.name} still documents/executes the pre-0079 daily args "
            f"({STALE_DAILY_ARGS!r}); add -SettleAfter"
        )


@pytest.mark.parametrize("path", [ADR_0079])
def test_adr_is_recorded_and_indexed(path: Path) -> None:
    assert path.is_file(), f"missing ADR {path.name}"
    assert "0079" in CHECK_DOCS.read_text(encoding="utf-8"), "ADR 0079 not in check_docs.ps1"
