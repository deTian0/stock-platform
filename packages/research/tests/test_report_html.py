"""Tests for the dependency-free markdown -> HTML report renderer (0071).

Two things must hold forever:

1. Rendering is **fail-open and safe** — odd markdown degrades, user text is
   always escaped, and an unknown theme name never raises.
2. The look stays **in sync with the repo's own report templates** — the shared
   colour tokens are asserted against
   ``apps/workbench/.../static/report-templates/a-share-preopen.html`` so the two
   cannot silently drift (skip when the template is absent, e.g. CI installs).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_platform_research.report_html import (
    LOCAL_THEME,
    THEMES,
    markdown_to_body,
    render_markdown_file,
    render_report_html,
)
from stock_platform_research.report_html_cli import main as cli_main

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = (
    REPO_ROOT
    / "apps"
    / "workbench"
    / "src"
    / "stock_platform_workbench"
    / "static"
    / "report-templates"
    / "a-share-preopen.html"
)


def test_body_renders_core_blocks():
    md = "\n".join(
        [
            "# 标题",
            "",
            "段落 **加粗** 与 `code`。",
            "",
            "| A | B |",
            "|---|---|",
            "| 1 | 2 |",
            "",
            "- 一",
            "- 二",
            "",
            "> 引用",
            "",
            "---",
            "",
            "```",
            "raw <b>x</b>",
            "```",
        ]
    )
    body = markdown_to_body(md)
    assert "<h1>标题</h1>" in body
    assert "<strong>加粗</strong>" in body
    assert "<code>code</code>" in body
    assert "<table>" in body and "<th>A</th>" in body and "<td>1</td>" in body
    assert "<ul><li>一</li><li>二</li></ul>" in body
    assert "<blockquote>" in body
    assert "<hr/>" in body
    assert "<pre><code>raw &lt;b&gt;x&lt;/b&gt;</code></pre>" in body


def test_user_text_is_escaped():
    body = markdown_to_body('<script>alert(1)</script> & "x"')
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    assert "&amp;" in body


def test_cn_color_convention_positive_is_red_negative_is_green():
    body = markdown_to_body("| 收益 |\n|---|\n| +90.24% |\n| -17.14% |")
    assert '<span class="up">+90.24%</span>' in body
    assert '<span class="down">-17.14%</span>' in body
    plain = markdown_to_body("+90.24% -17.14%", colorize=False)
    assert "span" not in plain


def test_document_has_hero_block_footer_and_escaped_title():
    doc = render_report_html("# hi", title="每日简报 <x>", badge="DAILY DIGEST")
    assert doc.startswith("<!DOCTYPE html>")
    assert '<div class="hero-tag">DAILY DIGEST</div>' in doc
    assert "<h1>每日简报 &lt;x&gt;</h1>" in doc
    assert '<main class="block">' in doc
    assert '<p class="disclaimer">' in doc
    assert "<html lang=\"zh-CN\">" in doc


def test_unknown_theme_falls_back_to_local():
    doc = render_report_html("x", title="t", theme="does-not-exist")
    assert "--up:#ff4d4f" in doc


def test_local_theme_tokens_match_report_template():
    if not THEMES.get("local"):
        pytest.skip("theme missing")
    if not TEMPLATE.is_file():
        pytest.skip("report template not found (installed-package / CI run)")
    template = TEMPLATE.read_text(encoding="utf-8-sig")
    for token in ("--bg:#0b0e14", "--accent:#4d8dff", "--gold:#f5c451", "--up:#ff4d4f", "--down:#00b578"):
        assert token in template, f"template lost {token}"
        assert token in LOCAL_THEME, f"renderer drifted from template: {token}"


def test_render_markdown_file_and_cli(tmp_path: Path):
    md = tmp_path / "A2_rankings.md"
    md.write_text("# A2 五榜\n\n| 代码 | 名称 |\n|---|---|\n| 000801 | 四川九洲 |\n", encoding="utf-8")
    out = render_markdown_file(md)
    assert out == md.with_suffix(".html") and out.is_file()
    assert "四川九洲" in out.read_text(encoding="utf-8")

    other = tmp_path / "cli.md"
    other.write_text("# CLI 模式\n\n正文\n", encoding="utf-8")
    rc = cli_main(["--in", str(other), "--theme", "local", "--badge", "TEST"])
    assert rc == 0
    html = other.with_suffix(".html").read_text(encoding="utf-8")
    assert "CLI 模式" in html and '<div class="hero-tag">TEST</div>' in html


def test_cli_directory_mode(tmp_path: Path):
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    rc = cli_main(["--dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "a.html").is_file() and (tmp_path / "b.html").is_file()
