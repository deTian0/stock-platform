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
      $("pref-status").textContent =
        "daily=" +
        (daily && daily.effective ? daily.effective : "") +
        " · fund_flow=" +
        (fundFlow && fundFlow.effective ? fundFlow.effective : "") +
        " · lhb=" +
        (lhb && lhb.effective ? lhb.effective : "");
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
          },
        }),
      });
      $("pref-status").textContent =
        "preferences updated → daily/realtime=" +
        daily +
        " fund_flow=" +
        fundFlow +
        " lhb=" +
        lhb;
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

  async function loadDebate(event) {
    if (event) event.preventDefault();
    const errEl = $("debate-error");
    clearError(errEl);
    $("debate-meta").textContent = "";
    const symbol = $("debate-symbol").value.trim();
    const asof = $("debate-asof").value;
    const params = new URLSearchParams({ symbol: symbol });
    if (asof) params.set("asof", asof);
    try {
      const data = await fetchJson("/api/debate/report?" + params.toString());
      $("debate-meta").textContent =
        "verdict=" + data.verdict + " · net=" + (data.score && data.score.net);
      $("debate-json").textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      showError(errEl, e.detail || String(e));
      $("debate-json").textContent = "";
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

  function boot() {
    $("btn-matrix").addEventListener("click", loadMatrix);
    $("btn-pref").addEventListener("click", applyPreference);
    $("btn-paper").addEventListener("click", loadPaper);
    $("daily-form").addEventListener("submit", loadDaily);
    $("fund-flow-form").addEventListener("submit", loadFundFlow);
    $("lhb-form").addEventListener("submit", loadLhb);
    $("debate-form").addEventListener("submit", loadDebate);
    loadMatrix();
    loadPaper();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
