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
    if (typeof err === "string") {
      el.textContent = err;
      return;
    }
    el.textContent = JSON.stringify(err, null, 2);
  }

  function clearError(el) {
    el.hidden = true;
    el.textContent = "";
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

  function renderRecommendCards(picks) {
    var host = $("recommend-cards");
    if (!host) return;
    host.innerHTML = "";
    if (!picks || !picks.length) {
      host.innerHTML = '<p class="hint" style="margin:0">暂无推荐结果</p>';
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
        '<div class="rec-meta"><span>收盘 <strong>' +
        escapeHtml(row.close == null ? "—" : row.close) +
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
    const symbols = $("daily-symbols").value.trim();
    const start = $("daily-start").value;
    const end = $("daily-end").value;
    const params = new URLSearchParams({ symbols: symbols });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    try {
      const data = await fetchJson("/api/market/daily?" + params.toString());
      $("daily-meta").textContent =
        "provider=" + data.provider + " · rows=" + (data.rows ? data.rows.length : 0);
      const tbody = $("daily-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of data.rows || []) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          row.symbol +
          "</td><td>" +
          row.date +
          "</td><td>" +
          row.close +
          "</td><td>" +
          row.volume +
          "</td><td>" +
          row.change_pct +
          "</td>";
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("daily-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadMinute(event) {
    if (event) event.preventDefault();
    const errEl = $("minute-error");
    clearError(errEl);
    $("minute-meta").textContent = "";
    const symbols = $("minute-symbols").value.trim();
    const freq = $("minute-freq").value;
    const start = $("minute-start").value;
    const end = $("minute-end").value;
    const params = new URLSearchParams({ symbols: symbols, freq: freq });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    try {
      const data = await fetchJson("/api/market/minute?" + params.toString());
      $("minute-meta").textContent =
        "provider=" +
        data.provider +
        " · freq=" +
        (data.freq || freq) +
        " · rows=" +
        (data.rows ? data.rows.length : 0);
      const tbody = $("minute-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of data.rows || []) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          row.symbol +
          "</td><td>" +
          row.datetime +
          "</td><td>" +
          row.close +
          "</td><td>" +
          row.volume +
          "</td><td>" +
          row.freq +
          "</td>";
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("minute-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadDepth5(event) {
    if (event) event.preventDefault();
    const errEl = $("depth5-error");
    clearError(errEl);
    $("depth5-meta").textContent = "";
    $("depth5-json").textContent = "";
    const symbols = $("depth5-symbols").value.trim();
    const params = new URLSearchParams({ symbols: symbols });
    try {
      const data = await fetchJson("/api/market/depth5?" + params.toString());
      $("depth5-meta").textContent =
        "provider=" + data.provider + " · rows=" + (data.rows ? data.rows.length : 0);
      const tbody = $("depth5-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of data.rows || []) {
        for (let i = 0; i < 5; i++) {
          const tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" +
            row.symbol +
            "</td><td>" +
            (i + 1) +
            "</td><td>" +
            (row.bid_prices ? row.bid_prices[i] : "") +
            "</td><td>" +
            (row.bid_volumes ? row.bid_volumes[i] : "") +
            "</td><td>" +
            (row.ask_prices ? row.ask_prices[i] : "") +
            "</td><td>" +
            (row.ask_volumes ? row.ask_volumes[i] : "") +
            "</td>";
          tbody.appendChild(tr);
        }
      }
      $("depth5-json").textContent = JSON.stringify(data.rows || [], null, 2);
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("depth5-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadFinancial(event) {
    if (event) event.preventDefault();
    const errEl = $("financial-error");
    clearError(errEl);
    $("financial-meta").textContent = "";
    $("financial-json").textContent = "";
    const symbols = $("financial-symbols").value.trim();
    const periods = $("financial-periods").value.trim() || "8";
    const params = new URLSearchParams({ symbols: symbols, periods: periods });
    try {
      const data = await fetchJson("/api/market/financial?" + params.toString());
      const items = data.items || [];
      $("financial-meta").textContent =
        "provider=" + data.provider + " · items=" + items.length;
      const tbody = $("financial-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const item of items) {
        const income = item.income || [];
        const balance = item.balance || [];
        const cashflow = item.cashflow || [];
        const n = Math.max(income.length, balance.length, cashflow.length, 1);
        for (let i = 0; i < n; i++) {
          const inc = income[i] || {};
          const bal = balance[i] || {};
          const cf = cashflow[i] || {};
          const tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" +
            item.symbol +
            "</td><td>" +
            (inc.period_end || bal.period_end || cf.period_end || "") +
            "</td><td>" +
            (inc.revenue != null ? inc.revenue : "") +
            "</td><td>" +
            (inc.net_income != null ? inc.net_income : "") +
            "</td><td>" +
            (bal.total_assets != null ? bal.total_assets : "") +
            "</td><td>" +
            (cf.net_operating_cash_flow != null
              ? cf.net_operating_cash_flow
              : "") +
            "</td>";
          tbody.appendChild(tr);
        }
      }
      $("financial-json").textContent = JSON.stringify(items, null, 2);
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("financial-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadAdjFactor(event) {
    if (event) event.preventDefault();
    const errEl = $("adj-factor-error");
    clearError(errEl);
    $("adj-factor-meta").textContent = "";
    $("adj-factor-json").textContent = "";
    const symbols = $("adj-factor-symbols").value.trim();
    const kind = $("adj-factor-kind").value || "qfq";
    const params = new URLSearchParams({ symbols: symbols, kind: kind });
    try {
      const data = await fetchJson("/api/market/adj-factor?" + params.toString());
      const rows = data.rows || [];
      $("adj-factor-meta").textContent =
        "provider=" +
        data.provider +
        " · kind=" +
        data.kind +
        " · rows=" +
        rows.length;
      const tbody = $("adj-factor-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          row.symbol +
          "</td><td>" +
          row.trade_date +
          "</td><td>" +
          row.ex_factor +
          "</td>";
        tbody.appendChild(tr);
      }
      $("adj-factor-json").textContent = JSON.stringify(rows, null, 2);
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("adj-factor-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadDailyAdjusted(event) {
    if (event) event.preventDefault();
    const errEl = $("daily-adjusted-error");
    clearError(errEl);
    $("daily-adjusted-meta").textContent = "";
    const symbols = $("daily-adjusted-symbols").value.trim();
    const kind = $("daily-adjusted-kind").value || "qfq";
    const start = $("daily-adjusted-start").value;
    const end = $("daily-adjusted-end").value;
    const params = new URLSearchParams({ symbols: symbols, kind: kind });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
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
        " · rows=" +
        rows.length;
      const tbody = $("daily-adjusted-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          row.symbol +
          "</td><td>" +
          row.date +
          "</td><td>" +
          row.close +
          "</td><td>" +
          row.ex_factor +
          "</td><td>" +
          (row.adjust_kind || data.kind) +
          "</td>";
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("daily-adjusted-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadFullMinute(event) {
    if (event) event.preventDefault();
    const errEl = $("full-minute-error");
    clearError(errEl);
    $("full-minute-meta").textContent = "";
    const symbols = $("full-minute-symbols").value.trim();
    const tradeDate = $("full-minute-date").value;
    const count = $("full-minute-count").value || "300";
    const params = new URLSearchParams({ symbols: symbols, count: count });
    if (tradeDate) params.set("trade_date", tradeDate);
    try {
      const data = await fetchJson("/api/market/full-minute?" + params.toString());
      $("full-minute-meta").textContent =
        "provider=" +
        data.provider +
        " · trade_date=" +
        (data.trade_date || tradeDate || "") +
        " · rows=" +
        (data.rows ? data.rows.length : 0);
      const tbody = $("full-minute-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of data.rows || []) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          row.symbol +
          "</td><td>" +
          row.datetime +
          "</td><td>" +
          row.close +
          "</td><td>" +
          row.volume +
          "</td><td>" +
          row.freq +
          "</td>";
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("full-minute-table").querySelector("tbody").innerHTML = "";
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
    const topN = Number($("recommend-topn").value || "5");
    const engine = ($("debate-engine") && $("debate-engine").value) || "deterministic";
    const body = {
      asof: asof,
      topN: topN,
      adjust_kind: "none",
      engine: engine,
      maxPicks: topN,
    };
    if (symbols) body.symbols = symbols;
    try {
      const data = await fetchJson("/api/research/brief/debate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      $("recommend-meta").textContent =
        "brief/debate engine=" +
        data.engine +
        " · debates=" +
        (data.debates ? data.debates.length : 0);
      var firstDebate = data.debates && data.debates[0] && data.debates[0].debate;
      if (firstDebate) renderDebateView($("debate-view"), firstDebate);
      $("recommend-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function loadRecommend(event) {
    if (event) event.preventDefault();
    const errEl = $("recommend-error");
    clearError(errEl);
    $("recommend-meta").textContent = "";
    const asof = $("recommend-asof").value;
    const symbols = $("recommend-symbols").value.trim();
    const topN = $("recommend-topn").value || "5";
    const params = new URLSearchParams({ asof: asof, topN: topN, adjust_kind: "none" });
    if (symbols) params.set("symbols", symbols);
    try {
      const data = await fetchJson("/api/research/brief?" + params.toString());
      $("recommend-meta").textContent =
        "provider=" +
        (data.provider || "") +
        " · picks=" +
        (data.picks ? data.picks.length : 0) +
        " · panel=" +
        data.panelSize;
      const picks = data.picks || [];
      renderRecommendCards(picks);
      const tbody = $("recommend-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of picks) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          escapeHtml(row.rank) +
          '</td><td><a href="#daily">' +
          escapeHtml(row.symbol) +
          "</a></td><td>" +
          escapeHtml(row.composite_score) +
          "</td><td>" +
          escapeHtml(row.close) +
          "</td><td>" +
          escapeHtml(row.reasonSummary || row.reason || "") +
          "</td>";
        tbody.appendChild(tr);
      }
      $("recommend-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("recommend-table").querySelector("tbody").innerHTML = "";
      $("recommend-cards").innerHTML = "";
      $("recommend-json").textContent = "";
    }
  }

  async function recommendToPaper() {
    // Also available: POST /api/research/brief/to-broker (same SIMULATE path via resolve_broker)
    const errEl = $("recommend-error");
    clearError(errEl);
    const asof = $("recommend-asof").value;
    const symbols = $("recommend-symbols").value.trim();
    const topN = Number($("recommend-topn").value || "5");
    const body = {
      asof: asof,
      topN: topN,
      adjust_kind: "none",
      decision_only: true,
      now: "2026-09-07T09:40:00+08:00",
      market: "CN",
    };
    if (symbols) body.symbols = symbols;
    try {
      const data = await fetchJson("/api/research/brief/to-paper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      $("recommend-meta").textContent =
        "to-paper draftId=" +
        (data.draft && data.draft.draftId) +
        " · liveTradingEnabled=" +
        String(data.liveTradingEnabled);
      $("recommend-json").textContent = JSON.stringify(data, null, 2);
      loadPaper();
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function loadPerformance() {
    const errEl = $("performance-error");
    clearError(errEl);
    $("performance-meta").textContent = "";
    try {
      const data = await fetchJson("/api/research/performance");
      const m = data.metrics || {};
      $("performance-meta").textContent =
        "settled=" +
        data.settledCount +
        " · direction_accuracy=" +
        m.direction_accuracy +
        " · avg_return=" +
        m.avg_return;
      renderStats($("performance-view"), [
        ["已结算", data.settledCount],
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

  async function runWizard(event) {
    if (event) event.preventDefault();
    const errEl = $("wizard-error");
    clearError(errEl);
    $("wizard-meta").textContent = "";
    const body = {
      asof: $("wizard-asof").value,
      symbols: $("wizard-symbols").value.trim(),
      topN: Number($("wizard-topn").value || "5"),
      adjust_kind: "none",
      decision_only: true,
      now: "2026-09-07T09:40:00+08:00",
      market: "CN",
      skipRefresh: $("wizard-skip-refresh").checked,
      toPaper: true,
    };
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
        (data.ok ? "ok" : "failed") +
        " · " +
        stepSummary +
        " · liveTradingEnabled=" +
        data.liveTradingEnabled;
      var view = $("wizard-view");
      if (view) view.hidden = false;
      renderSteps($("wizard-steps"), data.steps);
      var draft = data.draft || {};
      renderKv($("wizard-kv"), [
        ["结果", data.ok ? "成功" : "失败"],
        ["环境", data.environment || "SIMULATE"],
        ["实盘", data.liveTradingEnabled ? "开（异常）" : "关"],
        ["草稿 ID", draft.draftId || "—"],
        ["可执行", draft.executionEligible == null ? "—" : String(draft.executionEligible)],
      ]);
      $("wizard-json").textContent = JSON.stringify(data, null, 2);
      var brief = data.brief || (data.steps && data.steps.find(function (s) {
        return s.step === "brief" && s.result;
      }));
      var briefResult = data.brief || (brief && brief.result) || null;
      if (briefResult && briefResult.picks) {
        renderRecommendCards(briefResult.picks);
        $("recommend-meta").textContent =
          "from wizard · picks=" + briefResult.picks.length;
      }
      if (data.ok) loadPaper();
    } catch (e) {
      showError(errEl, e.detail || String(e));
      $("wizard-json").textContent = "";
      var wv = $("wizard-view");
      if (wv) wv.hidden = true;
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
    try {
      const data = await fetchJson("/api/research/strategy/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ configA: configA, configB: configB }),
      });
      $("strategy-meta").textContent =
        "winner=" +
        data.winner +
        " · deltaFinalEquity=" +
        data.deltaFinalEquity +
        " · liveTradingEnabled=" +
        String(data.liveTradingEnabled);
      renderKv($("strategy-kv"), [
        ["胜出", data.winner],
        ["权益差", data.deltaFinalEquity],
        ["A 成交", data.a && data.a.tradeCount],
        ["B 成交", data.b && data.b.tradeCount],
        ["实盘", String(data.liveTradingEnabled)],
      ]);
      $("strategy-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
      $("strategy-json").textContent = "";
    }
  }

  async function loadFundFlow(event) {
    if (event) event.preventDefault();
    const errEl = $("fund-flow-error");
    clearError(errEl);
    $("fund-flow-meta").textContent = "";
    const symbols = $("fund-flow-symbols").value.trim();
    const start = $("fund-flow-start").value;
    const end = $("fund-flow-end").value;
    const params = new URLSearchParams({ symbols: symbols });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    try {
      const data = await fetchJson("/api/market/fund-flow?" + params.toString());
      $("fund-flow-meta").textContent =
        "provider=" + data.provider + " · rows=" + (data.rows ? data.rows.length : 0);
      const tbody = $("fund-flow-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of data.rows || []) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          row.symbol +
          "</td><td>" +
          row.date +
          "</td><td>" +
          row.main_net +
          "</td><td>" +
          row.large_net +
          "</td><td>" +
          row.super_net +
          "</td>";
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("fund-flow-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadSectorFundFlow(event) {
    if (event) event.preventDefault();
    const errEl = $("sector-fund-flow-error");
    clearError(errEl);
    $("sector-fund-flow-meta").textContent = "";
    const sectors = $("sector-fund-flow-sectors").value.trim();
    const start = $("sector-fund-flow-start").value;
    const end = $("sector-fund-flow-end").value;
    const params = new URLSearchParams({ sectors: sectors });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    try {
      const data = await fetchJson("/api/market/sector-fund-flow?" + params.toString());
      $("sector-fund-flow-meta").textContent =
        "provider=" + data.provider + " · rows=" + (data.rows ? data.rows.length : 0);
      const tbody = $("sector-fund-flow-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of data.rows || []) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          row.sector_code +
          "</td><td>" +
          row.date +
          "</td><td>" +
          row.main_net +
          "</td><td>" +
          (row.change_pct == null ? "" : row.change_pct) +
          "</td>";
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("sector-fund-flow-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadNews(event) {
    if (event) event.preventDefault();
    const errEl = $("news-error");
    clearError(errEl);
    $("news-meta").textContent = "";
    const symbols = $("news-symbols").value.trim();
    const start = $("news-start").value;
    const end = $("news-end").value;
    const params = new URLSearchParams({ symbols: symbols });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    try {
      const data = await fetchJson("/api/market/news?" + params.toString());
      $("news-meta").textContent =
        "provider=" + data.provider + " · rows=" + (data.rows ? data.rows.length : 0);
      const tbody = $("news-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of data.rows || []) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          (row.symbol || "") +
          "</td><td>" +
          row.date +
          "</td><td>" +
          row.title +
          "</td><td>" +
          (row.sentiment == null ? "" : row.sentiment) +
          "</td>";
        tbody.appendChild(tr);
      }
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("news-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadLhb(event) {
    if (event) event.preventDefault();
    const errEl = $("lhb-error");
    clearError(errEl);
    $("lhb-meta").textContent = "";
    $("lhb-json").textContent = "";
    const symbols = $("lhb-symbols").value.trim();
    const asof = $("lhb-asof").value;
    const lookBack = $("lhb-lookback").value;
    const params = new URLSearchParams({ symbols: symbols, asof_date: asof });
    if (lookBack) params.set("look_back_days", lookBack);
    try {
      const data = await fetchJson("/api/market/lhb?" + params.toString());
      const items = data.items || [];
      const records = items.length ? items[0].records || [] : [];
      $("lhb-meta").textContent =
        "provider=" +
        data.provider +
        " · items=" +
        items.length +
        " · records=" +
        records.length;
      const tbody = $("lhb-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const item of items) {
        const recs = item.records || [];
        if (!recs.length) {
          const tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" +
            item.symbol +
            "</td><td colspan=\"4\">(空窗口)</td>";
          tbody.appendChild(tr);
          continue;
        }
        for (const row of recs) {
          const tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" +
            item.symbol +
            "</td><td>" +
            row.date +
            "</td><td>" +
            (row.reason || "") +
            "</td><td>" +
            row.net_buy +
            "</td><td>" +
            row.turnover_rate +
            "</td>";
          tbody.appendChild(tr);
        }
      }
      $("lhb-json").textContent = JSON.stringify(items, null, 2);
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("lhb-table").querySelector("tbody").innerHTML = "";
    }
  }

  async function loadUnlock(event) {
    if (event) event.preventDefault();
    const errEl = $("unlock-error");
    clearError(errEl);
    $("unlock-meta").textContent = "";
    $("unlock-json").textContent = "";
    const symbols = $("unlock-symbols").value.trim();
    const asof = $("unlock-asof").value;
    const forward = $("unlock-forward").value;
    const params = new URLSearchParams({ symbols: symbols, asof_date: asof });
    if (forward) params.set("forward_days", forward);
    try {
      const data = await fetchJson("/api/market/unlock?" + params.toString());
      const items = data.items || [];
      const history = items.length ? items[0].history || [] : [];
      const upcoming = items.length ? items[0].upcoming || [] : [];
      $("unlock-meta").textContent =
        "provider=" +
        data.provider +
        " · items=" +
        items.length +
        " · history=" +
        history.length +
        " · upcoming=" +
        upcoming.length;
      const tbody = $("unlock-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const item of items) {
        const buckets = [
          ["history", item.history || []],
          ["upcoming", item.upcoming || []],
        ];
        let wrote = false;
        for (let b = 0; b < buckets.length; b++) {
          const bucket = buckets[b][0];
          const rows = buckets[b][1];
          for (const row of rows) {
            wrote = true;
            const tr = document.createElement("tr");
            tr.innerHTML =
              "<td>" +
              item.symbol +
              "</td><td>" +
              bucket +
              "</td><td>" +
              row.date +
              "</td><td>" +
              (row.type || "") +
              "</td><td>" +
              row.shares +
              "</td><td>" +
              row.ratio +
              "</td>";
            tbody.appendChild(tr);
          }
        }
        if (!wrote) {
          const tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" + item.symbol + "</td><td colspan=\"5\">(无解禁记录)</td>";
          tbody.appendChild(tr);
        }
      }
      $("unlock-json").textContent = JSON.stringify(items, null, 2);
    } catch (e) {
      const detail = e.detail || { message: String(e) };
      if (e.status === 409) {
        showError(errEl, { fail_closed: true, ...detail });
      } else {
        showError(errEl, detail);
      }
      $("unlock-table").querySelector("tbody").innerHTML = "";
    }
  }

  function boot() {
    $("btn-matrix").addEventListener("click", loadMatrix);
    $("btn-preset").addEventListener("click", applyPreset);
    $("btn-pref").addEventListener("click", applyPreference);
    $("btn-paper").addEventListener("click", loadPaper);
    $("btn-broker").addEventListener("click", loadBroker);
    $("daily-form").addEventListener("submit", loadDaily);
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
    $("btn-performance").addEventListener("click", loadPerformance);
    $("strategy-form").addEventListener("submit", compareStrategies);
    $("btn-strategy-list").addEventListener("click", listStrategies);
    $("wizard-form").addEventListener("submit", runWizard);
    $("btn-ops-health").addEventListener("click", loadOpsHealth);
    window.addEventListener("hashchange", revealHashTarget);
    window.addEventListener("scroll", markNav, { passive: true });
    revealHashTarget();
    markNav();
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
