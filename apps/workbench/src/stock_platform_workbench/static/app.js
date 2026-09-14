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
        $("pref-status").textContent = "daily effective=" + daily.effective;
      }
    } catch (e) {
      showError(errEl, e.detail || String(e));
    }
  }

  async function applyPreference() {
    const errEl = $("matrix-error");
    clearError(errEl);
    const daily = $("pref-daily").value;
    try {
      await fetchJson("/api/settings/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: { daily: daily, realtime: daily } }),
      });
      $("pref-status").textContent = "preferences updated → " + daily;
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

  function boot() {
    $("btn-matrix").addEventListener("click", loadMatrix);
    $("btn-pref").addEventListener("click", applyPreference);
    $("btn-paper").addEventListener("click", loadPaper);
    $("daily-form").addEventListener("submit", loadDaily);
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
