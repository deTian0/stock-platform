"""CLI ``stock-platform-ops-ledger``: 调度执行台账（只读汇总 · 或追加一条执行记录）。

两种用法：:

    # ① 读取 + 汇总（默认）：写 ./data/health/ops_ledger.{json,md,html}
    stock-platform-ops-ledger
    stock-platform-ops-ledger --no-write          # 只打印
    stock-platform-ops-ledger --ledger D:/tmp/runs.jsonl --recent 20

    # ② 追加一条执行记录（由调度包装器调用；**退出码恒 0**，绝不拖垮被调度的任务）
    stock-platform-ops-ledger --record --task daily --exit-code 0 \\
        --started-at 2026-10-14T08:30:00+08:00 --ended-at 2026-10-14T08:30:12+08:00 --asof 2026-10-13

唯一**写**动作是向平台自有 ``data/logs/runs.jsonl`` 追加一行（T2 / v4.9.1，见 ADR 0076）；
``market.db`` 与平台库一律只读。

读模式退出码：**0 恒成立**（台账是观测面，不是门禁）；判定读 ``failingTasks`` 即可。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .dotenv import load_dotenv
from .loop_health import DEFAULT_LOOP_HEALTH_OUT_DIR
from .ops_ledger import (
    DEFAULT_OPS_LEDGER_OUT_DIR,
    DEFAULT_RUNS_RECENT,
    OPS_LEDGER_FILENAME,
    collect_ops_ledger,
    default_ops_ledger_path,
    record_run,
    render_ops_ledger_markdown,
)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        description="调度执行台账：汇总计划任务的执行痕迹（只读），或追加一条执行记录"
    )
    p.add_argument("--ledger", type=Path, default=None,
                   help=f"台账路径（默认 {DEFAULT_OPS_LEDGER_OUT_DIR}/{OPS_LEDGER_FILENAME}）")
    p.add_argument("--recent", type=int, default=DEFAULT_RUNS_RECENT,
                   help=f"汇总里保留最近多少次执行（默认 {DEFAULT_RUNS_RECENT}）")
    p.add_argument("--out-dir", type=Path, default=None,
                   help=f"报告输出目录（默认 {DEFAULT_LOOP_HEALTH_OUT_DIR}）")
    p.add_argument("--json-out", type=Path, help="覆盖 JSON 输出路径")
    p.add_argument("--out", type=Path, help="覆盖 Markdown 输出路径")
    p.add_argument("--html-out", type=Path, help="覆盖 HTML 输出路径")
    p.add_argument("--no-write", action="store_true", help="只打印，不写文件")
    p.add_argument("--json", action="store_true", help="打印 JSON 而不是 Markdown")

    rec = p.add_argument_group("record", "追加一条执行记录（--record 时生效）")
    rec.add_argument("--record", action="store_true", help="追加一条执行记录后退出")
    rec.add_argument("--task", default=None, help="任务名（daily / postmarket / marketdb-backfill）")
    rec.add_argument("--exit-code", type=int, default=0, help="被调度脚本的退出码")
    rec.add_argument("--started-at", default=None, help="开始时刻（ISO8601）")
    rec.add_argument("--ended-at", default=None, help="结束时刻（ISO8601）")
    rec.add_argument("--planned-at", default=None, help="计划时刻（ISO8601 或 HH:MM）")
    rec.add_argument("--duration-sec", type=float, default=None, help="耗时（秒）")
    rec.add_argument("--asof", default=None, help="本次执行针对的交易日 YYYY-MM-DD")
    rec.add_argument("--note", default=None, help="备注")
    args = p.parse_args(argv)

    ledger_path = args.ledger or default_ops_ledger_path()

    if args.record:
        if not args.task:
            print("ops-ledger --record 需要 --task", file=sys.stderr)
            return 0  # 记录失败绝不影响被调度的任务
        note = record_run(
            task=args.task,
            exit_code=args.exit_code,
            started_at=args.started_at,
            ended_at=args.ended_at,
            planned_at=args.planned_at,
            duration_sec=args.duration_sec,
            asof=args.asof,
            note=args.note,
            path=ledger_path,
        )
        print(
            "ops-ledger record task={t} exit={e} recorded={r} path={p}{why}".format(
                t=args.task,
                e=args.exit_code,
                r=note.get("recorded"),
                p=note.get("path"),
                why="" if note.get("recorded") else f" reason={note.get('reason')}",
            ),
            file=sys.stderr,
        )
        return 0

    payload = collect_ops_ledger(path=ledger_path, recent_limit=int(args.recent))
    md = render_ops_ledger_markdown(payload)

    if not args.no_write:
        out_dir = args.out_dir or Path(DEFAULT_LOOP_HEALTH_OUT_DIR)
        json_path = args.json_out or (out_dir / "ops_ledger.json")
        md_path = args.out or (out_dir / "ops_ledger.md")
        html_path = args.html_out or (out_dir / "ops_ledger.html")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md, encoding="utf-8")
        try:
            from .report_html import render_report_html

            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(
                render_report_html(
                    md,
                    title="调度执行台账（ops ledger）",
                    badge="OPS",
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — HTML 只是可选锦上添花
            pass

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(md)
    print(
        "ops-ledger status={s} totalRuns={n} failing={f}".format(
            s=payload.get("status"),
            n=payload.get("totalRuns"),
            f=payload.get("failingTasks"),
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
