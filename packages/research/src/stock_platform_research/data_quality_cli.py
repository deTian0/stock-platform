"""CLI ``stock-platform-data-quality`` — zero-network RO scan of market.db."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .data_quality import collect_data_quality, render_data_quality_markdown
from .dotenv import load_dotenv
from .loop_health import default_loop_health_dir


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        prog="stock-platform-data-quality",
        description="只读体检 market.db 数据质量（零网络；退出码恒 0）。",
    )
    p.add_argument("--asof", default=None, help="锚点日 YYYY-MM-DD（默认今天）")
    p.add_argument("--market-db", default=None, help="引擎 market.db 路径")
    p.add_argument("--lookback-days", type=int, default=None, help="回看自然日（默认 60）")
    p.add_argument("--sample-codes", type=int, default=None, help="尺度检查抽样码数")
    p.add_argument("--benchmark", default=None, help="声明基准裸码")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="报告目录（默认 loop-health 同目录）",
    )
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="Markdown 路径")
    p.add_argument("--no-write", action="store_true", help="只打印，不落盘")
    args = p.parse_args(argv)

    kwargs: dict = {}
    if args.lookback_days is not None:
        kwargs["lookback_days"] = args.lookback_days
    if args.sample_codes is not None:
        kwargs["sample_codes"] = args.sample_codes

    payload = collect_data_quality(
        market_db=args.market_db,
        asof=args.asof,
        benchmark=args.benchmark,
        **kwargs,
    )
    md = render_data_quality_markdown(payload)
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if not args.no_write:
        out_dir = args.out_dir or default_loop_health_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.json_out or (out_dir / "data_quality.json")
        md_path = args.out or (out_dir / "data_quality.md")
        json_path.write_text(text, encoding="utf-8")
        md_path.write_text(md, encoding="utf-8")
        print(f"[data-quality] json={json_path}", file=sys.stderr)
        print(f"[data-quality] md={md_path}", file=sys.stderr)
    elif args.json_out or args.out:
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(text, encoding="utf-8")
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(md, encoding="utf-8")

    print(md)
    print(
        f"data-quality status={payload.get('status')} checks={len(payload.get('checks') or [])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
