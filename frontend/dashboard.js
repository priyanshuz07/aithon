(function () {
  "use strict";

  const apiBase = String(window.ABF_API_BASE || "http://127.0.0.1:8000/api").replace(/\/$/, "");
  const refreshSelect = document.querySelector("#refresh-interval");
  const sessionBody = document.querySelector("#session-table-body");
  const alertList = document.querySelector("#alert-list");
  const detailDialog = document.querySelector("#session-dialog");
  const detailContent = document.querySelector("#session-detail-content");
  const refreshButton = document.querySelector("#refresh-dashboard");
  const filterRisk = document.querySelector("#filter-risk");
  const filterResponse = document.querySelector("#filter-response");
  const filterFrom = document.querySelector("#filter-from");
  const filterTo = document.querySelector("#filter-to");
  const searchInput = document.querySelector("#session-search");
  const charts = {};
  let summary = null;
  let refreshTimer = null;
  let busy = false;

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }

  function humanize(value) {
    return String(value || "unknown").replace(/_/g, " ");
  }

  function formatDate(value) {
    if (!value) return "Not recorded";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString();
  }

  function setMessage(id, message, visible) {
    const element = document.querySelector(id);
    if (!element) return;
    element.textContent = message || "";
    element.hidden = !visible;
  }

  async function apiRequest(path, options) {
    const response = await fetch(apiBase + path, options);
    let data = {};
    try {
      data = await response.json();
    } catch (_) {
      data = {};
    }
    if (!response.ok) {
      throw new Error(data.detail || "API returned HTTP " + response.status);
    }
    return data;
  }

  function riskClass(level) {
    return "risk-tag risk-" + String(level || "unknown").replace(/[^a-z_]/g, "");
  }

  function sessionMatches(session) {
    const level = filterRisk.value;
    const response = filterResponse.value;
    const date = String(session.started_at || "").slice(0, 10);
    const query = searchInput.value.trim().toLowerCase();
    return (!level || session.risk_level === level)
      && (!response || session.response === response)
      && (!filterFrom.value || date >= filterFrom.value)
      && (!filterTo.value || date <= filterTo.value)
      && (!query || [session.session_id, session.estimated_behavior_category].join(" ").toLowerCase().includes(query));
  }

  function renderSessions() {
    const rows = (summary.sessions || []).filter(sessionMatches);
    if (!rows.length) {
      sessionBody.innerHTML = '<tr><td colspan="8" class="table-empty">No sessions match these filters.</td></tr>';
      document.querySelector("#session-count-label").textContent = "0 sessions shown";
      return;
    }
    sessionBody.innerHTML = rows.map(function (session) {
      const score = session.risk_score == null ? "--" : session.risk_score + "/100";
      return '<tr tabindex="0" role="button" data-session-id="' + escapeHtml(session.session_id) + '">'
        + "<td><code>" + escapeHtml(session.session_id.slice(0, 13)) + "</code></td>"
        + "<td>" + escapeHtml(formatDate(session.started_at)) + "</td>"
        + "<td>" + escapeHtml(session.click_count) + "</td>"
        + "<td>" + escapeHtml(Number(session.request_frequency_per_minute || 0).toFixed(1)) + " / min</td>"
        + '<td class="score-cell">' + escapeHtml(score) + "</td>"
        + '<td class="category-cell">' + escapeHtml(humanize(session.estimated_behavior_category)) + "</td>"
        + '<td><span class="' + riskClass(session.risk_level) + '">' + escapeHtml(humanize(session.risk_level)) + "</span></td>"
        + '<td><span class="response-tag">' + escapeHtml(humanize(session.response)) + "</span></td></tr>";
    }).join("");
    document.querySelector("#session-count-label").textContent = rows.length + " of " + summary.total_sessions + " sessions";
  }

  function renderAlerts() {
    const alerts = (summary.sessions || []).filter(function (session) {
      return ["medium", "high", "critical"].includes(session.risk_level) && sessionMatches(session);
    });
    if (!alerts.length) {
      alertList.innerHTML = '<div class="empty-state"><span class="empty-mark">OK</span><p>No suspicious sessions match the selected filters.</p></div>';
      return;
    }
    alertList.innerHTML = alerts.slice(0, 12).map(function (session) {
      return '<button class="alert-row" type="button" data-session-id="' + escapeHtml(session.session_id) + '">'
        + '<span class="alert-indicator ' + riskClass(session.risk_level) + '"></span>'
        + '<span class="alert-copy"><strong>' + escapeHtml(humanize(session.estimated_behavior_category)) + '</strong>'
        + '<span><code>' + escapeHtml(session.session_id.slice(0, 16)) + '</code> · ' + escapeHtml(formatDate(session.started_at)) + '</span></span>'
        + '<span class="alert-score">' + escapeHtml(session.risk_score == null ? "--" : session.risk_score + "/100") + '</span>'
        + '<span class="' + riskClass(session.risk_level) + '">' + escapeHtml(humanize(session.risk_level)) + '</span></button>';
    }).join("");
  }

  function renderChart(canvasId, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof window.Chart !== "function") return;
    if (charts[canvasId]) charts[canvasId].destroy();
    charts[canvasId] = new window.Chart(canvas, config);
  }

  let chartResizeFrame = 0;
  window.addEventListener("resize", function () {
    if (chartResizeFrame) window.cancelAnimationFrame(chartResizeFrame);
    chartResizeFrame = window.requestAnimationFrame(function () {
      Object.values(charts).forEach(function (chart) {
        const container = chart.canvas.parentElement;
        chart.resize(container.clientWidth, container.clientHeight);
      });
      chartResizeFrame = 0;
    });
  });

  function chartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { labels: { color: "#aab7ce", usePointStyle: true, boxWidth: 7, padding: 16, font: { family: "IBM Plex Mono", size: 10 } } },
        tooltip: { backgroundColor: "#111a2a", borderColor: "#33415b", borderWidth: 1, titleColor: "#edf3ff", bodyColor: "#aab7ce", padding: 10 },
      },
      scales: {
        x: { grid: { color: "rgba(125, 146, 180, .09)" }, ticks: { color: "#7f8da7", maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: { size: 9 } }, border: { display: false } },
        y: { beginAtZero: true, grid: { color: "rgba(125, 146, 180, .09)" }, ticks: { color: "#7f8da7", precision: 0, font: { size: 9 } }, border: { display: false } },
      },
    };
  }

  function renderCharts(data) {
    const points = data.sessions_over_time || [];
    const labels = points.map(function (point) {
      return new Date(point.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    });
    const lineOptions = chartOptions();
    lineOptions.elements = { line: { tension: 0.32, borderWidth: 2 }, point: { radius: 0, hoverRadius: 4 } };
    lineOptions.scales.y.stacked = true;
    renderChart("sessions-chart", {
      type: "line",
      data: { labels: labels, datasets: [
        { label: "Normal", data: points.map(function (point) { return point.normal; }), borderColor: "#53d5c5", backgroundColor: "rgba(83,213,197,.08)", fill: true, stack: "sessions" },
        { label: "Suspicious", data: points.map(function (point) { return point.suspicious; }), borderColor: "#a991ff", backgroundColor: "rgba(169,145,255,.12)", fill: true, stack: "sessions" },
      ] },
      options: lineOptions,
    });

    const doughnutOptions = {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "70%",
      plugins: {
        legend: { position: "bottom", labels: { color: "#aab7ce", usePointStyle: true, boxWidth: 7, padding: 13, font: { family: "IBM Plex Mono", size: 9 } } },
        tooltip: chartOptions().plugins.tooltip,
      },
    };
    const risk = data.risk_distribution || {};
    renderChart("risk-chart", {
      type: "doughnut",
      data: { labels: ["Low", "Medium", "High", "Critical", "Not analyzed"], datasets: [{
        data: [risk.low || 0, risk.medium || 0, risk.high || 0, risk.critical || 0, risk.not_analyzed || 0],
        backgroundColor: ["#53d5c5", "#e8b45c", "#ff8a68", "#fb6687", "#35435e"],
        borderWidth: 0,
        spacing: 3,
      }] },
      options: doughnutOptions,
    });
    const response = data.response_distribution || {};
    renderChart("response-chart", {
      type: "doughnut",
      data: { labels: ["Allow", "Challenge", "Delay", "Block", "Not analyzed"], datasets: [{
        data: [response.allow || 0, response.challenge || 0, response.delay || 0, response.block || 0, response.not_analyzed || 0],
        backgroundColor: ["#53d5c5", "#77aaff", "#a991ff", "#fb6687", "#35435e"],
        borderWidth: 0,
        spacing: 3,
      }] },
      options: doughnutOptions,
    });
    document.querySelectorAll(".chart-unavailable").forEach(function (element) {
      element.hidden = typeof window.Chart === "function";
    });
  }

  function renderModelStatus(model) {
    document.querySelector("#model-loaded").textContent = model.loaded ? "LOADED" : "NOT CONFIGURED";
    document.querySelector("#model-loaded").className = "status-pill " + (model.loaded ? "is-online" : "is-offline");
    document.querySelector("#model-type").textContent = model.model_type || "Not reported";
    document.querySelector("#model-dataset").textContent = model.training_dataset_type || "Not reported";
    document.querySelector("#model-training").textContent = model.last_training_status || "Not reported";
    const metrics = model.evaluation_metrics;
    document.querySelector("#model-metrics").textContent = metrics
      ? Object.entries(metrics).map(function (entry) { return entry[0] + ": " + entry[1]; }).join(" · ")
      : "No evaluation metrics reported";
    document.querySelector("#model-indicator").classList.toggle("model-ready", Boolean(model.loaded));
    document.querySelector("#model-note").textContent = model.metrics_note
      || "Synthetic evaluation metrics do not establish real-world accuracy.";
  }

  function renderOverview(data) {
    document.querySelector("#overview-total").textContent = data.total_sessions;
    document.querySelector("#overview-normal").textContent = data.normal_sessions;
    document.querySelector("#overview-suspicious").textContent = data.suspicious_sessions;
    document.querySelector("#overview-high-risk").textContent = data.high_risk_sessions;
    document.querySelector("#overview-blocked").textContent = data.blocked_sessions;
    document.querySelector("#overview-active").textContent = data.active_sessions;
    document.querySelector("#nav-session-count").textContent = data.active_sessions;
    document.querySelector("#nav-alert-count").textContent = data.suspicious_sessions;
    document.querySelector("#sidebar-api-state").textContent = data.monitoring_status.toUpperCase();
    document.querySelector(".sidebar-pulse").classList.toggle("is-offline", data.monitoring_status !== "online");
    document.querySelector("#monitoring-copy").textContent = data.monitoring_status === "online" ? "API and database connected" : "Monitoring unavailable";
    document.querySelector("#last-activity").textContent = data.latest_activity_at ? "Last activity " + formatDate(data.latest_activity_at) : "No recorded activity";
    document.querySelector("#api-state").textContent = data.monitoring_status.toUpperCase();
    document.querySelector("#api-state").className = "status-pill " + (data.monitoring_status === "online" ? "is-online" : "is-offline");
    renderModelStatus(data.model_status || {});
  }

  function render(data) {
    summary = data;
    setMessage("#dashboard-loading", "", false);
    setMessage("#dashboard-error", "", false);
    document.querySelector("#dashboard-content").hidden = false;
    renderOverview(data);
    renderCharts(data);
    renderSessions();
    renderAlerts();
    document.querySelector("#last-updated").textContent = "Updated " + new Date().toLocaleTimeString();
  }

  function renderDemoScenario(result) {
    const signals = result.signals.length
      ? '<ul class="demo-signal-list">' + result.signals.map(function (signal) {
        return '<li><span>' + escapeHtml(humanize(signal.name)) + '</span><strong>+' + escapeHtml(signal.points) + '</strong><small>' + escapeHtml(signal.observation) + '</small></li>';
      }).join("") + '</ul>'
      : '<p class="detail-empty">No configured risk signals were triggered.</p>';
    const model = result.ml_prediction
      ? '<p class="demo-model-note">ML: ' + escapeHtml(result.ml_prediction.prediction) + ' (' + escapeHtml((result.ml_prediction.suspicious_probability * 100).toFixed(1)) + '% synthetic-model probability)</p>'
      : '<p class="demo-model-note">ML: unavailable; rules-only response.</p>';
    const level = humanize(result.risk_level);
    demoScenarioResult.innerHTML = '<div class="demo-result-heading"><div><p class="eyebrow">' + escapeHtml(result.scenario_title) + '</p><h3>Session <code>' + escapeHtml(result.session_id) + '</code></h3></div>'
      + '<strong class="demo-score ' + riskClass(result.risk_level) + '">' + escapeHtml(result.score) + '<small>/100 · ' + escapeHtml(level) + '</small></strong></div>'
      + '<div class="demo-outcome"><span>Estimated pattern</span><strong>' + escapeHtml(humanize(result.estimated_behavioral_category)) + '</strong><span>Recommended / actual</span><strong>' + escapeHtml(humanize(result.recommended_action)) + ' / ' + escapeHtml(humanize(result.actual_response)) + '</strong></div>'
      + '<p class="demo-explanation">' + escapeHtml(result.explanation) + '</p>' + model + signals
      + '<button type="button" class="text-link demo-open-session" data-session-id="' + escapeHtml(result.session_id) + '">Open persisted session details</button>';
    demoScenarioResult.querySelector(".demo-open-session").addEventListener("click", function () {
      openSession(result.session_id);
    });
    if (window.lucide) window.lucide.createIcons({ root: demoScenarioResult });
  }

  const demoScenarioResult = document.querySelector("#demo-scenario-result");
  document.querySelectorAll("[data-demo-scenario]").forEach(function (button) {
    button.addEventListener("click", async function () {
      button.disabled = true;
      demoScenarioResult.innerHTML = '<p class="loading-state">Creating synthetic session and evaluating the current model/rules…</p>';
      try {
        const result = await apiRequest("/demo/scenarios/" + encodeURIComponent(button.dataset.demoScenario), {
          method: "POST",
        });
        renderDemoScenario(result);
        await refreshDashboard();
      } catch (error) {
        demoScenarioResult.innerHTML = '<p class="error-state">' + escapeHtml(error.message) + '</p>';
      } finally {
        button.disabled = false;
      }
    });
  });

  async function refreshDashboard() {
    if (busy) return;
    busy = true;
    refreshButton.disabled = true;
    refreshButton.setAttribute("aria-busy", "true");
    try {
      const data = await apiRequest("/dashboard/summary?limit=500");
      render(data);
    } catch (error) {
      document.querySelector("#dashboard-content").hidden = true;
      setMessage("#dashboard-loading", "", false);
      setMessage("#dashboard-error", error.message + ". Check that the local API is running, then retry.", true);
    } finally {
      busy = false;
      refreshButton.disabled = false;
      refreshButton.removeAttribute("aria-busy");
    }
  }

  function setRefreshInterval(value) {
    if (refreshTimer) window.clearInterval(refreshTimer);
    refreshTimer = null;
    try { localStorage.setItem("abf.dashboard.refresh", value); } catch (_) { /* Keep this tab usable without storage. */ }
    if (value !== "0") refreshTimer = window.setInterval(refreshDashboard, Number(value) * 1000);
    document.querySelector("#refresh-state").textContent = value === "0" ? "Auto refresh off" : "Auto refresh every " + value + "s";
  }

  function featureRows(features) {
    if (!features) return '<p class="detail-empty">No behavioral snapshot has been stored.</p>';
    const rows = [
      ["Clicks", features.click_count],
      ["Average click interval", (features.average_inter_click_ms || 0) + " ms"],
      ["Page visits", features.page_visit_count],
      ["Time on page", ((features.page_time_ms || 0) / 1000).toFixed(1) + " s"],
      ["Form submissions", features.form_submission_count],
      ["Repeated actions", features.repeated_action_count],
      ["Observed requests", features.request_count],
      ["Request frequency", Number(features.request_frequency_per_minute || 0).toFixed(1) + " / min"],
      ["Session duration", ((features.session_duration_ms || 0) / 1000).toFixed(1) + " s"],
    ];
    return rows.map(function (row) { return '<div class="feature-row"><span>' + escapeHtml(row[0]) + '</span><strong>' + escapeHtml(row[1]) + '</strong></div>'; }).join("");
  }

  function renderDetails(data) {
    const signals = data.rule_signals && data.rule_signals.length
      ? '<ul class="signal-list">' + data.rule_signals.map(function (signal) {
        return '<li><span><strong>' + escapeHtml(humanize(signal.name)) + '</strong><small>' + escapeHtml(signal.observation) + '</small></span><b>+' + escapeHtml(signal.points) + '</b></li>';
      }).join("") + '</ul>'
      : '<p class="detail-empty">No rule-based signals increased this score.</p>';
    const metrics = data.ml_prediction
      ? '<pre class="ml-output">' + escapeHtml(JSON.stringify(data.ml_prediction, null, 2)) + '</pre>'
      : '<p class="detail-empty">No ML prediction available. The workspace does not contain a loaded ML model.</p>';
    const history = data.decision_history && data.decision_history.length
      ? '<div class="decision-history">' + data.decision_history.map(function (decision) {
        return '<article class="decision-history-row"><div class="history-time">' + escapeHtml(formatDate(decision.created_at)) + '<span>' + escapeHtml(humanize(decision.decision_source)) + '</span></div>'
          + '<div><span class="history-actions"><strong>' + escapeHtml(humanize(decision.recommended_action)) + '</strong><i data-lucide="arrow-right"></i><strong>' + escapeHtml(humanize(decision.actual_response)) + '</strong></span>'
          + '<p>' + escapeHtml(decision.reason) + '</p>'
          + (decision.reviewed_by ? '<small>Reviewed by ' + escapeHtml(decision.reviewed_by) + (decision.review_notes ? ': ' + escapeHtml(decision.review_notes) : '') + '</small>' : '')
          + '</div><code>' + escapeHtml(decision.request_id.slice(0, 8)) + '</code></article>';
      }).join("") + '</div>'
      : '<p class="detail-empty">No response decisions have been recorded.</p>';
    detailContent.innerHTML = '<div class="detail-head"><div><p class="eyebrow">SESSION RECORD</p><h2><code>' + escapeHtml(data.session_id) + '</code></h2><p class="muted">Started ' + escapeHtml(formatDate(data.started_at)) + '</p></div><span class="' + riskClass(data.risk_level) + '">' + escapeHtml(humanize(data.risk_level)) + '</span></div>'
      + '<div class="detail-score"><strong>' + escapeHtml(data.risk_score == null ? "--" : data.risk_score + "/100") + '</strong><span>' + escapeHtml(humanize(data.estimated_behavior_category)) + '</span></div>'
      + '<section class="detail-section"><h3>Behavioral features</h3><div class="feature-grid">' + featureRows(data.features) + '</div></section>'
      + '<section class="detail-section"><h3>Rule-based signals</h3>' + signals + '</section>'
      + '<section class="detail-section"><h3>Score explanation</h3><p class="detail-explanation">' + escapeHtml(data.explanation) + '</p></section>'
      + '<section class="detail-section"><h3>Machine-learning prediction</h3>' + metrics + '</section>'
      + '<div class="detail-actions"><div><span>Recommended action</span><strong>' + escapeHtml(humanize(data.recommended_action)) + '</strong></div><div><span>Recorded response</span><strong>' + escapeHtml(humanize(data.actual_response)) + '</strong><small>' + escapeHtml(data.enforcement_status) + '</small></div></div>'
      + '<section class="detail-section"><h3>Session decision history</h3>' + history + '</section>'
      + '<section class="detail-section admin-review-panel"><h3>Administrator review</h3><p class="detail-empty">Requires the server-configured administrator API key. Review actions are appended to history.</p>'
      + '<label for="admin-api-key">Admin API key</label><input id="admin-api-key" type="password" autocomplete="off" spellcheck="false">'
      + '<label for="admin-response">Actual response</label><select id="admin-response"><option value="allow">Allow</option><option value="challenge">Challenge</option><option value="delay">Delay</option><option value="block">Block</option></select>'
      + '<label for="admin-review-notes">Review notes</label><textarea id="admin-review-notes" maxlength="1000" rows="2"></textarea>'
      + '<button id="submit-admin-review" class="button button-outline" type="button">Record review</button><p id="admin-review-status" class="review-status" role="status" aria-live="polite"></p></section>';
    detailContent.querySelector("#admin-response").value = ["allow", "challenge", "delay", "block"].includes(data.recommended_action)
      ? data.recommended_action
      : data.actual_response;
    detailContent.querySelector("#submit-admin-review").addEventListener("click", async function (event) {
      const button = event.currentTarget;
      const statusElement = detailContent.querySelector("#admin-review-status");
      const adminKey = detailContent.querySelector("#admin-api-key").value;
      button.disabled = true;
      statusElement.textContent = "Submitting review...";
      try {
        await apiRequest("/admin/sessions/" + encodeURIComponent(data.session_id) + "/review", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: "Bearer " + adminKey },
          body: JSON.stringify({
            actual_response: detailContent.querySelector("#admin-response").value,
            notes: detailContent.querySelector("#admin-review-notes").value,
          }),
        });
        const refreshed = await apiRequest("/dashboard/sessions/" + encodeURIComponent(data.session_id));
        renderDetails(refreshed);
        detailContent.querySelector("#admin-review-status").textContent = "Review recorded in the decision history.";
        detailContent.querySelector("#admin-api-key").value = "";
        refreshDashboard();
      } catch (error) {
        statusElement.textContent = error.message;
        button.disabled = false;
      }
    });
    if (window.lucide) window.lucide.createIcons({ root: detailContent });
  }

  async function openSession(sessionId) {
    detailContent.innerHTML = '<div class="loading-state">Loading stored session details…</div>';
    if (typeof detailDialog.showModal === "function") detailDialog.showModal();
    try {
      let details = await apiRequest("/dashboard/sessions/" + encodeURIComponent(sessionId));
      const isPublicId = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(sessionId);
      const needsAnalysis = isPublicId && (
        details.risk_score == null
        || Date.parse(details.last_seen_at) > Date.parse(details.last_analysis_at || "1970-01-01T00:00:00Z")
      );
      if (needsAnalysis) {
        detailContent.innerHTML = '<div class="loading-state">Analyzing the latest stored behavior…</div>';
        await apiRequest("/session/" + encodeURIComponent(sessionId) + "/analyze", { method: "POST" });
        details = await apiRequest("/dashboard/sessions/" + encodeURIComponent(sessionId));
        window.setTimeout(refreshDashboard, 0);
      }
      renderDetails(details);
    } catch (error) {
      detailContent.innerHTML = '<div class="error-state">' + escapeHtml(error.message) + '</div>';
    }
  }

  function activateSessionRow(event) {
    const row = event.target.closest("[data-session-id]");
    if (row) openSession(row.dataset.sessionId);
  }

  sessionBody.addEventListener("click", activateSessionRow);
  sessionBody.addEventListener("keydown", function (event) {
    if ((event.key === "Enter" || event.key === " ") && event.target.matches("[data-session-id]")) {
      event.preventDefault();
      openSession(event.target.dataset.sessionId);
    }
  });
  alertList.addEventListener("click", activateSessionRow);
  [filterRisk, filterResponse, filterFrom, filterTo, searchInput].forEach(function (control) {
    control.addEventListener("input", function () {
      if (summary) { renderSessions(); renderAlerts(); }
    });
    control.addEventListener("change", function () {
      if (summary) { renderSessions(); renderAlerts(); }
    });
  });
  document.querySelector("#clear-filters").addEventListener("click", function () {
    filterRisk.value = "";
    filterResponse.value = "";
    filterFrom.value = "";
    filterTo.value = "";
    searchInput.value = "";
    if (summary) { renderSessions(); renderAlerts(); }
  });
  document.querySelector("#close-session-dialog").addEventListener("click", function () { detailDialog.close(); });
  detailDialog.addEventListener("click", function (event) {
    if (event.target === detailDialog) detailDialog.close();
  });
  refreshButton.addEventListener("click", refreshDashboard);
  refreshSelect.addEventListener("change", function () { setRefreshInterval(refreshSelect.value); });

  const sectionLinks = Array.from(document.querySelectorAll(".dashboard-nav a"));
  sectionLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      sectionLinks.forEach(function (item) { item.classList.toggle("is-active", item === link); });
    });
  });
  if ("IntersectionObserver" in window) {
    const sectionObserver = new IntersectionObserver(function (entries) {
      const visible = entries.filter(function (entry) { return entry.isIntersecting; })
        .sort(function (left, right) { return right.intersectionRatio - left.intersectionRatio; })[0];
      if (!visible) return;
      sectionLinks.forEach(function (link) {
        link.classList.toggle("is-active", link.hash === "#" + visible.target.id);
      });
    }, { rootMargin: "-15% 0px -68% 0px", threshold: [0, 0.15, 0.4] });
    ["overview", "traffic", "sessions", "alerts", "model", "demo-lab"].forEach(function (id) {
      const section = document.getElementById(id);
      if (section) sectionObserver.observe(section);
    });
  }

  try {
    const savedInterval = localStorage.getItem("abf.dashboard.refresh");
    if (["15", "30", "60", "0"].includes(savedInterval)) refreshSelect.value = savedInterval;
  } catch (_) { /* Default interval remains available. */ }
  setRefreshInterval(refreshSelect.value);
  refreshDashboard();
  if (window.lucide) window.lucide.createIcons();
})();
