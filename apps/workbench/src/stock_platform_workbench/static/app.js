(function () {
  "use strict";

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function showError(el, err) {
    el.hidden = false;
    el.textContent = formatErrorMessage(err);
  }

  function clearError(el) {
    el.hidden = true;
    el.textContent = "";
  }

  function formatErrorMessage(err) {
    if (err == null) return "请求失败";
    if (typeof err === "string") return err;
    if (typeof err !== "object") return String(err);
    var parts = [];
    if (err.fail_closed) parts.push("能力不可用（fail-closed）");
    if (err.reason) parts.push(String(err.reason));
    if (err.message && err.message !== "request_failed") parts.push(String(err.message));
    if (err.error && typeof err.error === "string") parts.push(err.error);
    if (err.detail && typeof err.detail === "string") parts.push(err.detail);
    else if (err.detail && typeof err.detail === "object") {
      if (err.detail.error) parts.push(String(err.detail.error));
      else if (err.detail.detail && typeof err.detail.detail === "string") {
        parts.push(err.detail.detail);
      }
      if (err.detail.tip) parts.push("提示：" + String(err.detail.tip));
    }
    if (err.tip) parts.push("提示：" + String(err.tip));
    if (err.capability) parts.push("能力=" + err.capability);
    if (err.provider) parts.push("provider=" + err.provider);
    if (err.status) parts.push("HTTP " + err.status);
    if (!parts.length) return JSON.stringify(err, null, 2);
    var head = parts.join(" · ");
    // Prefer Chinese / human tip; avoid dumping FastAPI envelope JSON
    var nestedDetail =
      err.detail && typeof err.detail === "object" && typeof err.detail.detail === "string"
        ? err.detail.detail
        : typeof err.detail === "string"
          ? err.detail
          : null;
    if (nestedDetail && /[\u4e00-\u9fff]/.test(nestedDetail)) {
      var prefix = [];
      if (err.fail_closed) prefix.push("能力不可用（fail-closed）");
      if (err.status) prefix.push("HTTP " + err.status);
      return (prefix.length ? prefix.join(" · ") + "\n" : "") + nestedDetail;
    }
    if (parts.length === 1 && err.detail && typeof err.detail === "string") return err.detail;
    return head + "\n" + JSON.stringify(err, null, 2);
  }

  function formatBriefError(err) {
    var base = formatErrorMessage(err);
    var tip =
      "下一步：检查截面日 asof（最近完整交易日）、宇宙 symbols 是否非空、.env 中 Tushare Token 与 STOCK_PLATFORM_PROVIDER_PRESET；live 场景勿启用 STOCK_PLATFORM_BRIEF_FALLBACK=replay。";
    if (base.indexOf("下一步：") >= 0) return base;
    return base + "\n" + tip;
  }

  function formatScore(score) {
    if (score == null || score === "") return "—";
    var n = Number(score);
    if (Number.isNaN(n)) return escapeHtml(score);
    return n.toFixed(4);
  }

  function dash(value) {
    if (value == null || value === "") return "—";
    return String(value);
  }

  function shortHash(value) {
    if (!value) return "—";
    var s = String(value);
    return s.length > 12 ? s.slice(0, 8) + "…" : s;
  }

  /** Price: 2–4 decimals depending on magnitude. */
  function formatPrice(value) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (Number.isNaN(n)) return String(value);
    var abs = Math.abs(n);
    var digits = abs >= 1000 ? 2 : abs >= 100 ? 2 : abs >= 10 ? 3 : 4;
    return n.toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: digits,
    });
  }

  /** Decimal ratio → percent text, e.g. 0.0106 → +1.06%. */
  function formatPct(value, digits) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (Number.isNaN(n)) return String(value);
    var d = digits == null ? 2 : digits;
    var pct = n * 100;
    var sign = pct > 0 ? "+" : "";
    return sign + pct.toFixed(d) + "%";
  }

  /** Large CNY nets: 亿 / 万 / plain. */
  function formatMoney(value) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (Number.isNaN(n)) return String(value);
    var abs = Math.abs(n);
    var sign = n < 0 ? "-" : "";
    if (abs >= 1e8) return sign + (abs / 1e8).toFixed(2) + "亿";
    if (abs >= 1e4) return sign + (abs / 1e4).toFixed(2) + "万";
    return (
      sign +
      abs.toLocaleString("zh-CN", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      })
    );
  }

  function formatVolume(value) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (Number.isNaN(n)) return String(value);
    if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + "亿";
    if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + "万";
    return n.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  }

  function formatFactor(value) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return n.toLocaleString("zh-CN", {
      minimumFractionDigits: 4,
      maximumFractionDigits: 6,
    });
  }

  function formatSharesWan(value) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) + "万股";
  }

  function formatSentiment(value) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (Number.isNaN(n)) return String(value);
    var sign = n > 0 ? "+" : "";
    return sign + n.toFixed(2);
  }

  function signedClass(value) {
    var n = Number(value);
    if (Number.isNaN(n) || n === 0) return "";
    return n > 0 ? "pos" : "neg";
  }

  function td(text, className) {
    return (
      '<td' +
      (className ? ' class="' + className + '"' : "") +
      ">" +
      escapeHtml(text == null || text === "" ? "—" : String(text)) +
      "</td>"
    );
  }

  function tdNum(text, className) {
    var cls = "num" + (className ? " " + className : "");
    return td(text, cls);
  }

  function setRawJson(elId, data) {
    var el = $(elId);
    if (!el) return;
    el.textContent = data == null ? "" : JSON.stringify(data, null, 2);
  }

  function emptyTable(tbody, colSpan, message) {
    tbody.innerHTML = "";
    var tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML =
      '<td colspan="' +
      colSpan +
      '">' +
      escapeHtml(message || "暂无数据") +
      "</td>";
    tbody.appendChild(tr);
  }

  function marketMeta(provider, rowCount, extra) {
    var parts = ["provider=" + (provider || "—"), "行数=" + (rowCount || 0)];
    if (extra) parts.push(extra);
    return parts.join(" · ");
  }

  function renderKv(el, rows) {
    if (!el) return;
    el.innerHTML = "";
    if (!rows || !rows.length) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    for (var i = 0; i < rows.length; i++) {
      var dt = document.createElement("dt");
      dt.textContent = rows[i][0];
      var dd = document.createElement("dd");
      dd.textContent = rows[i][1] == null || rows[i][1] === "" ? "—" : String(rows[i][1]);
      el.appendChild(dt);
      el.appendChild(dd);
    }
  }

  function renderSteps(el, steps) {
    if (!el) return;
    el.innerHTML = "";
    var names = { refresh: "刷新", brief: "推荐", to_paper: "纸面" };
    (steps || []).forEach(function (s) {
      var li = document.createElement("li");
      var kind = s.ok ? (s.skipped ? "skip" : "ok") : "fail";
      li.className = "step step-" + kind;
      var extra = s.skipped ? "跳过" : s.ok ? "完成" : "失败";
      if (s.pickCount != null) extra += " · " + s.pickCount + " 只";
      if (s.draftId) extra += " · " + shortHash(s.draftId);
      if (s.error) {
        extra += " · " + (typeof s.error === "string" ? s.error : JSON.stringify(s.error));
      }
      li.innerHTML =
        "<strong>" +
        escapeHtml(names[s.step] || s.step) +
        "</strong><span>" +
        escapeHtml(extra) +
        "</span>";
      el.appendChild(li);
    });
  }

  function renderStats(host, items) {
    if (!host) return;
    host.innerHTML = "";
    if (!items || !items.length) {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    items.forEach(function (it) {
      var div = document.createElement("div");
      div.className = "stat";
      div.innerHTML =
        '<div class="lbl">' +
        escapeHtml(it[0]) +
        '</div><div class="val">' +
        escapeHtml(dash(it[1])) +
        "</div>";
      host.appendChild(div);
    });
  }

  function renderDebateView(host, data) {
    if (!host) return;
    if (!data) {
      host.hidden = true;
      host.innerHTML = "";
      return;
    }
    host.hidden = false;
    var score = data.score || {};
    var rounds = data.rounds || [];
    var html =
      '<dl class="kv"><dt>裁决</dt><dd>' +
      escapeHtml(dash(data.verdict)) +
      "</dd><dt>净分</dt><dd>" +
      escapeHtml(dash(score.net)) +
      "</dd><dt>代码</dt><dd>" +
      escapeHtml(dash(data.symbol)) +
      "</dd><dt>asof</dt><dd>" +
      escapeHtml(dash(data.asof)) +
      "</dd></dl>";
    if (rounds.length) {
      html += '<div class="rounds">';
      for (var r = 0; r < rounds.length; r++) {
        var round = rounds[r];
        html +=
          '<article class="round"><h3>' +
          escapeHtml(round.role || "round") +
          "</h3><p>" +
          escapeHtml(round.thesis || "") +
          "</p></article>";
      }
      html += "</div>";
    }
    host.innerHTML = html;
  }

  function markNav() {
    var links = document.querySelectorAll(".ia-nav a");
    var y = window.scrollY + 88;
    var current = null;
    links.forEach(function (a) {
      var id = (a.getAttribute("href") || "").replace(/^#/, "");
      var el = id ? document.getElementById(id) : null;
      if (!el) return;
      var top = el.getBoundingClientRect().top + window.scrollY;
      if (top <= y) current = a;
    });
    links.forEach(function (a) {
      var on = a === current;
      a.classList.toggle("is-active", on);
      if (on) a.setAttribute("aria-current", "location");
      else a.removeAttribute("aria-current");
    });
  }

  function renderRecommendCards(picks, emptyInfo) {
    var host = $("recommend-cards");
    if (!host) return;
    host.innerHTML = "";
    if (!picks || !picks.length) {
      var msg = (emptyInfo && emptyInfo.emptyPicksMessage) || "暂无推荐结果";
      var tip = (emptyInfo && emptyInfo.emptyPicksTip) || "";
      host.innerHTML =
        '<p class="hint" style="margin:0">' +
        escapeHtml(msg) +
        (tip ? "<br/>" + escapeHtml(tip) : "") +
        "</p>";
      return;
    }
    for (var i = 0; i < picks.length; i++) {
      var row = picks[i];
      var card = document.createElement("article");
      card.className = "rec-card";
      var reasons = row.reasons || [];
      var chips = "";
      for (var j = 0; j < reasons.length; j++) {
        var item = reasons[j];
        var label = (item && (item.summary || item.key)) || "";
        if (!label) continue;
        chips += "<li>" + escapeHtml(label) + "</li>";
      }
      if (!chips && (row.reasonSummary || row.reason)) {
        chips = "<li>" + escapeHtml(row.reasonSummary || row.reason) + "</li>";
      }
      card.innerHTML =
        '<div class="rec-card-top">' +
        '<div><span class="rec-rank">#' +
        escapeHtml(row.rank) +
        '</span> <a class="rec-symbol" href="#daily">' +
        escapeHtml(row.symbol) +
        "</a></div>" +
        '<div class="rec-score">' +
        formatScore(row.composite_score) +
        "</div></div>" +
        '<div class="rec-meta"><span>现价 <strong>' +
        escapeHtml(row.close == null ? "—" : formatPrice(row.close)) +
        "</strong></span></div>" +
        '<p class="rec-summary">' +
        escapeHtml(row.reasonSummary || row.reason || "") +
        "</p>" +
        (chips ? '<ul class="reason-list">' + chips + "</ul>" : "");
      host.appendChild(card);
    }
  }

  function openAncestorDetails(el) {
    var node = el;
    while (node && node !== document.body) {
      if (node.tagName === "DETAILS") node.open = true;
      node = node.parentElement;
    }
  }

  function revealHashTarget() {
    var id = (location.hash || "").replace(/^#/, "");
    if (!id) return;
    var target = document.getElementById(id);
    if (!target) return;
    openAncestorDetails(target);
  }

  async function fetchJson(url, options) {
    const res = await fetch(url, options);
    let body = null;
    const text = await res.text();
    try {
      body = text ? JSON.parse(text) : null;
    } catch (_) {
      body = text;
    }
    if (!res.ok) {
      const detail = body && typeof body === "object" ? body : { status: res.status, body: body };
      const err = new Error("request_failed");
      err.status = res.status;
      err.detail = detail;
      throw err;
    }
    return body;
  }

  async function loadMatrix() {
    const errEl = $("matrix-error");
    clearError(errEl);
    try {
      const rows = await fetchJson("/api/settings/capability-matrix");
      const tbody = $("matrix-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          escapeHtml(row.id) +
          "</td><td>" +
          (row.usable
            ? '<span class="pill">可用</span>'
            : '<span class="pill muted">不可用</span>') +
          "</td><td>" +
          escapeHtml(row.effective || "") +
          "</td><td>" +
          escapeHtml(row.label || "") +
          "</td>";
        tbody.appendChild(tr);
      }
      const daily = rows.find(function (r) {
        return r.id === "daily";
      });
      if (daily && daily.effective) {
        $("pref-daily").value = daily.effective;
      }
      const fundFlow = rows.find(function (r) {
        return r.id === "fund_flow";
      });
      if (fundFlow && fundFlow.effective) {
        $("pref-fund-flow").value = fundFlow.effective;
      }
      const sectorFundFlow = rows.find(function (r) {
        return r.id === "sector_fund_flow";
      });
      if (sectorFundFlow && sectorFundFlow.effective) {
        $("pref-sector-fund-flow").value = sectorFundFlow.effective;
      }
      const newsCap = rows.find(function (r) {
        return r.id === "news";
      });
      if (newsCap && newsCap.effective) {
        $("pref-news").value = newsCap.effective;
      }
      const lhb = rows.find(function (r) {
        return r.id === "lhb";
      });
      if (lhb && lhb.effective) {
        $("pref-lhb").value = lhb.effective;
      }
      const unlock = rows.find(function (r) {
        return r.id === "unlock";
      });
      if (unlock && unlock.effective) {
        $("pref-unlock").value = unlock.effective;
      }
      const minute = rows.find(function (r) {
        return r.id === "minute";
      });
      if (minute && minute.effective) {
        $("pref-minute").value = minute.effective;
      }
      const depth5 = rows.find(function (r) {
        return r.id === "depth5";
      });
      if (depth5 && depth5.effective) {
        $("pref-depth5").value = depth5.effective;
      }
      const financial = rows.find(function (r) {
        return r.id === "financial";
      });
      if (financial && financial.effective) {
        $("pref-financial").value = financial.effective;
      }
      const adjFactor = rows.find(function (r) {
        return r.id === "adj_factor";
      });
      if (adjFactor && adjFactor.effective) {
        $("pref-adj-factor").value = adjFactor.effective;
      }
      const fullMinute = rows.find(function (r) {
        return r.id === "full_minute";
      });
      if (fullMinute && fullMinute.effective) {
        $("pref-full-minute").value = fullMinute.effective;
      }
      $("pref-status").textContent =
        "daily=" +
        (daily && daily.effective ? daily.effective : "") +
        " · fund_flow=" +
        (fundFlow && fundFlow.effective ? fundFlow.effective : "") +
        " · sector_fund_flow=" +
        (sectorFundFlow && sectorFundFlow.effective ? sectorFundFlow.effective : "") +
        " · news=" +
        (newsCap && newsCap.effective ? newsCap.effective : "") +
        " · lhb=" +
        (lhb && lhb.effective ? lhb.effective : "") +
        " · unlock=" +
        (unlock && unlock.effective ? unlock.effective : "") +
        " · minute=" +
        (minute && minute.effective ? minute.effective : "") +
        " · depth5=" +
        (depth5 && depth5.effective ? depth5.effective : "") +
        " · financial=" +
        (financial && financial.effective ? financial.effective : "") +
        " · adj_factor=" +
        (adjFactor && adjFactor.effective ? adjFactor.effective : "") +
        " · full_minute=" +
        (fullMinute && fullMinute.effective ? fullMinute.effective : "");
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function applyPreset() {
    const errEl = $("matrix-error");
    clearError(errEl);
    const presetId = $("pref-preset").value;
    try {
      const out = await fetchJson("/api/settings/presets/" + encodeURIComponent(presetId) + "/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      $("pref-status").textContent =
        "preset applied → " +
        out.applied +
        " (startup default still replay; liveTradingEnabled=false)";
      await loadMatrix();
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function applyPreference() {
    const errEl = $("matrix-error");
    clearError(errEl);
    const daily = $("pref-daily").value;
    const fundFlow = $("pref-fund-flow").value;
    const sectorFundFlow = $("pref-sector-fund-flow").value;
    const newsPref = $("pref-news").value;
    const lhb = $("pref-lhb").value;
    const unlock = $("pref-unlock").value;
    const minute = $("pref-minute").value;
    const depth5 = $("pref-depth5").value;
    const financial = $("pref-financial").value;
    const adjFactor = $("pref-adj-factor").value;
    const fullMinute = $("pref-full-minute").value;
    try {
      await fetchJson("/api/settings/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preferences: {
            daily: daily,
            realtime: daily,
            fund_flow: fundFlow,
            sector_fund_flow: sectorFundFlow,
            news: newsPref,
            lhb: lhb,
            unlock: unlock,
            minute: minute,
            depth5: depth5,
            financial: financial,
            adj_factor: adjFactor,
            full_minute: fullMinute,
          },
        }),
      });
      $("pref-status").textContent =
        "preferences updated → daily/realtime=" +
        daily +
        " fund_flow=" +
        fundFlow +
        " sector_fund_flow=" +
        sectorFundFlow +
        " news=" +
        newsPref +
        " lhb=" +
        lhb +
        " unlock=" +
        unlock +
        " minute=" +
        minute +
        " depth5=" +
        depth5 +
        " financial=" +
        financial +
        " adj_factor=" +
        adjFactor;
      await loadMatrix();
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function loadDaily(event) {
    if (event) event.preventDefault();
    const errEl = $("daily-error");
    clearError(errEl);
    $("daily-meta").textContent = "";
    setRawJson("daily-json", null);
    const symbols = $("daily-symbols").value.trim();
    const start = $("daily-start").value;
    const end = $("daily-end").value;
    const params = new URLSearchParams({ symbols: symbols });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const tbody = $("daily-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/daily?" + params.toString());
      const rows = data.rows || [];
      $("daily-meta").textContent = marketMeta(data.provider, rows.length);
      setRawJson("daily-json", data);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 9, "暂无日 K 数据");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.symbol) +
          td(row.date) +
          tdNum(formatPrice(row.open)) +
          tdNum(formatPrice(row.high)) +
          tdNum(formatPrice(row.low)) +
          tdNum(formatPrice(row.close)) +
          tdNum(formatVolume(row.volume)) +
          tdNum(formatMoney(row.amount)) +
          tdNum(formatPct(row.change_pct), signedClass(row.change_pct));
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 9, "查询失败");
      setRawJson("daily-json", null);
    }
  }

  function renderRealtimeCards(rows) {
    var host = $("realtime-cards");
    if (!host) return;
    host.innerHTML = "";
    if (!rows || !rows.length) {
      host.innerHTML = '<p class="empty-hint">暂无实时快照</p>';
      return;
    }
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var card = document.createElement("article");
      card.className = "snap-card";
      var chgCls = signedClass(row.change_pct);
      card.innerHTML =
        '<div class="snap-top"><div><span class="snap-symbol">' +
        escapeHtml(dash(row.symbol)) +
        '</span> <span class="snap-name">' +
        escapeHtml(dash(row.name)) +
        '</span></div><div class="snap-price ' +
        chgCls +
        '">' +
        escapeHtml(formatPrice(row.price)) +
        "</div></div>" +
        '<div class="snap-chg ' +
        chgCls +
        '">' +
        escapeHtml(formatPrice(row.change_amount)) +
        " · " +
        escapeHtml(formatPct(row.change_pct)) +
        "</div>" +
        '<dl class="snap-kv">' +
        "<dt>昨收</dt><dd>" +
        escapeHtml(formatPrice(row.prev_close)) +
        "</dd>" +
        "<dt>成交量</dt><dd>" +
        escapeHtml(formatVolume(row.volume)) +
        "</dd>" +
        "<dt>成交额</dt><dd>" +
        escapeHtml(formatMoney(row.amount)) +
        "</dd>" +
        "<dt>换手</dt><dd>" +
        escapeHtml(formatPct(row.turnover_rate)) +
        "</dd>" +
        "<dt>振幅</dt><dd>" +
        escapeHtml(formatPct(row.amplitude)) +
        "</dd></dl>";
      host.appendChild(card);
    }
  }

  async function loadRealtime(event) {
    if (event) event.preventDefault();
    const errEl = $("realtime-error");
    clearError(errEl);
    $("realtime-meta").textContent = "";
    setRawJson("realtime-json", null);
    const symbols = $("realtime-symbols").value.trim();
    const params = new URLSearchParams({ symbols: symbols });
    const tbody = $("realtime-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/realtime?" + params.toString());
      const rows = data.rows || [];
      $("realtime-meta").textContent = marketMeta(data.provider, rows.length);
      setRawJson("realtime-json", data);
      renderRealtimeCards(rows);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 7, "暂无实时快照");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.symbol) +
          td(row.name) +
          tdNum(formatPrice(row.price), signedClass(row.change_pct)) +
          tdNum(formatPrice(row.change_amount), signedClass(row.change_amount)) +
          tdNum(formatPct(row.change_pct), signedClass(row.change_pct)) +
          tdNum(formatVolume(row.volume)) +
          tdNum(formatMoney(row.amount));
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      renderRealtimeCards([]);
      emptyTable(tbody, 7, "查询失败");
      setRawJson("realtime-json", null);
    }
  }

  async function loadMinute(event) {
    if (event) event.preventDefault();
    const errEl = $("minute-error");
    clearError(errEl);
    $("minute-meta").textContent = "";
    setRawJson("minute-json", null);
    const symbols = $("minute-symbols").value.trim();
    const freq = $("minute-freq").value;
    const start = $("minute-start").value;
    const end = $("minute-end").value;
    const params = new URLSearchParams({ symbols: symbols, freq: freq });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const tbody = $("minute-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/minute?" + params.toString());
      const rows = data.rows || [];
      $("minute-meta").textContent = marketMeta(
        data.provider,
        rows.length,
        "freq=" + (data.freq || freq)
      );
      setRawJson("minute-json", data);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 5, "暂无分钟 K 数据");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.symbol) +
          td(row.datetime) +
          tdNum(formatPrice(row.close)) +
          tdNum(formatVolume(row.volume)) +
          td(row.freq);
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 5, "查询失败");
      setRawJson("minute-json", null);
    }
  }

  async function loadDepth5(event) {
    if (event) event.preventDefault();
    const errEl = $("depth5-error");
    clearError(errEl);
    $("depth5-meta").textContent = "";
    setRawJson("depth5-json", null);
    const symbols = $("depth5-symbols").value.trim();
    const params = new URLSearchParams({ symbols: symbols });
    const tbody = $("depth5-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/depth5?" + params.toString());
      const rows = data.rows || [];
      $("depth5-meta").textContent = marketMeta(data.provider, rows.length);
      setRawJson("depth5-json", data);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 6, "暂无五档盘口");
        return;
      }
      for (const row of rows) {
        for (let i = 0; i < 5; i++) {
          const tr = document.createElement("tr");
          tr.innerHTML =
            td(row.symbol) +
            tdNum(String(i + 1)) +
            tdNum(formatPrice(row.bid_prices ? row.bid_prices[i] : null), "bid") +
            tdNum(formatVolume(row.bid_volumes ? row.bid_volumes[i] : null), "bid") +
            tdNum(formatPrice(row.ask_prices ? row.ask_prices[i] : null), "ask") +
            tdNum(formatVolume(row.ask_volumes ? row.ask_volumes[i] : null), "ask");
          tbody.appendChild(tr);
        }
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 6, "查询失败");
      setRawJson("depth5-json", null);
    }
  }

  async function loadFinancial(event) {
    if (event) event.preventDefault();
    const errEl = $("financial-error");
    clearError(errEl);
    $("financial-meta").textContent = "";
    setRawJson("financial-json", null);
    const symbols = $("financial-symbols").value.trim();
    const periods = $("financial-periods").value.trim() || "8";
    const params = new URLSearchParams({ symbols: symbols, periods: periods });
    const tbody = $("financial-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/financial?" + params.toString());
      const items = data.items || [];
      $("financial-meta").textContent =
        "provider=" + data.provider + " · 标的=" + items.length;
      setRawJson("financial-json", data);
      tbody.innerHTML = "";
      var wrote = false;
      for (const item of items) {
        const income = item.income || [];
        const balance = item.balance || [];
        const cashflow = item.cashflow || [];
        const n = Math.max(income.length, balance.length, cashflow.length, 0);
        for (let i = 0; i < n; i++) {
          wrote = true;
          const inc = income[i] || {};
          const bal = balance[i] || {};
          const cf = cashflow[i] || {};
          const tr = document.createElement("tr");
          tr.innerHTML =
            td(item.symbol) +
            td(inc.period_end || bal.period_end || cf.period_end || "") +
            tdNum(formatMoney(inc.revenue)) +
            tdNum(formatMoney(inc.net_income), signedClass(inc.net_income)) +
            tdNum(formatMoney(bal.total_assets)) +
            tdNum(
              formatMoney(cf.net_operating_cash_flow),
              signedClass(cf.net_operating_cash_flow)
            );
          tbody.appendChild(tr);
        }
      }
      if (!wrote) emptyTable(tbody, 6, "暂无财务报表");
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 6, "查询失败");
      setRawJson("financial-json", null);
    }
  }

  async function loadAdjFactor(event) {
    if (event) event.preventDefault();
    const errEl = $("adj-factor-error");
    clearError(errEl);
    $("adj-factor-meta").textContent = "";
    setRawJson("adj-factor-json", null);
    const symbols = $("adj-factor-symbols").value.trim();
    const kind = $("adj-factor-kind").value || "qfq";
    const params = new URLSearchParams({ symbols: symbols, kind: kind });
    const tbody = $("adj-factor-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/adj-factor?" + params.toString());
      const rows = data.rows || [];
      $("adj-factor-meta").textContent = marketMeta(
        data.provider,
        rows.length,
        "kind=" + data.kind
      );
      setRawJson("adj-factor-json", data);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 3, "暂无复权因子");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.symbol) + td(row.trade_date) + tdNum(formatFactor(row.ex_factor));
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 3, "查询失败");
      setRawJson("adj-factor-json", null);
    }
  }

  async function loadDailyAdjusted(event) {
    if (event) event.preventDefault();
    const errEl = $("daily-adjusted-error");
    clearError(errEl);
    $("daily-adjusted-meta").textContent = "";
    setRawJson("daily-adjusted-json", null);
    const symbols = $("daily-adjusted-symbols").value.trim();
    const kind = $("daily-adjusted-kind").value || "qfq";
    const start = $("daily-adjusted-start").value;
    const end = $("daily-adjusted-end").value;
    const params = new URLSearchParams({ symbols: symbols, kind: kind });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const tbody = $("daily-adjusted-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/daily-adjusted?" + params.toString());
      const rows = data.rows || [];
      const providers = data.providers || {};
      $("daily-adjusted-meta").textContent =
        "daily=" +
        (providers.daily || "") +
        " · adj_factor=" +
        (providers.adj_factor || "") +
        " · kind=" +
        data.kind +
        " · 行数=" +
        rows.length;
      setRawJson("daily-adjusted-json", data);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 5, "暂无复权日 K");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.symbol) +
          td(row.date) +
          tdNum(formatPrice(row.close)) +
          tdNum(formatFactor(row.ex_factor)) +
          td(row.adjust_kind || data.kind);
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 5, "查询失败");
      setRawJson("daily-adjusted-json", null);
    }
  }

  async function loadFullMinute(event) {
    if (event) event.preventDefault();
    const errEl = $("full-minute-error");
    clearError(errEl);
    $("full-minute-meta").textContent = "";
    setRawJson("full-minute-json", null);
    const symbols = $("full-minute-symbols").value.trim();
    const tradeDate = $("full-minute-date").value;
    const count = $("full-minute-count").value || "300";
    const params = new URLSearchParams({ symbols: symbols, count: count });
    if (tradeDate) params.set("trade_date", tradeDate);
    const tbody = $("full-minute-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/full-minute?" + params.toString());
      const rows = data.rows || [];
      $("full-minute-meta").textContent = marketMeta(
        data.provider,
        rows.length,
        "trade_date=" + (data.trade_date || tradeDate || "")
      );
      setRawJson("full-minute-json", data);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 5, "暂无全量分钟");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.symbol) +
          td(row.datetime) +
          tdNum(formatPrice(row.close)) +
          tdNum(formatVolume(row.volume)) +
          td(row.freq);
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 5, "查询失败");
      setRawJson("full-minute-json", null);
    }
  }

  async function loadPaper() {
    const errEl = $("paper-error");
    clearError(errEl);
    try {
      const data = await fetchJson("/api/paper/status");
      $("paper-banner").textContent =
        (data.banner || "") +
        "\nliveTradingEnabled=" +
        String(data.liveTradingEnabled) +
        "\nenvironment=" +
        (data.allowedEnvironment || data.environment || "");
      var life = data.lifecycle || {};
      var adm = data.admission || {};
      renderKv($("paper-kv"), [
        ["横幅", data.banner || ""],
        ["环境", data.allowedEnvironment || data.environment || "SIMULATE"],
        ["实盘", data.liveTradingEnabled ? "开（异常）" : "关"],
        ["草稿数", data.draftCount],
        ["已接受", data.acceptedCount],
        ["策略草稿", life.draft ? shortHash(life.draft.strategyHash) : "无"],
        ["已校验", life.validated ? shortHash(life.validated.strategyHash) : "无"],
        ["已激活", life.active ? shortHash(life.active.strategyHash) : "无"],
        ["准入", adm.passed ? "通过" : "未通过"],
      ]);
      $("paper-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function ensureDefaultPaperStrategy() {
    const errEl = $("paper-error");
    clearError(errEl);
    try {
      const data = await fetchJson("/api/paper/strategies/ensure-default", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      var note =
        data.strategyStatus ||
        (data.strategyAutoActivated ? "已自动激活默认纸面策略" : "已有激活策略（幂等）");
      $("paper-banner").textContent =
        note +
        "\nliveTradingEnabled=" +
        String(data.liveTradingEnabled) +
        "\nenvironment=" +
        (data.environment || "SIMULATE");
      loadPaper();
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function loadBroker() {
    const errEl = $("broker-error");
    clearError(errEl);
    try {
      const data = await fetchJson("/api/broker/status");
      $("broker-banner").textContent =
        (data.banner || "") +
        "\nbroker=" +
        (data.broker || "") +
        "\nliveTradingEnabled=" +
        String(data.liveTradingEnabled) +
        "\nlastErrors=" +
        JSON.stringify(data.lastErrors || []);
      var acct = data.account || {};
      renderKv($("broker-kv"), [
        ["Broker", data.broker],
        ["环境", data.environment],
        ["实盘", data.liveTradingEnabled ? "开（异常）" : "关"],
        ["准入", data.admission && data.admission.passed ? "通过" : "未通过"],
        ["现金", acct.cash],
        ["权益", acct.equity],
      ]);
      var posBody = $("broker-positions") && $("broker-positions").querySelector("tbody");
      if (posBody) {
        posBody.innerHTML = "";
        (data.positions || []).forEach(function (p) {
          var tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" +
            escapeHtml(p.symbol || "") +
            '</td><td class="num">' +
            escapeHtml(dash(p.qty)) +
            '</td><td class="num">' +
            escapeHtml(dash(p.avg_price != null ? p.avg_price : p.avgPrice)) +
            "</td>";
          posBody.appendChild(tr);
        });
      }
      $("broker-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function loadDebate(event) {
    if (event) event.preventDefault();
    const errEl = $("debate-error");
    clearError(errEl);
    $("debate-meta").textContent = "";
    const symbol = $("debate-symbol").value.trim();
    const asof = $("debate-asof").value;
    const engine = ($("debate-engine") && $("debate-engine").value) || "deterministic";
    const params = new URLSearchParams({ symbol: symbol, engine: engine });
    if (asof) params.set("asof", asof);
    try {
      const data = await fetchJson("/api/debate/report?" + params.toString());
      $("debate-meta").textContent =
        "engine=" +
        engine +
        " · kind=" +
        (data.kind || "") +
        " · verdict=" +
        data.verdict +
        " · net=" +
        (data.score && data.score.net);
      renderDebateView($("debate-view"), data);
      $("debate-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
      $("debate-json").textContent = "";
    }
  }

  async function recommendDebate() {
    const errEl = $("recommend-error");
    clearError(errEl);
    const asof = $("recommend-asof").value;
    const symbols = $("recommend-symbols").value.trim();
    const topN = Number($("recommend-topn").value || "10");
    const engine = ($("debate-engine") && $("debate-engine").value) || "deterministic";
    const body = {
      topN: topN,
      adjust_kind: "none",
      softGates: true,
      engine: engine,
      maxPicks: topN,
    };
    if (asof) body.asof = asof;
    if (symbols) body.symbols = symbols;
    setRecommendBusy(true, "正在生成推荐并辩论…");
    try {
      const data = await fetchJson("/api/research/brief/debate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (data.brief) applyBriefToRecommendPanel(data.brief, "辩论");
      else {
        $("recommend-meta").textContent =
          "辩论完成 · engine=" + data.engine + " · 场次=" + (data.debates ? data.debates.length : 0);
      }
      var firstDebate = data.debates && data.debates[0] && data.debates[0].debate;
      if (firstDebate) renderDebateView($("debate-view"), firstDebate);
      $("recommend-json").textContent = JSON.stringify(data, null, 2);
      if (data.brief && data.brief.asof && $("recommend-asof")) {
        $("recommend-asof").value = data.brief.asof;
      }
    } catch (e) {
      showError(errEl, formatBriefError(e.detail || e));
    } finally {
      setRecommendBusy(false);
    }
  }

  function setRecommendBusy(busy, loadingMsg) {
    var ids = ["btn-recommend-go", "btn-recommend-paper", "btn-recommend-debate", "btn-wizard-go"];
    for (var i = 0; i < ids.length; i++) {
      var btn = $(ids[i]);
      if (btn) btn.disabled = !!busy;
    }
    var loading = $("recommend-loading");
    if (loading) {
      if (busy) {
        loading.hidden = false;
        loading.textContent =
          loadingMsg ||
          window.__recommendLoadingHint ||
          "正在拉取日线并打分，watch≈30 只时可能需要数十秒…";
      } else {
        loading.hidden = true;
      }
    }
    var meta = $("recommend-meta");
    if (meta) {
      if (busy) meta.classList.add("is-loading");
      else meta.classList.remove("is-loading");
    }
  }

  function ynZh(flag) {
    return flag ? "是" : "否";
  }

  function applyBriefToRecommendPanel(data, sourceLabel) {
    var picks = (data && data.picks) || [];
    var metaBits = [];
    if (sourceLabel) metaBits.push(sourceLabel);
    metaBits.push("asof=" + ((data && data.asof) || "—"));
    if (data && data.asofMode) metaBits.push("asofMode=" + data.asofMode);
    metaBits.push("provider=" + ((data && data.provider) || "—"));
    metaBits.push("推荐=" + picks.length);
    metaBits.push("截面=" + ((data && data.panelSize) || 0));
    if (data && data.dataNote) metaBits.push(data.dataNote);
    if (data && data.gatesNote) metaBits.push(data.gatesNote);
    $("recommend-meta").textContent = metaBits.join(" · ");
    renderKv($("recommend-kv"), [
      ["截面日 asof", (data && data.asof) || "—"],
      ["asof 模式", (data && data.asofMode) || "—"],
      ["行情 provider", (data && data.provider) || "—"],
      ["宇宙规模", data && data.universeSize != null ? String(data.universeSize) : "—"],
      ["宇宙层级", (data && data.universeTier) || "—"],
      ["有效截面 panel", data && data.panelSize != null ? String(data.panelSize) : "—"],
      ["推荐数", String(picks.length)],
      ["软闸门 softGates", ynZh(!!(data && data.softGates))],
      ["闸门已放宽", ynZh(!!(data && data.gatesRelaxed))],
      ["生成时间", (data && data.generatedAt) || "—"],
      ["数据说明", (data && data.dataNote) || (data && data.gatesNote) || "—"],
      ["已落库", data && data.persistOk ? "是" : data && data.persistError ? "失败" : "—"],
      [
        "绩效样本",
        data && data.perfLogOk
          ? "已记入 +" + String(data.perfLogAppended || 0)
          : data && data.perfLogError
            ? "失败"
            : "—",
      ],
      ["环境", (data && data.environment) || "SIMULATE"],
    ]);
    renderRecommendCards(picks, data || {});
    var tbody = $("recommend-table").querySelector("tbody");
    if (tbody) {
      tbody.innerHTML = "";
      if (!picks.length) {
        emptyTable(
          tbody,
          5,
          (data && data.emptyPicksMessage) || "暂无推荐列表（可改 asof / 扩大宇宙 / 确认 Tushare）"
        );
      } else {
        for (var i = 0; i < picks.length; i++) {
          var row = picks[i];
          var tr = document.createElement("tr");
          tr.innerHTML =
            td(row.rank) +
            '<td><a href="#daily">' +
            escapeHtml(row.symbol) +
            "</a></td>" +
            tdNum(formatScore(row.composite_score)) +
            tdNum(formatPrice(row.close)) +
            td(row.reasonSummary || row.reason || "");
          tbody.appendChild(tr);
        }
      }
    }
    $("recommend-json").textContent = JSON.stringify(data, null, 2);
    if (data && data.persistOk) {
      metaBits.push("已落库");
      if (data.perfLogNote) metaBits.push(data.perfLogNote);
      $("recommend-meta").textContent = metaBits.join(" · ");
    } else if (data && data.persistError) {
      metaBits.push(data.persistError);
      $("recommend-meta").textContent = metaBits.join(" · ");
    }
  }

  async function loadRecommendHistory() {
    var errEl = $("recommend-error");
    var meta = $("recommend-history-meta");
    var tbody = $("recommend-history-table") && $("recommend-history-table").querySelector("tbody");
    if (!tbody) return;
    try {
      var data = await fetchJson("/api/research/briefs?limit=30");
      var items = (data && data.items) || [];
      tbody.innerHTML = "";
      if (!items.length) {
        emptyTable(tbody, 6, (data && data.emptyMessage) || "暂无历史推荐 — 请先生成一日并落库");
        if (meta) meta.textContent = "历史：0 条（空态；可从向导或本页生成）";
        return;
      }
      if (meta) meta.textContent = "历史：" + items.length + " 条 · 点「回看」或「复盘」";
      for (var i = 0; i < items.length; i++) {
        (function (row) {
          var tr = document.createElement("tr");
          tr.innerHTML =
            td(row.asof || "—") +
            td(row.provider || "—") +
            tdNum(row.pickCount != null ? String(row.pickCount) : "—") +
            td(row.generatedAt || row.updatedAt || "—") +
            td(row.dataNote || (row.gatesRelaxed ? "闸门已软化" : "—")) +
            "<td></td>";
          var actions = tr.lastElementChild;
          var btnView = document.createElement("button");
          btnView.type = "button";
          btnView.className = "secondary";
          btnView.textContent = "回看";
          btnView.addEventListener("click", function (ev) {
            ev.stopPropagation();
            loadStoredBrief(row.asof);
          });
          var btnReview = document.createElement("button");
          btnReview.type = "button";
          btnReview.className = "secondary";
          btnReview.textContent = "复盘";
          btnReview.style.marginLeft = "0.35rem";
          btnReview.addEventListener("click", function (ev) {
            ev.stopPropagation();
            loadBriefReview(row.asof);
          });
          actions.appendChild(btnView);
          actions.appendChild(btnReview);
          tr.style.cursor = "pointer";
          tr.title = "点击回看 asof=" + (row.asof || "");
          tr.addEventListener("click", function () {
            loadStoredBrief(row.asof);
          });
          tbody.appendChild(tr);
        })(items[i]);
      }
    } catch (e) {
      emptyTable(tbody, 6, "历史列表加载失败");
      if (meta) meta.textContent = "历史加载失败";
      if (errEl) showError(errEl, formatErrorMessage(e.detail || e));
    }
  }

  function directionOkZh(ok) {
    if (ok === true) return "对";
    if (ok === false) return "错";
    return "—";
  }

  async function loadBriefReview(asof) {
    var errEl = $("recommend-review-error");
    var meta = $("recommend-review-meta");
    var tbody = $("recommend-review-table") && $("recommend-review-table").querySelector("tbody");
    if (!asof || !tbody) return;
    clearError(errEl);
    var holdingEl = $("recommend-review-holding");
    var holding = holdingEl && holdingEl.value ? holdingEl.value : "1d";
    if (meta) meta.textContent = "正在复盘 " + asof + "（" + holding + "）…";
    try {
      var data = await fetchJson(
        "/api/research/briefs/" +
          encodeURIComponent(asof) +
          "/review?holding=" +
          encodeURIComponent(holding)
      );
      var da =
        data.direction_accuracy != null
          ? data.direction_accuracy
          : data.directionAccuracy;
      if (meta) {
        meta.textContent =
          "asof=" +
          (data.asof || asof) +
          " · holding=" +
          (data.holding || holding) +
          " · settled=" +
          (data.settledCount != null ? data.settledCount : "—") +
          " · pending=" +
          (data.pendingCount != null ? data.pendingCount : "—") +
          " · direction_accuracy=" +
          (da != null ? da : "—");
      }
      renderKv($("recommend-review-kv"), [
        ["截面日", data.asof || asof],
        ["持有期", data.holding || holding],
        ["已结算", data.settledCount],
        ["pending", data.pendingCount],
        ["方向正确率", da != null ? da : "—"],
        ["上涨占比 up_rate", data.upRate != null ? data.upRate : "—"],
        ["口径", data.metricNote || "—"],
      ]);
      tbody.innerHTML = "";
      var rows = data.rows || [];
      if (!rows.length) {
        emptyTable(tbody, 8, "复盘无行（可能仍为 pending，或缺后续日线）");
      } else {
        for (var i = 0; i < rows.length; i++) {
          var r = rows[i];
          var tr = document.createElement("tr");
          tr.innerHTML =
            td(r.rank != null ? r.rank : "—") +
            td(r.symbol || "—") +
            td(r.pending ? "pending" : "已结算") +
            tdNum(r.rawReturn != null ? r.rawReturn : "—") +
            td(directionOkZh(r.directionOk)) +
            td(r.entryDate || "—") +
            td(r.exitDate || "—") +
            td(r.note || "—");
          tbody.appendChild(tr);
        }
      }
      var jsonEl = $("recommend-review-json");
      if (jsonEl) jsonEl.textContent = JSON.stringify(data, null, 2);
      var block = $("recommend-review-block");
      if (block && block.scrollIntoView) block.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      emptyTable(tbody, 8, "复盘加载失败");
      if (meta) meta.textContent = "复盘失败";
      showError(errEl, formatErrorMessage(e.detail || e));
    }
  }

  async function loadStoredBrief(asof) {
    var errEl = $("recommend-error");
    clearError(errEl);
    if (!asof) return;
    setRecommendBusy(true, "正在读取已存推荐 " + asof + " …");
    try {
      var data = await fetchJson("/api/research/briefs/" + encodeURIComponent(asof));
      applyBriefToRecommendPanel(data, "历史回看");
      if (data.asof && $("recommend-asof")) $("recommend-asof").value = data.asof;
      location.hash = "#recommend";
      return true;
    } catch (e) {
      showError(errEl, formatBriefError(Object.assign({ status: e.status }, e.detail || {})));
      return false;
    } finally {
      setRecommendBusy(false);
    }
  }

  async function openBacktestDay(asof) {
    if (!asof) return;
    if ($("recommend-asof")) $("recommend-asof").value = asof;
    if (window.__lastBacktest && window.__lastBacktest.universeTier && $("recommend-tier")) {
      $("recommend-tier").value = window.__lastBacktest.universeTier;
    }
    if (
      window.__lastBacktest &&
      Array.isArray(window.__lastBacktest.symbols) &&
      window.__lastBacktest.symbols.length &&
      $("recommend-symbols")
    ) {
      $("recommend-symbols").value = window.__lastBacktest.symbols.join(",");
    }
    location.hash = "#recommend";
    clearError($("recommend-error"));
    setRecommendBusy(true, "正在加载回测日 " + asof + " 推荐…");
    try {
      var data = await fetchJson("/api/research/briefs/" + encodeURIComponent(asof));
      applyBriefToRecommendPanel(data, "回测→回看");
      if (data.asof && $("recommend-asof")) $("recommend-asof").value = data.asof;
      loadBriefReview(asof);
      loadRecommendHistory();
      return;
    } catch (e) {
      if (e.status && e.status !== 404) {
        showError(
          $("recommend-error"),
          formatBriefError(Object.assign({ status: e.status }, e.detail || {}))
        );
        return;
      }
    } finally {
      setRecommendBusy(false);
    }
    await loadRecommend();
    loadBriefReview(asof);
  }

  async function loadRecommendPerfStrip() {
    var el = $("recommend-perf-strip");
    if (!el) return;
    try {
      var data = await fetchJson("/api/research/performance?autoSettle=true");
      var m = (data && data.metrics) || {};
      var acc =
        m.direction_accuracy != null
          ? m.direction_accuracy
          : data.direction_accuracy != null
            ? data.direction_accuracy
            : null;
      var chips = [];
      chips.push(
        '<span class="rec-chip">pending ' +
          (data.pendingCount != null ? data.pendingCount : "—") +
          "</span>"
      );
      chips.push(
        '<span class="rec-chip">settled ' +
          (data.settledCount != null ? data.settledCount : "—") +
          "</span>"
      );
      chips.push(
        '<span class="rec-chip">direction_accuracy ' +
          (acc != null ? acc : "—") +
          "</span>"
      );
      var recent = (data && data.recentDays) || [];
      if (recent.length) {
        var mini = recent
          .map(function (d) {
            var v =
              d.direction_accuracy != null ? d.direction_accuracy : "—";
            return (
              '<span class="rec-chip muted" title="settled ' +
              (d.settledCount != null ? d.settledCount : "?") +
              '">' +
              escapeHtml(String(d.date || "").slice(5)) +
              " " +
              v +
              "</span>"
            );
          })
          .join("");
        chips.push(
          '<span class="rec-chip">近' +
            recent.length +
            "日</span>" +
            mini
        );
      }
      if (data.settleSource) {
        chips.push(
          '<span class="rec-chip muted">settle=' + escapeHtml(data.settleSource) + "</span>"
        );
      }
      el.innerHTML = chips.join("");
    } catch (_) {
      el.innerHTML =
        '<span class="rec-chip muted">绩效摘要暂不可用（无样本或未落库）</span>';
    }
  }

  async function loadRecommend(event) {
    if (event) event.preventDefault();
    const errEl = $("recommend-error");
    clearError(errEl);
    $("recommend-meta").textContent = "";
    const asof = $("recommend-asof").value;
    const symbols = $("recommend-symbols").value.trim();
    const topN = $("recommend-topn").value || "10";
    const tier = ($("recommend-tier") && $("recommend-tier").value) || "watch";
    const params = new URLSearchParams({
      topN: topN,
      adjust_kind: "none",
      softGates: "true",
      universeTier: tier,
    });
    if (asof) params.set("asof", asof);
    if (symbols) params.set("symbols", symbols);
    var nSym = symbols ? symbols.split(",").filter(Boolean).length : 0;
    setRecommendBusy(
      true,
      nSym
        ? "正在拉取日线并打分（约 " + nSym + " 只），请稍候…"
        : null
    );
    try {
      const data = await fetchJson("/api/research/brief?" + params.toString());
      applyBriefToRecommendPanel(data, "今日选股");
      if (data.asof && $("recommend-asof")) $("recommend-asof").value = data.asof;
      loadRecommendHistory();
      loadRecommendPerfStrip();
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, formatBriefError({ fail_closed: true, status: e.status, ...detail }));
      } else {
        showError(errEl, formatBriefError(Object.assign({ status: e.status }, detail)));
      }
      emptyTable($("recommend-table").querySelector("tbody"), 5, "生成失败（fail-closed / 见上方 tip）");
      $("recommend-cards").innerHTML =
        '<p class="empty-hint">生成失败（fail-closed）。请根据上方中文 tip 检查 asof、宇宙、Token 与能力矩阵；未设 BRIEF_FALLBACK=replay 时不会静默用 fixtures。也可回 <a href="#wizard">① 向导</a> 重试。</p>';
      $("recommend-json").textContent = "";
      renderKv($("recommend-kv"), []);
    } finally {
      setRecommendBusy(false);
    }
  }

  async function recommendToPaper() {
    // Also available: POST /api/research/brief/to-broker (same SIMULATE path via resolve_broker)
    const errEl = $("recommend-error");
    clearError(errEl);
    const asof = $("recommend-asof").value;
    const symbols = $("recommend-symbols").value.trim();
    const topN = Number($("recommend-topn").value || "10");
    const body = {
      topN: topN,
      adjust_kind: "none",
      softGates: true,
      universeTier: ($("recommend-tier") && $("recommend-tier").value) || "watch",
      decision_only: true,
      market: "CN",
    };
    if (asof) body.asof = asof;
    if (symbols) body.symbols = symbols;
    setRecommendBusy(true, "正在生成推荐并写入纸面草稿（SIMULATE）…");
    try {
      const data = await fetchJson("/api/research/brief/to-paper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      var statusBits = [
        "已写入纸面 draftId=" + (data.draft && data.draft.draftId),
        "环境=SIMULATE",
        "实盘=" + (data.liveTradingEnabled ? "开（异常）" : "关"),
      ];
      if (data.strategyStatus) statusBits.push(data.strategyStatus);
      else if (data.strategyAutoActivated) statusBits.push("已自动激活默认纸面策略");
      if (data.brief) {
        applyBriefToRecommendPanel(data.brief, "写入纸面");
        if (data.brief.asof && $("recommend-asof")) $("recommend-asof").value = data.brief.asof;
      }
      $("recommend-meta").textContent =
        ($("recommend-meta").textContent ? $("recommend-meta").textContent + " · " : "") +
        statusBits.join(" · ");
      $("recommend-json").textContent = JSON.stringify(data, null, 2);
      loadPaper();
    } catch (e) {
      showError(errEl, formatBriefError(e.detail || e));
    } finally {
      setRecommendBusy(false);
    }
  }

  async function loadPerformance() {
    const errEl = $("performance-error");
    clearError(errEl);
    $("performance-meta").textContent = "";
    try {
      const data = await fetchJson("/api/research/performance?autoSettle=true");
      const m = data.metrics || {};
      var settleNote = "";
      if (data.settledNewly) {
        settleNote = " · 本次新结算=" + data.settledNewly;
      }
      if (data.settleSource) {
        settleNote += " · settle=" + data.settleSource;
      }
      $("performance-meta").textContent =
        "total=" +
        (data.totalEntries != null ? data.totalEntries : "—") +
        " · pending=" +
        (data.pendingCount != null ? data.pendingCount : "—") +
        " · settled=" +
        data.settledCount +
        " · direction_accuracy=" +
        m.direction_accuracy +
        " · avg_return=" +
        m.avg_return +
        settleNote;
      renderStats($("performance-view"), [
        ["总条目", data.totalEntries],
        ["pending", data.pendingCount],
        ["已结算", data.settledCount],
        ["本次新结算", data.settledNewly],
        ["方向正确率", m.direction_accuracy],
        ["平均收益", m.avg_return],
        ["上涨占比", m.up_rate],
        ["超额占比", m.outperform_rate],
      ]);
      $("performance-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
      $("performance-json").textContent = "";
    }
  }

  async function settlePerformancePending() {
    const errEl = $("performance-error");
    clearError(errEl);
    try {
      const data = await fetchJson("/api/research/performance/settle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      $("performance-meta").textContent =
        "结算完成：新结算=" +
        (data.settledNewly != null ? data.settledNewly : 0) +
        " · pending=" +
        data.pendingCount +
        " · settled=" +
        data.settledCount +
        (data.settleSource ? " · source=" + data.settleSource : "");
      await loadPerformance();
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function logStoredBriefToPerformance() {
    const errEl = $("performance-error");
    clearError(errEl);
    var asof = $("recommend-asof") && $("recommend-asof").value;
    if (!asof) {
      showError(errEl, "请先在「今日推荐」填写或回看一个 asof");
      return;
    }
    try {
      const data = await fetchJson("/api/research/performance/log-brief", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asof: asof, fromStore: true, holding: "5d" }),
      });
      $("performance-meta").textContent =
        "已从存档记入 asof=" +
        (data.asof || asof) +
        " · appended=" +
        data.appended +
        " · " +
        (data.note || "");
      await loadPerformance();
    } catch (e) {
      showError(errEl, formatErrorMessage(e.detail || e));
    }
  }

  async function runWizard(event) {
    if (event) event.preventDefault();
    const errEl = $("wizard-error");
    clearError(errEl);
    $("wizard-meta").textContent = "";
    const asof = $("wizard-asof").value;
    const body = {
      symbols: $("wizard-symbols").value.trim(),
      topN: Number($("wizard-topn").value || "10"),
      adjust_kind: "none",
      softGates: true,
      universeTier: ($("wizard-tier") && $("wizard-tier").value) || "watch",
      decision_only: true,
      market: "CN",
      skipRefresh: $("wizard-skip-refresh").checked,
      toPaper: true,
    };
    if (asof) body.asof = asof;
    setRecommendBusy(true, "向导运行中：拉取日线并生成今日推荐…");
    try {
      const data = await fetchJson("/api/research/wizard/daily", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const stepSummary = (data.steps || [])
        .map(function (s) {
          return s.step + ":" + (s.ok ? "ok" : "fail");
        })
        .join(" · ");
      $("wizard-meta").textContent =
        (data.ok ? "成功" : "失败") +
        " · " +
        stepSummary +
        " · 实盘=" +
        (data.liveTradingEnabled ? "开（异常）" : "关");
      var view = $("wizard-view");
      if (view) view.hidden = false;
      renderSteps($("wizard-steps"), data.steps);
      var draft = data.draft || {};
      var strategyLabel = "—";
      if (data.strategyStatus) strategyLabel = data.strategyStatus;
      else if (data.strategyAutoActivated) strategyLabel = "已自动激活默认纸面策略";
      else if (draft.draftId) strategyLabel = "沿用已激活策略";
      var briefResult = data.brief || null;
      renderKv($("wizard-kv"), [
        ["结果", data.ok ? "成功" : "失败"],
        ["环境", data.environment || "SIMULATE"],
        ["实盘", data.liveTradingEnabled ? "开（异常）" : "关"],
        ["asof", (briefResult && briefResult.asof) || asof || "—"],
        ["推荐数", briefResult && briefResult.picks ? String(briefResult.picks.length) : "0"],
        ["策略", strategyLabel],
        ["草稿 ID", draft.draftId || "—"],
        ["可执行", draft.executionEligible == null ? "—" : String(draft.executionEligible)],
      ]);
      if (data.strategyStatus) {
        $("wizard-meta").textContent =
          $("wizard-meta").textContent + " · " + data.strategyStatus;
      }
      $("wizard-json").textContent = JSON.stringify(data, null, 2);
      if (briefResult) {
        if (briefResult.asof) {
          if ($("wizard-asof")) $("wizard-asof").value = briefResult.asof;
          if ($("recommend-asof")) $("recommend-asof").value = briefResult.asof;
        }
        applyBriefToRecommendPanel(briefResult, "来自向导");
        location.hash = "#recommend";
        revealHashTarget();
      }
      if (data.ok) loadPaper();
    } catch (e) {
      showError(errEl, formatBriefError(e.detail || e));
      $("wizard-json").textContent = "";
      var wv = $("wizard-view");
      if (wv) wv.hidden = true;
    } finally {
      setRecommendBusy(false);
    }
  }

  async function loadRecommendDefaults(tierOverride) {
    try {
      var tier =
        tierOverride ||
        ($("recommend-tier") && $("recommend-tier").value) ||
        "watch";
      const data = await fetchJson(
        "/api/research/defaults?universeTier=" + encodeURIComponent(tier)
      );
      if (data.loadingHint) window.__recommendLoadingHint = data.loadingHint;
      if (data.hint && $("recommend-hint")) {
        $("recommend-hint").textContent =
          data.hint +
          " 可跳转日 K / 纸面。写入纸面始终 SIMULATE；非投资建议。";
      }
      if (data.asof) {
        if ($("wizard-asof")) $("wizard-asof").value = data.asof;
        if ($("recommend-asof")) $("recommend-asof").value = data.asof;
      }
      if (data.symbols) {
        if ($("wizard-symbols")) $("wizard-symbols").value = data.symbols;
        if ($("recommend-symbols")) $("recommend-symbols").value = data.symbols;
      }
      if (data.universeTier) {
        if ($("recommend-tier")) $("recommend-tier").value = data.universeTier;
        if ($("wizard-tier")) $("wizard-tier").value = data.universeTier;
        if ($("backtest-tier")) $("backtest-tier").value = data.universeTier;
      }
      if (data.topN != null) {
        if ($("wizard-topn")) $("wizard-topn").value = String(data.topN);
        if ($("recommend-topn")) $("recommend-topn").value = String(data.topN);
      }
      var meta = $("recommend-meta");
      if (meta) {
        meta.textContent =
          "已加载 defaults · asof=" +
          (data.asof || "—") +
          " · provider=" +
          (data.provider || "—") +
          " · tier=" +
          (data.universeTier || tier) +
          " · 宇宙=" +
          (data.symbolCount != null ? data.symbolCount : "—") +
          " · topN=" +
          (data.topN != null ? data.topN : "—") +
          " · 环境=SIMULATE";
      }
      renderKv($("recommend-kv"), [
        ["截面日 asof", data.asof || "—"],
        ["asof 模式", data.asofMode || "—"],
        ["行情 provider", data.provider || "—"],
        ["宇宙规模", data.symbolCount != null ? String(data.symbolCount) : "—"],
        ["宇宙层级", data.universeTier || "watch"],
        ["推荐数 topN", data.topN != null ? String(data.topN) : "—"],
        ["软闸门", ynZh(!!data.softGates)],
        ["环境", data.environment || "SIMULATE"],
        ["实盘", ynZh(!!data.liveTradingEnabled)],
      ]);
    } catch (_) {
      /* keep HTML defaults */
    }
  }

  async function runRollingBacktest(event) {
    if (event) event.preventDefault();
    const errEl = $("backtest-error");
    clearError(errEl);
    const lastN = Number(($("backtest-lastn") && $("backtest-lastn").value) || "5");
    const tier = ($("backtest-tier") && $("backtest-tier").value) || "watch";
    const holding = ($("backtest-holding") && $("backtest-holding").value) || "1d";
    const topN = Number(($("backtest-topn") && $("backtest-topn").value) || "5");
    if ($("backtest-meta")) {
      $("backtest-meta").textContent =
        "正在回测（tier=" + tier + " · lastN=" + lastN + "）…";
    }
    const tbody =
      $("backtest-table") && $("backtest-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/research/backtest/rolling-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lastN: lastN,
          universeTier: tier,
          holding: holding,
          topN: topN,
          softGates: true,
        }),
      });
      window.__lastBacktest = data;
      var acc =
        data.direction_accuracy != null
          ? data.direction_accuracy
          : data.directionAccuracy;
      $("backtest-meta").textContent =
        "ok · source=" +
        (data.dailySource || "—") +
        " · asof " +
        (data.asofStart || "—") +
        "～" +
        (data.asofEnd || "—") +
        " · 日数=" +
        (data.asofCount != null ? data.asofCount : "—") +
        " · settled=" +
        (data.settledCount != null ? data.settledCount : "—") +
        " · pending=" +
        (data.pendingCount != null ? data.pendingCount : "—") +
        " · direction_accuracy=" +
        (acc != null ? acc : "—");
      renderKv($("backtest-kv"), [
        ["日线源", data.dailySource || "—"],
        ["宇宙层级", data.universeTier || tier],
        ["宇宙规模", data.universeSize != null ? String(data.universeSize) : "—"],
        ["区间", (data.asofStart || "—") + " ～ " + (data.asofEnd || "—")],
        ["交易日数", data.asofCount != null ? String(data.asofCount) : "—"],
        ["已结算样本", data.settledCount != null ? String(data.settledCount) : "—"],
        ["pending", data.pendingCount != null ? String(data.pendingCount) : "—"],
        ["direction_accuracy", acc != null ? String(acc) : "—"],
        ["环境", data.environment || "SIMULATE"],
        ["实盘", ynZh(!!data.liveTradingEnabled)],
      ]);
      if (tbody) {
        tbody.innerHTML = "";
        var days = data.days || [];
        if (!days.length) {
          emptyTable(tbody, 7, "无逐日结果（空态；非假数据）");
        } else {
          for (var i = 0; i < days.length; i++) {
            var d = days[i];
            var tr = document.createElement("tr");
            var da =
              d.directionAccuracy != null ? d.directionAccuracy : "—";
            var asof = d.asof || "";
            tr.innerHTML =
              td(asof || "—") +
              td(d.panelSize != null ? d.panelSize : "—") +
              td(d.pickCount != null ? d.pickCount : "—") +
              td(d.settledCount != null ? d.settledCount : "—") +
              td(d.pendingCount != null ? d.pendingCount : "—") +
              td(da) +
              "<td></td>";
            var actionTd = tr.lastChild;
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "linkish";
            btn.textContent = "看推荐";
            btn.title = "加载该日 picks 到今日推荐";
            btn.setAttribute("data-asof", asof);
            btn.addEventListener("click", function (ev) {
              var a = ev.currentTarget.getAttribute("data-asof");
              openBacktestDay(a);
            });
            actionTd.appendChild(btn);
            tbody.appendChild(tr);
          }
        }
      }
      if ($("backtest-json")) {
        $("backtest-json").textContent = JSON.stringify(data, null, 2);
      }
      loadRecommendPerfStrip();
    } catch (e) {
      showError(errEl, formatErrorMessage(e.detail || e));
      if ($("backtest-meta")) $("backtest-meta").textContent = "回测失败（fail-closed）";
      if (tbody) emptyTable(tbody, 7, "回测失败：无日线或不满足条件（不静默假数据）");
      if ($("backtest-json")) $("backtest-json").textContent = "";
      renderKv($("backtest-kv"), []);
    }
  }

  async function runWalkForwardSummary(event) {
    if (event) event.preventDefault();
    const errEl = $("wf-error");
    clearError(errEl);
    const start = $("wf-start") && $("wf-start").value;
    const end = $("wf-end") && $("wf-end").value;
    if (!start || !end) {
      showError(errEl, "请填写 start / end");
      return;
    }
    try {
      const data = await fetchJson("/api/research/backtest/walk-forward", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: start,
          end: end,
          trainDays: Number(($("wf-train") && $("wf-train").value) || 60),
          testDays: Number(($("wf-test") && $("wf-test").value) || 20),
          stepDays: Number(($("wf-step") && $("wf-step").value) || 20),
        }),
      });
      var s = (data && data.summary) || {};
      if ($("wf-meta")) {
        $("wf-meta").textContent =
          "计划折=" +
          (data.n_planned_folds != null ? data.n_planned_folds : "—") +
          " · 有效折=" +
          (data.n_valid_folds != null ? data.n_valid_folds : "—") +
          " · compounded_oos=" +
          (s.compounded_oos_return != null ? s.compounded_oos_return : "—") +
          " · degradation=" +
          (s.degradation != null ? s.degradation : "—") +
          " · consistency=" +
          (s.consistency != null ? s.consistency : "—");
      }
      if ($("wf-json")) $("wf-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, formatErrorMessage(e.detail || e));
      if ($("wf-meta")) $("wf-meta").textContent = "Walk-forward 失败";
      if ($("wf-json")) $("wf-json").textContent = "";
    }
  }

  async function loadOpsHealth() {
    try {
      const data = await fetchJson("/api/ops/health");
      var em = data.eastmoney || {};
      var lr = data.lastRefresh;
      var refreshText = "无";
      if (lr) {
        refreshText = lr.ok
          ? "ok · " + dash(lr.asof)
          : "失败 · " + dash(lr.error || lr.asof);
      }
      renderKv($("ops-kv"), [
        ["状态", data.status],
        ["版本", data.version],
        ["执行", data.executionMode],
        ["实盘", String(data.liveTradingEnabled)],
        ["启动预设 preset", data.providerPreset || "—"],
        ["BRIEF_FALLBACK", data.briefFallback || "（未开启）"],
        ["Tushare token 已配置", ynZh(!!data.supplementTokenConfigured)],
        ["默认 replay", String(data.defaultReplay)],
        ["EM 间隔", em.minInterval],
        ["熔断", em.circuitOpen ? "开" : "关"],
        ["连续失败", em.consecutiveFailures],
        ["上次刷新", refreshText],
      ]);
      $("ops-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      $("ops-json").textContent = String(e);
    }
  }

  async function listStrategies() {
    const errEl = $("strategy-error");
    clearError(errEl);
    try {
      const data = await fetchJson("/api/research/strategy/configs");
      $("strategy-meta").textContent = "configs=" + (data.configs ? data.configs.length : 0);
      var ids = (data.configs || [])
        .map(function (c) {
          return c.id || c;
        })
        .join("、");
      renderKv($("strategy-kv"), [
        ["数量", data.configs ? data.configs.length : 0],
        ["配置", ids || "—"],
        ["实盘", String(data.liveTradingEnabled)],
      ]);
      $("strategy-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function compareStrategies(event) {
    if (event) event.preventDefault();
    const errEl = $("strategy-error");
    clearError(errEl);
    const configA = $("strategy-a").value.trim();
    const configB = $("strategy-b").value.trim();
    const lastN = Number(($("strategy-lastn") && $("strategy-lastn").value) || "8");
    const tier = ($("strategy-tier") && $("strategy-tier").value) || "core";
    const requireEngine = !!(
      $("strategy-require-engine") && $("strategy-require-engine").checked
    );
    if ($("strategy-meta")) {
      $("strategy-meta").textContent = "正在对比（panel 优先 engine）…";
    }
    try {
      const data = await fetchJson("/api/research/strategy/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          configA: configA,
          configB: configB,
          lastN: lastN,
          universeTier: tier,
          requireEngine: requireEngine,
        }),
      });
      $("strategy-meta").textContent =
        "winner=" +
        data.winner +
        " · deltaFinalEquity=" +
        data.deltaFinalEquity +
        " · panelSource=" +
        (data.panelSource || "—") +
        " · liveTradingEnabled=" +
        String(data.liveTradingEnabled);
      renderKv($("strategy-kv"), [
        ["胜出", data.winner],
        ["权益差", data.deltaFinalEquity],
        ["面板来源", data.panelSource || "—"],
        ["面板行数", data.panelRows != null ? data.panelRows : "—"],
        ["交易日数", data.panelDates != null ? data.panelDates : "—"],
        ["说明", data.panelNote || "—"],
        ["A 成交", data.a && data.a.tradeCount],
        ["B 成交", data.b && data.b.tradeCount],
        ["实盘", String(data.liveTradingEnabled)],
      ]);
      $("strategy-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, formatErrorMessage(e.detail || e));
      if ($("strategy-meta")) $("strategy-meta").textContent = "对比失败";
      $("strategy-json").textContent = "";
      renderKv($("strategy-kv"), []);
    }
  }

  async function loadFundFlow(event) {
    if (event) event.preventDefault();
    const errEl = $("fund-flow-error");
    clearError(errEl);
    $("fund-flow-meta").textContent = "";
    setRawJson("fund-flow-json", null);
    const symbols = $("fund-flow-symbols").value.trim();
    const start = $("fund-flow-start").value;
    const end = $("fund-flow-end").value;
    const params = new URLSearchParams({ symbols: symbols });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const tbody = $("fund-flow-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/fund-flow?" + params.toString());
      const rows = data.rows || [];
      $("fund-flow-meta").textContent = marketMeta(data.provider, rows.length);
      setRawJson("fund-flow-json", data);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 5, "暂无资金流数据");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.symbol) +
          td(row.date) +
          tdNum(formatMoney(row.main_net), signedClass(row.main_net)) +
          tdNum(formatMoney(row.large_net), signedClass(row.large_net)) +
          tdNum(formatMoney(row.super_net), signedClass(row.super_net));
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 5, "查询失败");
      setRawJson("fund-flow-json", null);
    }
  }

  async function loadSectorFundFlow(event) {
    if (event) event.preventDefault();
    const errEl = $("sector-fund-flow-error");
    clearError(errEl);
    $("sector-fund-flow-meta").textContent = "";
    setRawJson("sector-fund-flow-json", null);
    const sectors = $("sector-fund-flow-sectors").value.trim();
    const start = $("sector-fund-flow-start").value;
    const end = $("sector-fund-flow-end").value;
    const params = new URLSearchParams({ sectors: sectors });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const tbody = $("sector-fund-flow-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/sector-fund-flow?" + params.toString());
      const rows = data.rows || [];
      $("sector-fund-flow-meta").textContent = marketMeta(data.provider, rows.length);
      setRawJson("sector-fund-flow-json", data);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 5, "暂无板块资金流");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.sector_code) +
          td(row.sector_name || "") +
          td(row.date) +
          tdNum(formatMoney(row.main_net), signedClass(row.main_net)) +
          tdNum(formatPct(row.change_pct), signedClass(row.change_pct));
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 5, "查询失败");
      setRawJson("sector-fund-flow-json", null);
    }
  }

  function renderNewsList(rows) {
    var host = $("news-list");
    if (!host) return;
    host.innerHTML = "";
    if (!rows || !rows.length) {
      host.innerHTML = '<p class="empty-hint">暂无新闻</p>';
      return;
    }
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var article = document.createElement("article");
      article.className = "news-item";
      var sent = row.sentiment == null ? "" : formatSentiment(row.sentiment);
      article.innerHTML =
        '<div class="news-meta-line"><span>' +
        escapeHtml(dash(row.symbol || row.sector_code)) +
        "</span><span>" +
        escapeHtml(dash(row.date)) +
        "</span>" +
        (sent
          ? '<span class="' +
            signedClass(row.sentiment) +
            '">' +
            escapeHtml(sent) +
            "</span>"
          : "") +
        "</div><h3>" +
        escapeHtml(dash(row.title)) +
        "</h3>" +
        (row.summary
          ? '<p class="news-summary">' + escapeHtml(row.summary) + "</p>"
          : "");
      host.appendChild(article);
    }
  }

  async function loadNews(event) {
    if (event) event.preventDefault();
    const errEl = $("news-error");
    clearError(errEl);
    $("news-meta").textContent = "";
    setRawJson("news-json", null);
    const symbols = $("news-symbols").value.trim();
    const start = $("news-start").value;
    const end = $("news-end").value;
    const params = new URLSearchParams({ symbols: symbols });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const tbody = $("news-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/news?" + params.toString());
      const rows = data.rows || [];
      $("news-meta").textContent = marketMeta(data.provider, rows.length);
      setRawJson("news-json", data);
      renderNewsList(rows);
      tbody.innerHTML = "";
      if (!rows.length) {
        emptyTable(tbody, 4, "暂无新闻");
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          td(row.symbol || row.sector_code || "") +
          td(row.date) +
          td(row.title) +
          tdNum(
            row.sentiment == null ? "—" : formatSentiment(row.sentiment),
            signedClass(row.sentiment)
          );
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      renderNewsList([]);
      emptyTable(tbody, 4, "查询失败");
      setRawJson("news-json", null);
    }
  }

  async function loadLhb(event) {
    if (event) event.preventDefault();
    const errEl = $("lhb-error");
    clearError(errEl);
    $("lhb-meta").textContent = "";
    setRawJson("lhb-json", null);
    const symbols = $("lhb-symbols").value.trim();
    const asof = $("lhb-asof").value;
    const lookBack = $("lhb-lookback").value;
    const params = new URLSearchParams({ symbols: symbols, asof_date: asof });
    if (lookBack) params.set("look_back_days", lookBack);
    const tbody = $("lhb-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/lhb?" + params.toString());
      const items = data.items || [];
      var recCount = 0;
      for (var i = 0; i < items.length; i++) {
        recCount += (items[i].records || []).length;
      }
      $("lhb-meta").textContent =
        "provider=" +
        data.provider +
        " · 标的=" +
        items.length +
        " · 记录=" +
        recCount;
      setRawJson("lhb-json", data);
      tbody.innerHTML = "";
      if (!items.length) {
        emptyTable(tbody, 5, "暂无龙虎榜记录");
        return;
      }
      for (const item of items) {
        const recs = item.records || [];
        if (!recs.length) {
          const tr = document.createElement("tr");
          tr.className = "empty-row";
          tr.innerHTML = td(item.symbol) + '<td colspan="4">近窗口无上榜记录</td>';
          tbody.appendChild(tr);
          continue;
        }
        for (const row of recs) {
          const tr = document.createElement("tr");
          tr.innerHTML =
            td(item.symbol) +
            td(row.date) +
            td(row.reason || "") +
            tdNum(formatMoney(row.net_buy), signedClass(row.net_buy)) +
            tdNum(formatPct(row.turnover_rate));
          tbody.appendChild(tr);
        }
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 5, "查询失败");
      setRawJson("lhb-json", null);
    }
  }

  async function loadUnlock(event) {
    if (event) event.preventDefault();
    const errEl = $("unlock-error");
    clearError(errEl);
    $("unlock-meta").textContent = "";
    setRawJson("unlock-json", null);
    const symbols = $("unlock-symbols").value.trim();
    const asof = $("unlock-asof").value;
    const forward = $("unlock-forward").value;
    const params = new URLSearchParams({ symbols: symbols, asof_date: asof });
    if (forward) params.set("forward_days", forward);
    const tbody = $("unlock-table").querySelector("tbody");
    try {
      const data = await fetchJson("/api/market/unlock?" + params.toString());
      const items = data.items || [];
      var history = 0;
      var upcoming = 0;
      for (var i = 0; i < items.length; i++) {
        history += (items[i].history || []).length;
        upcoming += (items[i].upcoming || []).length;
      }
      $("unlock-meta").textContent =
        "provider=" +
        data.provider +
        " · 标的=" +
        items.length +
        " · 历史=" +
        history +
        " · 待解禁=" +
        upcoming;
      setRawJson("unlock-json", data);
      tbody.innerHTML = "";
      if (!items.length) {
        emptyTable(tbody, 6, "暂无解禁记录");
        return;
      }
      for (const item of items) {
        const buckets = [
          ["历史", item.history || []],
          ["待解禁", item.upcoming || []],
        ];
        let wrote = false;
        for (let b = 0; b < buckets.length; b++) {
          const bucket = buckets[b][0];
          const rows = buckets[b][1];
          for (const row of rows) {
            wrote = true;
            const tr = document.createElement("tr");
            tr.innerHTML =
              td(item.symbol) +
              td(bucket) +
              td(row.date) +
              td(row.type || "") +
              tdNum(formatSharesWan(row.shares)) +
              tdNum(formatPct(row.ratio));
            tbody.appendChild(tr);
          }
        }
        if (!wrote) {
          const tr = document.createElement("tr");
          tr.className = "empty-row";
          tr.innerHTML = td(item.symbol) + '<td colspan="5">无解禁记录</td>';
          tbody.appendChild(tr);
        }
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      emptyTable(tbody, 6, "查询失败");
      setRawJson("unlock-json", null);
    }
  }

  function boot() {
    $("btn-matrix").addEventListener("click", loadMatrix);
    $("btn-preset").addEventListener("click", applyPreset);
    $("btn-pref").addEventListener("click", applyPreference);
    $("btn-paper").addEventListener("click", loadPaper);
    $("btn-paper-ensure").addEventListener("click", ensureDefaultPaperStrategy);
    $("btn-broker").addEventListener("click", loadBroker);
    $("daily-form").addEventListener("submit", loadDaily);
    $("realtime-form").addEventListener("submit", loadRealtime);
    $("minute-form").addEventListener("submit", loadMinute);
    $("depth5-form").addEventListener("submit", loadDepth5);
    $("financial-form").addEventListener("submit", loadFinancial);
    $("adj-factor-form").addEventListener("submit", loadAdjFactor);
    $("daily-adjusted-form").addEventListener("submit", loadDailyAdjusted);
    $("full-minute-form").addEventListener("submit", loadFullMinute);
    $("fund-flow-form").addEventListener("submit", loadFundFlow);
    $("sector-fund-flow-form").addEventListener("submit", loadSectorFundFlow);
    $("news-form").addEventListener("submit", loadNews);
    $("lhb-form").addEventListener("submit", loadLhb);
    $("unlock-form").addEventListener("submit", loadUnlock);
    $("debate-form").addEventListener("submit", loadDebate);
    $("recommend-form").addEventListener("submit", loadRecommend);
    $("btn-recommend-paper").addEventListener("click", recommendToPaper);
    $("btn-recommend-debate").addEventListener("click", recommendDebate);
    if ($("btn-recommend-history")) {
      $("btn-recommend-history").addEventListener("click", loadRecommendHistory);
    }
    $("btn-performance").addEventListener("click", loadPerformance);
    if ($("btn-performance-settle")) {
      $("btn-performance-settle").addEventListener("click", settlePerformancePending);
    }
    if ($("btn-performance-log-stored")) {
      $("btn-performance-log-stored").addEventListener("click", logStoredBriefToPerformance);
    }
    if ($("recommend-review-holding")) {
      $("recommend-review-holding").addEventListener("change", function () {
        var meta = $("recommend-review-meta");
        var asofMatch = meta && meta.textContent ? meta.textContent.match(/asof=(\d{4}-\d{2}-\d{2})/) : null;
        if (asofMatch) loadBriefReview(asofMatch[1]);
      });
    }
    $("strategy-form").addEventListener("submit", compareStrategies);
    $("btn-strategy-list").addEventListener("click", listStrategies);
    if ($("backtest-form")) {
      $("backtest-form").addEventListener("submit", runRollingBacktest);
    }
    if ($("walkforward-form")) {
      $("walkforward-form").addEventListener("submit", runWalkForwardSummary);
    }
    if ($("recommend-tier")) {
      $("recommend-tier").addEventListener("change", function () {
        loadRecommendDefaults($("recommend-tier").value);
      });
    }
    if ($("wizard-tier")) {
      $("wizard-tier").addEventListener("change", function () {
        loadRecommendDefaults($("wizard-tier").value);
      });
    }
    $("wizard-form").addEventListener("submit", runWizard);
    $("btn-ops-health").addEventListener("click", loadOpsHealth);
    window.addEventListener("hashchange", revealHashTarget);
    window.addEventListener("scroll", markNav, { passive: true });
    revealHashTarget();
    markNav();
    loadRecommendDefaults();
    loadRecommendHistory();
    loadRecommendPerfStrip();
    loadMatrix();
    loadPaper();
    loadBroker();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
