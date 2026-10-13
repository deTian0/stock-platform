"""CLI: render markdown reports into the platform's styled HTML.

Examples::

    stock-platform-report-html --in data/digests/latest.md
    stock-platform-report-html --in report.md --out report.html --title "A4 绩效台账"
    stock-platform-report-html --dir data/reports/2026-10-12 --theme local

The renderer is dependency-free (:mod:`stock_platform_research.report_html`), so
this command works anywhere the research package is importable — including the
scheduled tasks, which never have a browser or a markdown library around.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report_html import THEMES, render_markdown_file


def _convert_dir(directory: Path, **kwargs: object) -> list[Path]:
    written: list[Path] = []
    for md in sorted(directory.glob("*.md")):
        written.append(render_markdown_file(md, title=None, **kwargs))  # type: ignore[arg-type]
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stock-platform-report-html",
        description="Render markdown report(s) into the platform's styled HTML.",
    )
    parser.add_argument("--in", dest="src", default=None, help="Input markdown file")
    parser.add_argument("--dir", dest="directory", default=None, help="Render every *.md in this directory")
    parser.add_argument("--out", dest="dst", default=None, help="Output html path (single-file mode)")
    parser.add_argument("--title", default=None, help="Document title (default: first heading or file stem)")
    parser.add_argument("--subtitle", default=None, help="Hero subtitle line")
    parser.add_argument("--source", default=None, help="Footer source line")
    parser.add_argument("--badge", default="REPORT", help="Hero badge text (default REPORT)")
    parser.add_argument("--theme", default="local", choices=sorted(THEMES), help="Theme name (default local)")
    parser.add_argument("--no-color", dest="colorize", action="store_false", help="Disable red-up/green-down emphasis")
    parser.set_defaults(colorize=True)
    args = parser.parse_args(argv)

    if not args.src and not args.directory:
        parser.error("one of --in or --dir is required")

    common = {
        "subtitle": args.subtitle,
        "source": args.source,
        "badge": args.badge,
        "theme": args.theme,
        "colorize": args.colorize,
    }
    try:
        if args.directory:
            written = _convert_dir(Path(args.directory), **common)
            for path in written:
                print(f"rendered {path}")
            print(f"report-html OK: {len(written)} file(s) from {args.directory}")
            return 0
        out = render_markdown_file(Path(args.src), args.dst, title=args.title, **common)  # type: ignore[arg-type]
    except Exception as exc:  # keep the CLI honest: report, do not traceback
        print(f"report-html failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"report-html OK: {args.src} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
