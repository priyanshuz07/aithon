(function () {
  "use strict";

  const apiBase = String(window.ABF_API_BASE || "/api").replace(/\/$/, "");
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
  let activeSessionId = null;
  let refreshingOpenAnalysis = false;
  let activeBehaviorSimulation = null;
  let guidedDemoMode = null;
  let guidedDemoSessionId = null;
  let guidedDemoToken = 0;
  let guidedDemoSequence = 0;
  let guidedDemoRuns = [];
  const simulationResult = document.querySelector("#behavior-simulation-result");
  const simulationStatus = document.querySelector("#behavior-simulation-status");
  const stopSimulationButton = document.querySelector("#stop-behavior-simulation");
  const resetSimulationButton = document.querySelector("#reset-behavior-simulation");
  const simulationButtons = Array.from(document.querySelectorAll("[data-simulation-mode]"));
  const guidedModeButtons = Array.from(document.querySelectorAll("[data-guided-mode]"));
  const runGuidedAnalysisButton = document.querySelector("#run-guided-analysis");
  const resetGuidedDemoButton = document.querySelector("#reset-guided-demo");
  const guidedAnalysisOutput = document.querySelector("#guided-analysis-output");
  const guidedAnalysisStatus = document.querySelector("#guided-analysis-status");
  const guidedTimeline = document.querySelector("#guided-demo-timeline");
  const guidedDemoScenarios = {
    normal_user: {
      title: "NORMAL USER",
      status: "NORMAL",
      factors: [
        ["Request frequency", "LOW · 18 simulated requests/min"],
        ["Action repetition", "LOW · 1 repeated action"],
        ["Timing variation", "NORMAL · natural 1.8–3.2s pauses"],
        ["Navigation pattern", "NORMAL · 4 varied page transitions"],
      ],
      signals: [
        { name: "Low request baseline", points: 4, observation: "18 simulated requests/min; within this demo's routine range." },
        { name: "Low action repetition", points: 4, observation: "A single repeated control; no sustained repeat burst." },
        { name: "Routine navigation", points: 4, observation: "Several different demo pages visited at a measured pace." },
      ],
      timeline: [
        "Demo session started",
        "Natural browsing and clicks simulated",
        "Request frequency classified LOW",
        "Risk score calculated: 12/100",
        "Navigation and timing remain NORMAL",
        "Firewall policy selects ALLOW",
        "Final decision: ALLOW",
      ],
      explanation: "The scripted profile uses a low request rate, varied navigation, and realistic pauses. Its demo score remains below the review threshold, so the firewall allows the session.",
    },
    automated_bot: {
      title: "AUTOMATED BOT",
      status: "HIGH RISK",
      factors: [
        ["Request frequency", "HIGH · 164 simulated requests/min"],
        ["Action repetition", "HIGH · 31 repeated actions"],
        ["Timing variation", "LOW · near-identical 376ms intervals"],
        ["Navigation pattern", "ABNORMAL · same route repeated"],
      ],
      signals: [
        { name: "High request frequency", points: 24, observation: "A concentrated request burst in the scripted bot profile." },
        { name: "Repeated actions", points: 24, observation: "The same control is activated repeatedly." },
        { name: "Low timing variation", points: 22, observation: "Action intervals are unusually consistent and fast." },
        { name: "Abnormal navigation", points: 22, observation: "The scenario revisits the same page sequence." },
      ],
      timeline: [
        "Demo session started",
        "Rapid request burst simulated",
        "Repeated actions detected in the profile",
        "Low timing variation marked ABNORMAL",
        "Repeated navigation marked ABNORMAL",
        "High-risk threshold selects BLOCK",
        "Final decision: BLOCK",
      ],
      explanation: "This scripted bot combines frequent requests, repeated actions, highly regular timing, and a looping navigation path. The combined demo score exceeds the high-risk threshold, so the firewall blocks it.",
    },
    adaptive_bot: {
      title: "ADAPTIVE BOT",
      status: "SUSPICIOUS",
      factors: [
        ["Request frequency", "MEDIUM · 68 simulated requests/min"],
        ["Action repetition", "MEDIUM · 8 repeated actions"],
        ["Timing variation", "VARIABLE · intervals change between actions"],
        ["Navigation pattern", "ABNORMAL · route order changes with repeated transitions"],
      ],
      signals: [
        { name: "Variable request bursts", points: 18, observation: "Activity alternates between short bursts and quieter intervals." },
        { name: "Changing timing", points: 14, observation: "The scripted interval varies to avoid a single fixed cadence." },
        { name: "Intermittent action reuse", points: 10, observation: "Actions vary, with some controls reused later." },
        { name: "Unusual navigation transitions", points: 12, observation: "The path changes order but retains repeated transitions." },
      ],
      timeline: [
        "Demo session started",
        "Variable action timing simulated",
        "Request bursts alternate with pauses",
        "Risk score calculated: 54/100",
        "Changing sequence is harder to match, but repeat signals remain",
        "Medium-risk threshold selects REVIEW",
        "Final decision: REVIEW",
      ],
      explanation: "The adaptive profile varies its timing and action order, making simple repetition checks less decisive. Medium request volume and recurring navigation transitions still produce a suspicious demo score, so the firewall requests review instead of immediate block.",
    },
  };
  const simulationProfiles = {
    normal_user: {
      label: "NORMAL USER",
      steps: 8,
      interval: function (index) { return [3200, 3400, 3100, 3300, 3500, 3000, 3400][index % 7]; },
      hasClick: function (index) { return index === 0 || index === 3 || index === 6; },
      hasPageView: function (index) { return index === 0 || index === 4; },
      actionId: function (index) { return "normal.action." + index; },
      pageId: function (index) { return ["home", "catalog", "product", "support"][index % 4]; },
    },
    bot_attack: {
      label: "BOT ATTACK",
      steps: 32,
      interval: function () { return 330; },
      hasClick: function () { return true; },
      hasPageView: function (index) { return index % 4 === 0; },
      actionId: function () { return "bot.repeat.search"; },
      pageId: function () { return "bot.catalog"; },
    },
    adaptive_bot: {
      label: "ADAPTIVE BOT",
      steps: 24,
      intervals: [420, 1180, 660, 1450, 510, 930, 380, 1270, 740, 560, 1390, 810, 470, 1120, 630, 1510, 890, 520, 1330, 700, 980, 410, 1210],
      hasClick: function (index) { return index % 5 !== 3; },
      hasPageView: function (index) { return index % 3 !== 1; },
      actionId: function (index) {
        const actions = ["search", "open", "compare", "filter", "review", "return", "sort", "expand", "close", "view", "back", "next"];
        return "adaptive." + actions[(index * 5 + Math.floor(index / 4)) % actions.length];
      },
      pageId: function (index) { return "adaptive.page." + ((index * 7 + Math.floor(index / 4) * 3) % 11); },
    },
  };

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
        + "<td><code>" + escapeHtml(session.session_id.slice(0, 13)) + "</code>"
        + (session.simulation_mode ? '<span class="simulation-session-tag">SIM / ' + escapeHtml(humanize(session.simulation_mode)) + '</span>' : "") + "</td>"
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
        + '<span class="' + riskClass(session.risk_level) + '">' + escapeHtml(humanize(session.risk_level)) + '</span>'
        + '<span class="alert-decision"><small>FIREWALL</small><strong>' + escapeHtml(firewallDecisionLabel(session.response)) + '</strong></span></button>';
    }).join("");
  }

  function firewallDecisionLabel(action) {
    return action === "delay" ? "Review (delay)" : humanize(action);
  }

  function renderRecentEvents(data) {
    const events = data.recent_events || [];
    const container = document.querySelector("#recent-event-list");
    document.querySelector("#recent-event-count").textContent = events.length + " recent persisted events";
    if (!events.length) {
      container.innerHTML = '<div class="empty-state"><span class="empty-mark">--</span><p>No stored behavior events yet.</p></div>';
      return;
    }
    container.innerHTML = events.map(function (event) {
      return '<article class="recent-event-row"><time>' + escapeHtml(formatDate(event.time)) + '</time>'
        + '<span class="event-type-tag">' + escapeHtml(humanize(event.event_type)) + '</span>'
        + '<span class="recent-event-description">' + escapeHtml(event.description) + '</span>'
        + '<button type="button" class="recent-event-session" data-session-id="' + escapeHtml(event.session_id) + '"><code>' + escapeHtml(event.session_id.slice(0, 13)) + '</code>'
        + (event.simulation_mode ? '<small>SIM / ' + escapeHtml(humanize(event.simulation_mode)) + '</small>' : '') + '</button></article>';
    }).join("");
    container.querySelectorAll("[data-session-id]").forEach(function (button) {
      button.addEventListener("click", function () { openSession(button.dataset.sessionId); });
    });
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
    const riskPoints = data.risk_history || [];
    const riskEmpty = document.querySelector("#risk-history-empty");
    if (riskEmpty) riskEmpty.hidden = riskPoints.length > 0;
    const labels = riskPoints.map(function (point) {
       return new Date(point.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    });
    const lineOptions = chartOptions();
    lineOptions.elements = { line: { tension: 0.2, borderWidth: 2 }, point: { radius: 2, hoverRadius: 5 } };
    lineOptions.scales.y.min = 0;
    lineOptions.scales.y.max = 100;
    lineOptions.scales.y.ticks.stepSize = 20;
    renderChart("risk-history-chart", {
      type: "line",
      data: { labels: labels, datasets: [
        { label: "Risk score", data: riskPoints.map(function (point) { return point.risk_score; }), borderColor: "#77aaff", backgroundColor: "rgba(119,170,255,.12)", fill: true, tension: 0.2,
          pointBackgroundColor: riskPoints.map(function (point) { return point.risk_score >= 80 ? "#ff718e" : point.risk_score >= 60 ? "#ff9d73" : point.risk_score >= 30 ? "#e8b45c" : "#53d5c5"; }) },
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
    if (riskEmpty && riskPoints.length === 0) riskEmpty.hidden = false;
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
    document.querySelector("#overview-average-risk").textContent = data.average_risk_score == null ? "--" : data.average_risk_score;
    document.querySelector("#overview-normal").textContent = data.normal_sessions;
    document.querySelector("#overview-suspicious").textContent = data.suspicious_sessions;
    document.querySelector("#overview-blocked").textContent = data.blocked_sessions;
    document.querySelector("#overview-threats").textContent = data.threats_detected;
    document.querySelector("#overview-active").textContent = data.active_sessions;
    document.querySelector("#nav-session-count").textContent = data.active_sessions;
    document.querySelector("#nav-alert-count").textContent = data.suspicious_sessions;
    document.querySelector("#sidebar-api-state").textContent = data.monitoring_status.toUpperCase();
    document.querySelector(".sidebar-pulse").classList.toggle("is-offline", data.monitoring_status !== "online");
    document.querySelector("#monitoring-copy").textContent = data.monitoring_status === "online" ? "API and database connected" : "Monitoring unavailable";
    document.querySelector("#last-activity").textContent = data.latest_activity_at ? "Last activity " + formatDate(data.latest_activity_at) : "No recorded activity";
    document.querySelector("#api-state").textContent = data.monitoring_status.toUpperCase();
    document.querySelector("#api-state").className = "status-pill " + (data.monitoring_status === "online" ? "is-online" : "is-offline");
    const responses = data.response_distribution || {};
    document.querySelector("#decision-allow-count").textContent = responses.allow || 0;
    document.querySelector("#decision-review-count").textContent = responses.delay || 0;
    document.querySelector("#decision-challenge-count").textContent = responses.challenge || 0;
    document.querySelector("#decision-block-count").textContent = responses.block || 0;
    renderModelStatus(data.model_status || {});
  }

  function setBackendDashboardSectionsVisible(visible) {
    [".overview-section", "#traffic", "#sessions", "#alerts", "#recent-events", "#model", ".telemetry-tools"].forEach(function (selector) {
      const section = document.querySelector(selector);
      if (section) section.hidden = !visible;
    });
  }

  function render(data) {
    summary = data;
    setBackendDashboardSectionsVisible(true);
    setMessage("#dashboard-loading", "", false);
    setMessage("#dashboard-error", "", false);
    document.querySelector("#dashboard-content").hidden = false;
    renderOverview(data);
    renderCharts(data);
    renderSessions();
    renderAlerts();
    renderRecentEvents(data);
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

  function simulationUuid() {
    if (!window.crypto || typeof window.crypto.randomUUID !== "function") {
      throw new Error("This browser cannot create secure demo session IDs.");
    }
    return window.crypto.randomUUID();
  }

  function simulationEvent(type, payload) {
    return {
      event_id: simulationUuid(),
      type: type,
      at: new Date().toISOString(),
      payload: payload,
    };
  }

  function makeSimulationEvents(simulation, index) {
    const profile = simulationProfiles[simulation.mode];
    const events = [];
    if (index === 0) {
      events.push(simulationEvent("session.start", {
        sdk_session_id: simulation.sessionId,
        sdk_version: "simulation.1",
      }));
    }
    if (profile.hasClick(index)) {
      const actionId = profile.actionId(index);
      simulation.clickCount += 1;
      simulation.actionCounts[actionId] = (simulation.actionCounts[actionId] || 0) + 1;
      if (simulation.actionCounts[actionId] > 1) simulation.repeatedActionCount += 1;
      const now = Date.now();
      if (simulation.lastClickAt !== null) {
        simulation.interClickTotalMs += now - simulation.lastClickAt;
        simulation.interClickCount += 1;
      }
      simulation.lastClickAt = now;
      events.push(simulationEvent("interaction.click", { action_id: actionId }));
    }
    if (profile.hasPageView(index)) {
      simulation.pageVisitCount += 1;
      simulation.currentPage = profile.pageId(index);
      events.push(simulationEvent("navigation.page_view", { page: simulation.currentPage }));
    }
    simulation.requestCount += 1;
    events.push(simulationEvent("network.request", { resource_type: "fetch" }));
    return events;
  }

  function simulationSnapshot(simulation) {
    const durationMs = Math.max(1, Date.now() - simulation.startedAt);
    return {
      page: simulation.currentPage || "simulation",
      click_count: simulation.clickCount,
      page_visit_count: simulation.pageVisitCount,
      page_time_ms: durationMs,
      average_inter_click_ms: simulation.interClickCount
        ? Math.round(simulation.interClickTotalMs / simulation.interClickCount)
        : 0,
      form_submission_count: 0,
      repeated_action_count: simulation.repeatedActionCount,
      request_count: simulation.requestCount,
      request_frequency_per_minute: Number((simulation.requestCount * 60_000 / durationMs).toFixed(2)),
      session_duration_ms: durationMs,
      pending_event_count: 0,
    };
  }

  function renderBehaviorSimulation(simulation, analysis) {
    const signals = analysis.signals && analysis.signals.length
      ? '<ul class="demo-signal-list">' + analysis.signals.map(function (signal) {
        return '<li><span>' + escapeHtml(humanize(signal.name)) + '</span><strong>+' + escapeHtml(signal.points) + '</strong><small>' + escapeHtml(signal.observation) + '</small></li>';
      }).join("") + '</ul>'
      : '<p class="detail-empty">No risk rules have fired for the events received so far.</p>';
    const riskLabels = { low: "NORMAL", medium: "SUSPICIOUS", high: "HIGH RISK", critical: "HIGH RISK" };
    const riskStatus = riskLabels[analysis.risk_level] || humanize(analysis.risk_level);
    simulationResult.innerHTML = '<div class="simulation-result-head"><div><strong>' + escapeHtml(simulationProfiles[simulation.mode].label) + ' / DEMO SESSION</strong><code>' + escapeHtml(simulation.sessionId) + '</code></div>'
      + '<span class="simulation-demo-tag">SIMULATION</span></div>'
      + '<div class="simulation-result-summary"><div><span>Progress</span><strong>' + escapeHtml(simulation.completedSteps) + ' / ' + escapeHtml(simulationProfiles[simulation.mode].steps) + ' actions</strong></div>'
      + '<div><span>Risk score</span><strong>' + escapeHtml(analysis.risk_score) + ' / 100</strong></div>'
      + '<div><span>Status</span><strong>' + escapeHtml(riskStatus) + '</strong></div>'
      + '<div><span>Firewall decision</span><strong>' + escapeHtml(humanize(analysis.actual_response)) + '</strong></div></div>'
      + '<p class="simulation-result-explanation">' + escapeHtml(analysis.reason) + '</p>' + signals
      + '<div class="simulation-result-actions"><button type="button" data-open-simulation-session="' + escapeHtml(simulation.sessionId) + '">Open persisted session details</button></div>';
    simulationResult.querySelector("[data-open-simulation-session]").addEventListener("click", function () {
      openSession(simulation.sessionId);
    });
  }

  function waitForSimulation(ms, simulation) {
    return new Promise(function (resolve) {
      function finish() {
        simulation.timeout = null;
        simulation.resumeWait = null;
        resolve();
      }
      simulation.resumeWait = finish;
      simulation.timeout = window.setTimeout(finish, ms);
    });
  }

  async function runBehaviorSimulation(mode) {
    if (!simulationProfiles[mode]) return;
    if (activeBehaviorSimulation) stopBehaviorSimulation();
    const simulation = {
      mode: mode,
      sessionId: null,
      startedAt: Date.now(),
      clickCount: 0,
      pageVisitCount: 0,
      requestCount: 0,
      repeatedActionCount: 0,
      actionCounts: {},
      interClickTotalMs: 0,
      interClickCount: 0,
      lastClickAt: null,
      currentPage: "simulation",
      completedSteps: 0,
      stopped: false,
      timeout: null,
      resumeWait: null,
    };
    activeBehaviorSimulation = simulation;
    simulationButtons.forEach(function (button) { button.disabled = true; });
    stopSimulationButton.disabled = false;
    simulationStatus.textContent = "Creating a separate labeled demo session...";
    simulationResult.innerHTML = '<p class="loading-state">Starting ' + escapeHtml(simulationProfiles[mode].label) + ' event stream...</p>';

    try {
      const session = await apiRequest("/session/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: simulationUuid(),
          sdk_version: "simulation.1",
          simulation_mode: mode,
        }),
      });
      simulation.sessionId = session.session_id;
      simulation.startedAt = Date.parse(session.started_at) || Date.now();
      for (let index = 0; index < simulationProfiles[mode].steps; index += 1) {
        if (simulation.stopped) break;
        if (index > 0) {
          const interval = simulationProfiles[mode].intervals
            ? simulationProfiles[mode].intervals[(index - 1) % simulationProfiles[mode].intervals.length]
            : simulationProfiles[mode].interval(index - 1);
          await waitForSimulation(interval, simulation);
        }
        if (simulation.stopped) break;
        const events = makeSimulationEvents(simulation, index);
        await apiRequest("/events", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: simulation.sessionId,
            batch_id: simulationUuid(),
            events: events,
            features: simulationSnapshot(simulation),
          }),
        });
        simulation.completedSteps = index + 1;
        const analysis = await apiRequest("/session/" + encodeURIComponent(simulation.sessionId) + "/access");
        if (!simulation.stopped && activeBehaviorSimulation === simulation) {
          renderBehaviorSimulation(simulation, analysis);
          simulationStatus.textContent = simulation.completedSteps + " / " + simulationProfiles[mode].steps + " actions analyzed";
        }
      }
      if (!simulation.stopped && activeBehaviorSimulation === simulation) {
        simulationStatus.textContent = "Simulation complete · saved session " + simulation.sessionId.slice(0, 8);
      } else if (activeBehaviorSimulation === simulation) {
        simulationStatus.textContent = "Simulation stopped · saved session " + simulation.sessionId.slice(0, 8);
      }
    } catch (error) {
      if (activeBehaviorSimulation === simulation) {
        simulationResult.innerHTML = '<p class="error-state">Simulation stopped: ' + escapeHtml(error.message) + '</p>';
        simulationStatus.textContent = "Simulation could not complete";
      }
    } finally {
      if (activeBehaviorSimulation === simulation) {
        activeBehaviorSimulation = null;
        simulationButtons.forEach(function (button) { button.disabled = false; });
        stopSimulationButton.disabled = true;
        refreshDashboard();
      }
    }
  }

  function stopBehaviorSimulation() {
    const simulation = activeBehaviorSimulation;
    if (!simulation || simulation.stopped) return;
    simulation.stopped = true;
    stopSimulationButton.disabled = true;
    simulationStatus.textContent = "Stop requested; finishing the current API request...";
    if (simulation.resumeWait) simulation.resumeWait();
  }

  simulationButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      runBehaviorSimulation(button.dataset.simulationMode);
    });
  });
  stopSimulationButton.addEventListener("click", stopBehaviorSimulation);
  resetSimulationButton.addEventListener("click", function () {
    const simulation = activeBehaviorSimulation;
    if (simulation) {
      simulation.stopped = true;
      if (simulation.resumeWait) simulation.resumeWait();
      activeBehaviorSimulation = null;
    }
    simulationButtons.forEach(function (button) { button.disabled = false; });
    stopSimulationButton.disabled = true;
    simulationStatus.textContent = "Output reset; saved simulation sessions remain labeled in the dashboard.";
    simulationResult.innerHTML = '<p>Choose a mode to start another separately labeled demo session.</p>';
    refreshDashboard();
  });

  function createGuidedSessionId() {
    guidedDemoSequence += 1;
    return "DEMO-" + Date.now().toString(36).toUpperCase() + "-" + guidedDemoSequence.toString().padStart(3, "0");
  }

  function guidedRiskLevel(score) {
    return score < 30 ? "low" : score < 70 ? "medium" : "high";
  }

  function guidedRiskStatus(score) {
    return score < 30 ? "NORMAL" : score < 70 ? "SUSPICIOUS" : "HIGH RISK";
  }

  function guidedDecision(score) {
    return score < 30 ? "ALLOW" : score < 70 ? "REVIEW" : "BLOCK";
  }

  function guidedScore(scenario) {
    return scenario.signals.reduce(function (total, signal) { return total + signal.points; }, 0);
  }

  function guidedDecisionReason(scenario, score, action) {
    if (action === "ALLOW") return "LOW RISK · " + scenario.explanation;
    if (action === "BLOCK") return "HIGH RISK · " + scenario.explanation;
    return "MEDIUM RISK · " + scenario.explanation;
  }

  function renderGuidedPreview(mode) {
    const scenario = guidedDemoScenarios[mode];
    const score = guidedScore(scenario);
    const level = guidedRiskLevel(score);
    const action = guidedDecision(score);
    guidedModeButtons.forEach(function (button) {
      const selected = button.dataset.guidedMode === mode;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    document.querySelector("#guided-analysis-title").textContent = scenario.title.replace(/_/g, " ");
    document.querySelector("#guided-session-label").textContent = "DEMO / " + guidedDemoSessionId;
    guidedAnalysisOutput.innerHTML = '<div class="guided-analysis-meta"><span>SELECTED SIMULATION</span><code>' + escapeHtml(guidedDemoSessionId) + '</code></div>'
      + '<div class="guided-score-row"><div><span>Risk score</span><strong>' + score + '<small>/100</small></strong></div><span class="' + riskClass(level) + '">' + escapeHtml(guidedRiskStatus(score)) + '</span></div>'
      + '<div class="guided-factor-grid">' + scenario.factors.map(function (factor) {
        return '<div class="guided-factor"><strong>' + escapeHtml(factor[0]) + '</strong><span>' + escapeHtml(factor[1]) + '</span></div>';
      }).join("") + '</div>'
      + '<div class="guided-patterns"><h4>WHY WAS THIS FLAGGED? <small>DEMO ANALYSIS</small></h4><ul class="xai-signal-list">'
      + scenario.signals.map(function (signal) {
        return '<li><span><strong>' + escapeHtml(signal.name) + '</strong><small>' + escapeHtml(signal.observation) + '</small></span><b>+' + escapeHtml(signal.points) + '</b></li>';
      }).join("") + '</ul><p>' + escapeHtml(scenario.explanation) + '</p></div>';

    document.querySelector("#guided-decision-title").textContent = scenario.title;
    document.querySelector("#guided-decision-score").innerHTML = score + '<small>/100</small>';
    const decisionLevel = document.querySelector("#guided-decision-level");
    decisionLevel.textContent = guidedRiskStatus(score);
    decisionLevel.className = "status-pill " + (level === "low" ? "is-online" : level === "medium" ? "is-review" : "is-offline");
    const actionDisplay = document.querySelector("#guided-action-display");
    actionDisplay.textContent = action;
    actionDisplay.className = "guided-action-display decision-" + action.toLowerCase();
    document.querySelector("#guided-decision-reason").textContent = guidedDecisionReason(scenario, score, action);
    document.querySelectorAll("[data-guided-action]").forEach(function (element) {
      element.classList.toggle("is-selected", element.dataset.guidedAction === action);
    });
    runGuidedAnalysisButton.disabled = false;
    guidedAnalysisStatus.textContent = "Scenario preview ready · run analysis to add it to demo data.";
    guidedTimeline.innerHTML = '<li>Run Analysis to generate this scenario\'s simulated timeline.</li>';
    document.querySelectorAll("[data-flow-stage]").forEach(function (stage) {
      stage.classList.remove("is-current", "is-complete");
    });
  }

  function renderGuidedTimeline(events) {
    if (!events.length) {
      guidedTimeline.innerHTML = '<li>Timeline events will appear when analysis runs.</li>';
      return;
    }
    guidedTimeline.innerHTML = events.map(function (entry) {
      return '<li><time>' + escapeHtml(entry.time) + '</time><span>' + escapeHtml(entry.message) + '</span></li>';
    }).join("");
  }

  function renderGuidedDashboard() {
    const runs = guidedDemoRuns;
    const scores = runs.map(function (run) { return run.score; });
    const suspiciousRuns = runs.filter(function (run) { return run.score >= 30; });
    const blockedRuns = runs.filter(function (run) { return run.action === "BLOCK"; });
    const average = scores.length ? Math.round(scores.reduce(function (sum, score) { return sum + score; }, 0) / scores.length) : 0;
    document.querySelector("#demo-metric-sessions").textContent = runs.length;
    document.querySelector("#demo-metric-normal").textContent = runs.filter(function (run) { return run.score < 30; }).length;
    document.querySelector("#demo-metric-suspicious").textContent = suspiciousRuns.length;
    document.querySelector("#demo-metric-blocked").textContent = blockedRuns.length;
    document.querySelector("#demo-metric-average").textContent = average;
    document.querySelector("#demo-metric-threats").textContent = suspiciousRuns.length;

    const graph = document.querySelector("#demo-risk-graph");
    const chartRuns = runs.slice(0, 8).reverse();
    graph.innerHTML = chartRuns.length
      ? '<div class="demo-risk-bars">' + chartRuns.map(function (run) {
        return '<div class="demo-risk-column"><strong>' + run.score + '</strong><div class="demo-risk-track"><i class="demo-bar-' + escapeHtml(guidedRiskLevel(run.score)) + '" style="height:' + Math.max(4, run.score) + '%"></i></div><small>' + escapeHtml(run.modeLabel) + '</small></div>';
      }).join("") + '</div>'
      : '<p class="detail-empty">Run a scenario to plot its risk score.</p>';

    const actionNames = ["ALLOW", "REVIEW", "CHALLENGE", "BLOCK"];
    const actionCounts = actionNames.map(function (action) {
      return { action: action, count: runs.filter(function (run) { return run.action === action; }).length };
    });
    document.querySelector("#demo-action-stats").innerHTML = actionCounts.map(function (item) {
      return '<div class="demo-action-stat"><span class="decision-dot decision-dot-' + item.action.toLowerCase() + '"></span><strong>' + item.action + '</strong><b>' + item.count + '</b></div>';
    }).join("");

    const recentEvents = runs.flatMap(function (run) {
      return run.timeline.map(function (entry) { return Object.assign({ modeLabel: run.modeLabel }, entry); });
    }).slice(0, 8);
    document.querySelector("#demo-recent-events").innerHTML = recentEvents.length
      ? recentEvents.map(function (entry) {
        return '<li><time>' + escapeHtml(entry.time) + '</time><span>' + escapeHtml(entry.modeLabel) + '</span><strong>' + escapeHtml(entry.message) + '</strong></li>';
      }).join("")
      : '<li>Run Analysis to generate demo events.</li>';

    document.querySelector("#demo-session-list").innerHTML = runs.length
      ? '<div class="demo-session-list-head"><span>MODE / SESSION</span><span>SCORE</span><span>DECISION</span></div>'
        + runs.slice(0, 8).map(function (run) {
          return '<div class="demo-session-list-row"><span><strong>' + escapeHtml(run.modeLabel) + '</strong><code>' + escapeHtml(run.sessionId) + '</code></span><b>' + run.score + '/100</b><span class="demo-action-label decision-text-' + run.action.toLowerCase() + '">' + run.action + '</span></div>';
        }).join("")
      : '<p class="detail-empty">No demo sessions have been run.</p>';
  }

  async function runGuidedAnalysis() {
    if (!guidedDemoMode) return;
    const token = ++guidedDemoToken;
    const mode = guidedDemoMode;
    const scenario = guidedDemoScenarios[mode];
    const score = guidedScore(scenario);
    const action = guidedDecision(score);
    const now = Date.now();
    guidedDemoSessionId = createGuidedSessionId();
    renderGuidedPreview(mode);
    runGuidedAnalysisButton.disabled = true;
    guidedModeButtons.forEach(function (button) { button.disabled = true; });
    guidedAnalysisStatus.textContent = "Running scripted analysis stages...";
    const timeline = [];
    const flowStages = Array.from(document.querySelectorAll("[data-flow-stage]"));

    try {
      for (let stageIndex = 0; stageIndex < flowStages.length; stageIndex += 1) {
        if (token !== guidedDemoToken) return;
        flowStages.forEach(function (stage, index) {
          stage.classList.toggle("is-current", index === stageIndex);
          stage.classList.toggle("is-complete", index < stageIndex);
        });
        const event = {
          time: new Date(now + stageIndex * 1000).toLocaleTimeString(),
          message: scenario.timeline[stageIndex],
        };
        timeline.push(event);
        renderGuidedTimeline(timeline);
        guidedAnalysisStatus.textContent = "Analysis stage " + (stageIndex + 1) + " of " + flowStages.length + " · simulated";
        await new Promise(function (resolve) { window.setTimeout(resolve, 360); });
      }
      if (token !== guidedDemoToken) return;

      const run = {
        mode: mode,
        modeLabel: scenario.title,
        sessionId: guidedDemoSessionId,
        score: score,
        riskLevel: guidedRiskLevel(score),
        status: guidedRiskStatus(score),
        action: action,
        explanation: scenario.explanation,
        timeline: timeline,
        completedAt: new Date().toISOString(),
      };
      guidedDemoRuns.unshift(run);
      guidedDemoRuns = guidedDemoRuns.slice(0, 20);
      guidedAnalysisStatus.textContent = "Demo analysis complete · preset scenario result";
      renderGuidedDashboard();
    } finally {
      if (token === guidedDemoToken) {
        runGuidedAnalysisButton.disabled = false;
        guidedModeButtons.forEach(function (button) { button.disabled = false; });
      }
    }
  }

  guidedModeButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      if (button.disabled) return;
      guidedDemoMode = button.dataset.guidedMode;
      guidedDemoSessionId = createGuidedSessionId();
      renderGuidedPreview(guidedDemoMode);
    });
  });
  runGuidedAnalysisButton.addEventListener("click", runGuidedAnalysis);
  resetGuidedDemoButton.addEventListener("click", function () {
    guidedDemoToken += 1;
    guidedDemoMode = null;
    guidedDemoSessionId = null;
    guidedDemoRuns = [];
    guidedModeButtons.forEach(function (button) {
      button.disabled = false;
      button.classList.remove("is-selected");
      button.setAttribute("aria-pressed", "false");
    });
    runGuidedAnalysisButton.disabled = true;
    guidedAnalysisOutput.innerHTML = '<p class="detail-empty">Scenario signals, risk score, and explanation will appear here.</p>';
    document.querySelector("#guided-analysis-title").textContent = "Select a behavior mode";
    document.querySelector("#guided-session-label").textContent = "DEMO PROFILE";
    document.querySelector("#guided-decision-title").textContent = "Awaiting scenario";
    document.querySelector("#guided-decision-score").innerHTML = '--<small>/100</small>';
    document.querySelector("#guided-decision-level").textContent = "NO SCENARIO";
    document.querySelector("#guided-decision-level").className = "status-pill";
    document.querySelector("#guided-action-display").textContent = "SELECT A MODE";
    document.querySelector("#guided-action-display").className = "guided-action-display";
    document.querySelector("#guided-decision-reason").textContent = "The selected demo outcome will appear here.";
    document.querySelectorAll("[data-guided-action]").forEach(function (element) { element.classList.remove("is-selected"); });
    document.querySelectorAll("[data-flow-stage]").forEach(function (stage) { stage.classList.remove("is-current", "is-complete"); });
    guidedAnalysisStatus.textContent = "Demo reset · choose a scenario to begin again.";
    renderGuidedTimeline([]);
    renderGuidedDashboard();
  });
  renderGuidedDashboard();

  async function refreshDashboard() {
    if (busy) return;
    busy = true;
    refreshButton.disabled = true;
    refreshButton.setAttribute("aria-busy", "true");
    try {
      const data = await apiRequest("/dashboard/summary?limit=500");
      render(data);
    } catch (error) {
      document.querySelector("#dashboard-content").hidden = false;
      setBackendDashboardSectionsVisible(false);
      setMessage("#dashboard-loading", "", false);
      setMessage("#dashboard-error", error.message + ". Database-backed panels are unavailable; the local scripted Live Demo remains usable.", true);
    } finally {
      busy = false;
      refreshButton.disabled = false;
      refreshButton.removeAttribute("aria-busy");
      refreshOpenBehaviorAnalysis();
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

  function updateBehaviorAnalysis(data) {
    const container = detailContent.querySelector("#behavior-analysis-content");
    if (!container) return;

    const factorDefinitions = [
      ["request_frequency", "Request frequency", "level"],
      ["action_repetition", "Action repetition", "level"],
      ["timing_variation", "Timing variation", "status"],
      ["navigation_pattern", "Navigation pattern", "status"],
    ];
    const factorData = data.behavioral_factors || {};
    const factors = factorDefinitions.map(function (definition) {
      const factor = factorData[definition[0]] || {};
      const state = factor[definition[2]] || "insufficient_data";
      const stateLabel = state === "insufficient_data" ? "INSUFFICIENT DATA" : state.toUpperCase();
      const stateClass = state === "insufficient_data" ? "factor-insufficient" : "factor-" + state;
      return '<div class="xai-factor"><div><strong>' + escapeHtml(definition[1]) + '</strong><span class="' + stateClass + '">' + escapeHtml(stateLabel) + '</span></div>'
        + '<p>' + escapeHtml(factor.observation || "No stored evidence is available for this factor.") + '</p></div>';
    }).join("");
    const signals = data.rule_signals && data.rule_signals.length
      ? '<ul class="xai-signal-list">' + data.rule_signals.map(function (signal) {
        return '<li><span><strong>' + escapeHtml(humanize(signal.name)) + '</strong><small>' + escapeHtml(signal.observation) + '</small></span><b>+' + escapeHtml(signal.points) + '</b></li>';
      }).join("") + '</ul>'
      : '<p class="detail-empty">No score-increasing patterns were detected in the stored behavior.</p>';
    const modelNote = data.ml_prediction
      ? "The optional model uses synthetic training data; its probability is not a calibrated confidence value."
      : "No calibrated confidence value is produced by the rules-only analysis.";
    const recommendedAction = data.recommended_action || "not analyzed";
    const actualResponse = data.actual_response || "not analyzed";
    const riskLabels = { low: "NORMAL", medium: "SUSPICIOUS", high: "HIGH RISK", critical: "HIGH RISK" };
    const riskLevel = data.risk_level || "not_analyzed";
    const riskScore = data.risk_score == null ? "--" : String(data.risk_score);

    container.innerHTML = '<h4 class="xai-title">WHY WAS THIS FLAGGED?</h4>'
      + '<div class="xai-risk-summary"><span>Risk Score</span><strong>' + escapeHtml(riskScore) + '<small>/100</small></strong><span class="' + riskClass(riskLevel) + '">' + escapeHtml(riskLabels[riskLevel] || "NOT ANALYZED") + '</span></div>'
      + '<p class="xai-summary">' + escapeHtml(data.explanation || "No stored analysis explanation is available.") + '</p>'
      + '<div class="xai-factor-grid">' + factors + '</div>'
      + '<div class="behavior-analysis-patterns"><h4>Detected patterns and score contribution</h4>' + signals + '</div>'
      + '<div class="behavior-analysis-decision"><h4>Recommended firewall action</h4><div><span>Recommended</span><strong>' + escapeHtml(humanize(recommendedAction)) + '</strong>'
      + '<span>Applied</span><strong>' + escapeHtml(humanize(actualResponse)) + '</strong></div></div>'
      + '<p class="behavior-analysis-method">' + escapeHtml(modelNote) + '</p>';
  }

  async function refreshOpenBehaviorAnalysis() {
    const sessionId = activeSessionId;
    if (!sessionId || !detailDialog.open || refreshingOpenAnalysis) return;
    refreshingOpenAnalysis = true;
    try {
      const data = await apiRequest("/dashboard/sessions/" + encodeURIComponent(sessionId));
      if (activeSessionId === sessionId && detailDialog.open) updateBehaviorAnalysis(data);
    } catch (_) {
      // Keep the last persisted analysis visible if a refresh temporarily fails.
    } finally {
      refreshingOpenAnalysis = false;
    }
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
    const behaviorTimeline = data.behavior_timeline && data.behavior_timeline.length
      ? '<ol class="session-behavior-timeline">' + data.behavior_timeline.map(function (item) {
        return '<li><time>' + escapeHtml(formatDate(item.time)) + '</time><span class="event-type-tag">' + escapeHtml(humanize(item.event_type)) + '</span><strong>' + escapeHtml(item.description) + '</strong></li>';
      }).join("") + '</ol>'
      : '<p class="detail-empty">No behavior events have been recorded for this session.</p>';
    detailContent.innerHTML = '<div class="detail-head"><div><p class="eyebrow">SESSION RECORD</p><h2><code>' + escapeHtml(data.session_id) + '</code></h2>'
      + (data.simulation_mode ? '<span class="simulation-session-tag">DEMO / ' + escapeHtml(humanize(data.simulation_mode)) + '</span>' : "")
      + '<p class="muted">Started ' + escapeHtml(formatDate(data.started_at)) + '</p></div><span class="' + riskClass(data.risk_level) + '">' + escapeHtml(humanize(data.risk_level)) + '</span></div>'
      + '<div class="detail-score"><strong>' + escapeHtml(data.risk_score == null ? "--" : data.risk_score + "/100") + '</strong><span>' + escapeHtml(humanize(data.estimated_behavior_category)) + '</span></div>'
      + '<section class="detail-section behavior-analysis"><h3>BEHAVIOR ANALYSIS</h3><div id="behavior-analysis-content"></div></section>'
      + '<section class="detail-section"><h3>Behavioral features</h3><div class="feature-grid">' + featureRows(data.features) + '</div></section>'
      + '<section class="detail-section"><h3>Behavior timeline</h3>' + behaviorTimeline + '</section>'
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
    updateBehaviorAnalysis(data);
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
    activeSessionId = sessionId;
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
  detailDialog.addEventListener("close", function () { activeSessionId = null; });
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
    if (["10", "15", "30", "60", "0"].includes(savedInterval)) refreshSelect.value = savedInterval;
  } catch (_) { /* Default interval remains available. */ }
  setRefreshInterval(refreshSelect.value);
  refreshDashboard();
  if (window.lucide) window.lucide.createIcons();
})();
