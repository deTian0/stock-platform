# 0071 — 报告 HTML 化：单一渲染器 + 对齐本仓报告模板主题

- Status: Accepted
- Date: 2026-10-13
- Supersedes: —
- Related: ADR 0041（daily pipeline）、ADR 0049（SQLite brief 权威）、
  ADR 0033（绩效口径）、ADR 0070（日常循环自足）

## 背景

平台所有报告都是**先写 Markdown**（digest、五榜、命中、绩效，以及研究侧 21 项跑批产物）：
Markdown 对 agent 与 diff 最友好，但人要看的是**有样式的一页**。仓库里其实已经有这套样式——
手工维护的三份报告模板：

```
apps/workbench/src/stock_platform_workbench/static/report-templates/
  a-share-preopen.html / a-share-intraday.html / us-preopen.html
```

它们定义了本仓的「报告观感」：深色面板 + 金色 accent + **A 股红涨绿跌配色**
（`--up:#ff4d4f` / `--down:#00b578`）+ hero 标题栏 + block 分节 + 页脚免责声明。

问题在于**产出侧没有出口**：

1. 平台**原生没有 Markdown→HTML 路径**（digest / rankings / hits / performance 只写 `.md`；
   intel-report 预填是唯一走模板的原生 HTML 出口）。
2. 报告跑批器（`stock-platform-report-sweep`）此前**自带一份浅色主题渲染器**，与模板观感不一致，
   且它是**私有副本**——两处样式必然漂移。
3. 本机**没有 Markdown 库**（`markdown` / `markdown2` / `mistune` 全缺），
   也不能为了排版引入新依赖（本机 `pip install -e` 会被 safe-delete 拦截，见 ADR 0069 附注）。

## 决策

**把「Markdown→HTML」抽成唯一单点，主题对齐本仓报告模板，并让 digest 默认双格式产出。**

### D1 — 新增零依赖渲染器 `research/report_html.py`

- `markdown_to_body(md)`：标题 / 表格 / 有序无序列表 / 引用 / 代码围栏 / 分隔线 / 行内
  `code`·`**加粗**`·`*斜体*`·链接。**先 `html.escape` 再套标签** ⇒ 用户文本永不产生原始 HTML。
- `render_report_html(md, *, title, subtitle, source, badge, theme, note, ...)`：
  套上 hero（`hero-tag` + `h1` + `hero-date` + 可选 `hero-note`）、`main.block` 正文、
  footer（来源 + 免责声明）。
- `THEMES = {"local": LOCAL_THEME, "plain": PLAIN_THEME}`；**未知主题名回落 `local`，永不抛**。
- `render_markdown_file(src, dst=None, ...)`：`.md → .html`，缺省同名换后缀。
- **不加任何第三方依赖**（仅 stdlib：`html` / `re` / `pathlib` / `datetime`）。
- **fail-open**：畸形 Markdown 退化成转义文本，渲染永不抛异常（报告链不允许因排版中断）。

### D2 — 主题以「本仓模板」为准，并用测试焊死

`LOCAL_THEME` 的 `:root` token 块与 `a-share-preopen.html` 的调色板**逐 token 相同**，
`test_report_html.py::test_local_theme_tokens_match_report_template` 直接读模板文件比对
（模板缺失则 `skip`，CI 不阻塞）。想改配色必须**同时**改模板与主题，否则测试红。

### D3 — A 股配色约定随行内百分比自动着色

`_SIGN_RE` 只匹配**带符号的百分比**（`+90.24%` / `-17.14%` / `−17.14%`），
包成 `<span class="up">` / `<span class="down">`。带 `(?<![\w>])` 反向断言，
避免误吞「`2020-2026`」这类区间；`colorize=False` 可整体关闭。

### D4 — 新增 CLI `stock-platform-report-html`

`--in FILE` 或 `--dir DIR`（整目录 `.md → .html`），另有 `--title/--subtitle/--source/--badge/--theme/--no-color`。
用于「把任意已有报告重渲染成模板样式」，也让**自动化任务无需懂 Python** 即可出 HTML。

### D5 — digest 默认产出 md + html

`build_digest(..., emit_html: bool = False)`（库默认保持旧行为，纯增量），
**CLI 默认开启**并新增 `--no-html` 关闭 ⇒ `Invoke-DailyPipeline.ps1 -Digest` 与两个计划任务
**零改动**即开始同时产出 `{asof}.html` 与 `latest.html`。
返回值新增 `htmlPath` / `latestHtmlPath`（**旧键全部保留**，消费方零迁移）。

### D6 — 跑批器改为调用单点

`stock-platform-report-sweep` 的跑批脚本删掉私有 `_CSS` / `md_to_html`，改 import
`stock_platform_research.report_html`。**样式只有一处定义**。

## 非目标

- **不引入前端框架 / CDN**（沿用 ADR 0064 与 B6 的「零新前端依赖」纪律）。
- **不改 `report-templates/*.html`**：它们是人工预填模板（含 `{{...}}` 占位），
  本次只让**产出侧**向它们的观感对齐。
- **不做原生 HTML 出口的架构改造**：intel-report 预填继续用它自己的模板。

## 后果

- **正向**：调度产出从「只有 md」变成「md + 与模板同观的 html」；`--dir` 可一键重渲染历史报告；
  样式漂移有测试兜底；零新依赖、零网络。
- **代价**：配色/版式改动需**双写**（模板 + `LOCAL_THEME`）；主题只是「观感对齐」，
  不是逐像素复刻——模板里的 `.opp/.risk/.cards` 等预填专用组件不进入通用渲染器。
- **口径**：所有 HTML 页脚固定带研究免责声明；`liveTradingEnabled` 恒 false 的 SIMULATE 声明不变。
