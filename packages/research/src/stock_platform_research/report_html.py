"""Zero-dependency markdown -> HTML renderer carrying the platform report theme.

Why this module exists
----------------------
The platform's reports (daily digest, sweep items) are authored as **markdown**
because that is what agents and diffs read best. Humans, however, want the styled
HTML the repo already ships: the hand-maintained templates under
``apps/workbench/src/stock_platform_workbench/static/report-templates/*.html``
(dark surfaces, gold accent bar, and the **Chinese market convention:
red = up, green = down**).

Rather than let each producer invent its own CSS, the look lives here once:

  - ``LOCAL_THEME`` mirrors those templates (token-for-token for the shared
    colors); ``test_report_html.py`` asserts the two never drift.
  - ``PLAIN_THEME`` is a light, print-friendly fallback.

Design constraints (deliberate):

  - **No third-party dependency.** ``markdown`` / ``jinja2`` are not installed in
    this environment and must not become a requirement.
  - **Fail-open.** Odd markdown degrades to escaped text; rendering never raises
    and never emits unescaped user text.
  - **Pure.** No file or network access outside the thin ``render_markdown_file``
    convenience wrapper.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "DISCLAIMER",
    "LOCAL_THEME",
    "PLAIN_THEME",
    "THEMES",
    "markdown_to_body",
    "render_markdown_file",
    "render_report_html",
]

DISCLAIMER = (
    "本报告由 stock-platform 自动生成，属研究简报，不构成投资建议；"
    "环境 SIMULATE（liveTradingEnabled 恒为 false）。股市有风险，投资需谨慎。"
)

# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------
# LOCAL_THEME is the report-template look. The :root token block is byte-identical
# to a-share-preopen.html / a-share-intraday.html / us-preopen.html so a single
# edit to the palette propagates by copy; a test guards the sync.
LOCAL_THEME = """
:root{
  --bg:#0b0e14; --panel:#131823; --panel-2:#1a2130; --border:#232c3d;
  --text:#e6edf7; --text-dim:#8b96ab; --accent:#4d8dff;
  --gold:#f5c451; --warn:#ff9c2e; --up:#ff4d4f; --down:#00b578;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;
  font-variant-numeric:tabular-nums;line-height:1.7;-webkit-font-smoothing:antialiased;padding:24px 16px}
.wrap{max-width:1080px;margin:0 auto}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--text-dim)}
.hero{background:linear-gradient(135deg,#131c2e 0%,#0d1220 100%);border:1px solid var(--border);
  border-radius:16px;padding:24px;margin-bottom:18px;position:relative;overflow:hidden}
.hero::after{content:'';position:absolute;left:0;right:0;bottom:0;height:2px;
  background:linear-gradient(90deg,var(--accent),transparent)}
.hero-tag{display:inline-block;font-size:12px;letter-spacing:2px;color:var(--gold);
  border:1px solid rgba(245,196,81,.35);border-radius:20px;padding:2px 12px;margin-bottom:10px}
.hero h1{font-size:25px;font-weight:700;letter-spacing:.5px;margin-bottom:6px}
.hero-date{font-size:13px;color:var(--text-dim)}
.hero-note{margin-top:14px;background:rgba(77,141,255,.08);border-left:3px solid var(--accent);
  border-radius:0 8px 8px 0;padding:10px 14px;font-size:13.5px;color:var(--text-dim)}
.block{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:22px 24px}
.block>*:first-child{margin-top:0}
h1,h2,h3,h4,h5,h6{font-weight:600;line-height:1.4}
h2{font-size:17px;margin:26px 0 12px;padding-left:12px;position:relative}
h2::before{content:'';position:absolute;left:0;top:4px;bottom:4px;width:3px;
  background:var(--accent);border-radius:2px}
h3{font-size:15px;margin:20px 0 8px;color:#cdd8ea}
h4,h5,h6{font-size:13.5px;margin:16px 0 6px;color:var(--text-dim)}
p{font-size:13.5px;margin:8px 0}
ul,ol{margin:8px 0 8px 20px}
li{font-size:13.5px;margin:4px 0}
strong{color:#fff}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
hr{border:none;border-top:1px solid var(--border);margin:20px 0}
code{background:var(--panel-2);border:1px solid var(--border);border-radius:5px;padding:1px 5px;
  font-size:12.5px;font-family:"Cascadia Code",Consolas,ui-monospace,monospace;color:#c8d6ea}
pre{background:#0e131c;border:1px solid var(--border);border-radius:10px;padding:12px 14px;overflow:auto;margin:12px 0}
pre code{background:none;border:none;padding:0;color:#b9c6da}
blockquote{border-left:3px solid var(--border);margin:10px 0;padding:2px 14px;color:var(--text-dim);
  background:rgba(255,255,255,.02);border-radius:0 8px 8px 0}
table{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0;border:1px solid var(--border);
  border-radius:10px;overflow:hidden}
th{text-align:left;font-weight:500;color:var(--text-dim);font-size:12px;padding:8px 10px;
  border-bottom:1px solid var(--border);white-space:nowrap;background:var(--panel-2)}
td{padding:8px 10px;border-bottom:1px solid rgba(35,44,61,.6);vertical-align:top;
  white-space:normal;word-break:break-word}
tr:last-child td{border-bottom:none}
tbody tr:nth-child(even) td{background:rgba(255,255,255,.015)}
footer{margin-top:18px;padding-top:14px;border-top:1px solid var(--border);text-align:center}
footer .src{font-size:12px;color:var(--text-dim);margin-bottom:6px}
footer .disclaimer{font-size:12px;color:#6b7689}
@media(max-width:640px){
  body{padding:14px 10px} .hero{padding:18px 16px} .hero h1{font-size:20px}
  .block{padding:16px 14px} table{font-size:12px}
}
@media print{
  body{background:#fff;color:#111;padding:0} .hero{background:#f3f5f9;border:1px solid #ddd}
  .block{background:#fff;border:1px solid #ddd} th{background:#f3f5f9}
  th{color:#555} h3{color:#333} code{background:#f3f5f9;color:#111}
  footer .disclaimer{color:#666}
}
"""

# PLAIN_THEME: light, printable, zero styling assumptions.
PLAIN_THEME = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
 background:#f7f8fa;color:#1f2328;margin:0;padding:28px 20px;line-height:1.6}
.wrap{max-width:1080px;margin:0 auto;background:#fff;border:1px solid #e3e6ea;
 border-radius:12px;padding:28px 34px}
.hero{border-bottom:2px solid #eceff3;padding-bottom:12px;margin-bottom:8px}
.hero-tag{display:inline-block;font-size:12px;color:#57606a;border:1px solid #d0d7de;
 border-radius:10px;padding:1px 8px;margin-bottom:8px}
.hero h1{font-size:24px;margin:0 0 6px}
.hero-date{font-size:13px;color:#57606a}
.hero-note{margin-top:10px;background:#f6f8fa;border-left:3px solid #d0d7de;padding:8px 12px;
 font-size:13px;color:#57606a;border-radius:0 6px 6px 0}
h2{font-size:19px;margin-top:26px;border-bottom:1px solid #f0f2f5;padding-bottom:6px}
h3{font-size:16px;margin-top:20px}
h4,h5,h6{font-size:14px;margin-top:16px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13px}
th,td{border:1px solid #e3e6ea;padding:6px 10px;text-align:left;vertical-align:top;
 white-space:normal;word-break:break-word}
th{background:#f2f4f7;font-weight:600}
tr:nth-child(even) td{background:#fafbfc}
code{background:#f2f4f7;border-radius:4px;padding:1px 5px;font-size:12px}
pre{background:#f6f8fa;border:1px solid #e3e6ea;border-radius:8px;padding:12px;overflow:auto}
pre code{background:none;padding:0}
blockquote{border-left:4px solid #d6dbe1;margin:10px 0;padding:2px 14px;color:#4b5563;background:#fbfcfd}
hr{border:none;border-top:1px solid #eceff3;margin:22px 0}
a{color:#0969da}
.up{color:#c5221f} .down{color:#0a7d43} .flat{color:#57606a}
footer{margin-top:22px;padding-top:16px;border-top:1px solid #eceff3;text-align:center}
footer .src,footer .disclaimer{font-size:12px;color:#6b7689;margin:3px 0}
"""

THEMES: dict[str, str] = {"local": LOCAL_THEME, "plain": PLAIN_THEME}

# ---------------------------------------------------------------------------
# inline + block rendering
# ---------------------------------------------------------------------------
_SIGN_RE = re.compile(r"(?<![\w>])([+\-\u2212]\d+(?:\.\d+)?%)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_FENCE_RE = re.compile(r"^\s*```")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
_QUOTE_RE = re.compile(r"^\s*>\s?")
_UL_RE = re.compile(r"^\s*[-*]\s+")
_OL_RE = re.compile(r"^\s*\d+\.\s+")
_BULLET_STRIP_RE = re.compile(r"^\s*[-*]\s+")
_OL_STRIP_RE = re.compile(r"^\s*\d+\.\s+")


def _colorize(match: re.Match[str]) -> str:
    token = match.group(1)
    cls = "up" if token[0] == "+" else "down"
    return f'<span class="{cls}">{token}</span>'


def _inline(text: str, *, colorize: bool = True) -> str:
    """Inline markdown -> HTML. Input is escaped first, so no raw HTML survives."""
    s = html.escape(text)
    s = re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    s = _LINK_RE.sub(r'<a href="\2">\1</a>', s)
    if colorize:
        s = _SIGN_RE.sub(_colorize, s)
    return s


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def markdown_to_body(md: str, *, colorize: bool = True) -> str:
    """Render a markdown document body to an HTML fragment (no <html> wrapper)."""
    lines = str(md or "").splitlines()
    n = len(lines)
    out: list[str] = []
    i = 0
    while i < n:
        line = lines[i]
        if _FENCE_RE.match(line):
            i += 1
            buf: list[str] = []
            while i < n and not _FENCE_RE.match(lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue
        m = _HEADING_RE.match(line)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2), colorize=colorize)}</h{lvl}>")
            i += 1
            continue
        if _RULE_RE.match(line):
            out.append("<hr/>")
            i += 1
            continue
        if (
            line.strip().startswith("|")
            and i + 1 < n
            and _TABLE_SEP_RE.match(lines[i + 1])
            and "-" in lines[i + 1]
        ):
            header = _split_row(line)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            head = "".join(f"<th>{_inline(c, colorize=colorize)}</th>" for c in header)
            body = "".join(
                "<tr>" + "".join(f"<td>{_inline(c, colorize=colorize)}</td>" for c in r) + "</tr>"
                for r in rows
            )
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue
        if _QUOTE_RE.match(line):
            buf = []
            while i < n and _QUOTE_RE.match(lines[i]):
                buf.append(_QUOTE_RE.sub("", lines[i]))
                i += 1
            out.append("<blockquote>" + markdown_to_body("\n".join(buf), colorize=colorize) + "</blockquote>")
            continue
        if _UL_RE.match(line):
            buf = []
            while i < n and _UL_RE.match(lines[i]):
                buf.append(_BULLET_STRIP_RE.sub("", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(b, colorize=colorize)}</li>" for b in buf) + "</ul>")
            continue
        if _OL_RE.match(line):
            buf = []
            while i < n and _OL_RE.match(lines[i]):
                buf.append(_OL_STRIP_RE.sub("", lines[i]))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(b, colorize=colorize)}</li>" for b in buf) + "</ol>")
            continue
        if not line.strip():
            i += 1
            continue
        out.append("<p>" + _inline(line, colorize=colorize) + "</p>")
        i += 1
    return "\n".join(out)


# ---------------------------------------------------------------------------
# document
# ---------------------------------------------------------------------------
def _default_subtitle(generated_at: str | None) -> str:
    stamp = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"生成时间 {stamp} · 环境 SIMULATE"


def render_report_html(
    md: str,
    *,
    title: str,
    subtitle: str | None = None,
    source: str | None = None,
    badge: str = "REPORT",
    theme: str = "local",
    generated_at: str | None = None,
    colorize: bool = True,
    note: str | None = None,
    disclaimer: str | None = None,
    strip_leading_h1: bool = False,
) -> str:
    """Wrap a markdown document in the platform report shell (hero + block + footer).

    ``theme`` selects :data:`THEMES` (unknown names fall back to ``local``), so a
    caller can never crash on a bad theme name.
    """
    css = THEMES.get(str(theme or "local").lower(), LOCAL_THEME)
    safe_title = html.escape(str(title or "report"))
    sub = html.escape(subtitle or _default_subtitle(generated_at))
    src = html.escape(
        source or "数据来源：stock-platform 权威存储（SQLite brief 仓库 / market.db，只读）"
    )
    note_html = f'<div class="hero-note">{_inline(note, colorize=colorize)}</div>' if note else ""
    foot = html.escape(disclaimer or DISCLAIMER)
    body_md = md
    if strip_leading_h1:
        # The hero already owns the page H1. Drop the digest title, and demote any
        # later standalone `# ` (hit-tracking report, etc.) so the page has one H1.
        lines = str(md or "").splitlines()
        if lines and lines[0].startswith("# ") and not lines[0].startswith("# " * 2):
            lines = lines[1:]
        demoted: list[str] = []
        for line in lines:
            if line.startswith("# ") and not line.startswith("## "):
                demoted.append("#" + line)
            else:
                demoted.append(line)
        body_md = "\n".join(demoted)
    body = markdown_to_body(body_md, colorize=colorize)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{safe_title}</title>\n<style>{css}</style>\n</head>\n<body>\n"
        '<div class="wrap">\n'
        '<header class="hero">\n'
        f'<div class="hero-tag">{html.escape(str(badge))}</div>\n'
        f"<h1>{safe_title}</h1>\n"
        f'<div class="hero-date">{sub}</div>\n'
        f"{note_html}\n"
        "</header>\n"
        f'<main class="block">\n{body}\n</main>\n'
        "<footer>\n"
        f'<p class="src">{src}</p>\n'
        f'<p class="disclaimer">{foot}</p>\n'
        "</footer>\n"
        "</div>\n</body>\n</html>\n"
    )


def render_markdown_file(
    src: str | Path,
    dst: str | Path | None = None,
    *,
    title: str | None = None,
    **kwargs: Any,
) -> Path:
    """Render ``src`` (.md) into ``dst`` (.html). Default dst swaps the suffix."""
    src_path = Path(src)
    text = src_path.read_text(encoding="utf-8-sig")
    out = Path(dst) if dst is not None else src_path.with_suffix(".html")
    if title is None:
        first = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("#")), None)
        title = first or src_path.stem
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report_html(text, title=title, **kwargs), encoding="utf-8")
    return out


def _today() -> str:  # pragma: no cover - trivial
    return date.today().isoformat()
