(function () {
  "use strict";

  function $(id) {
    return document.getElementById(id);
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
          row.id +
          "</td><td>" +
          String(row.usable) +
          "</td><td>" +
          (row.effective || "") +
          "</td><td>" +
          (row.label || "") +
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
      const tbody = $("recommend-table").querySelector("tbody");
      tbody.innerHTML = "";
      for (const row of data.picks || []) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          row.rank +
          "</td><td><a href=\"#daily\">" +
          row.symbol +
          "</a></td><td>" +
          row.composite_score +
          "</td><td>" +
          row.close +
          "</td><td>" +
          (row.reason || "") +
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
      $("performance-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
      $("performance-json").textContent = "";
    }
  }

  async function listStrategies() {
    const errEl = $("strategy-error");
    clearError(errEl);
    try {
      const data = await fetchJson("/api/research/strategy/configs");
      $("strategy-meta").textContent = "configs=" + (data.configs ? data.configs.length : 0);
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
    $("lhb-form").addEventListener("submit", loadLhb);
    $("unlock-form").addEventListener("submit", loadUnlock);
    $("debate-form").addEventListener("submit", loadDebate);
    $("recommend-form").addEventListener("submit", loadRecommend);
    $("btn-recommend-paper").addEventListener("click", recommendToPaper);
    $("btn-recommend-debate").addEventListener("click", recommendDebate);
    $("btn-performance").addEventListener("click", loadPerformance);
    $("strategy-form").addEventListener("submit", compareStrategies);
    $("btn-strategy-list").addEventListener("click", listStrategies);
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
