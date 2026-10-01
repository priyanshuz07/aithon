(function () {
  "use strict";

  const apiBase = window.ABF_API_BASE || "/api";
  if (window.ABFAdaptiveAccess) window.ABFAdaptiveAccess.initialize();
  const monitor = window.ABFBehaviorSDK.create({
    apiBaseUrl: apiBase,
    flushIntervalMs: 5000,
    onStatus: updateCollectorStatus,
  });
  window.ABFBehaviorMonitor = monitor;

  function updateCollectorStatus(state) {
    document.querySelectorAll("[data-sdk-status]").forEach(function (element) {
      element.textContent = state.status === "online" ? "MONITORING LIVE" : state.status.toUpperCase();
    });
    const notice = document.querySelector("[data-monitor-notice-copy]");
    if (notice) {
      notice.textContent = state.status === "disabled"
        ? "Behavior monitoring is paused on this page. No new activity is being collected."
        : "Behavior monitoring is active for this demo. We measure action counts and timing only; typed and sensitive form values are never collected.";
    }
    const collector = document.querySelector("#collector-status");
    if (collector) {
      collector.textContent = state.status.toUpperCase();
      collector.classList.toggle("is-offline", state.status === "offline");
      collector.classList.toggle("is-online", state.status === "online");
    }
  }

  async function checkHealth() {
    const indicator = document.querySelector("#home-api-orb, #api-orb");
    const label = document.querySelector("#home-api-label, #api-label");
    const detail = document.querySelector("#home-api-detail, #api-detail");
    if (!indicator || !label || !detail) return;

    try {
      const response = await fetch(apiBase + "/health");
      if (!response.ok) throw new Error("HTTP " + response.status);
      const health = await response.json();
      indicator.className = "status-orb online";
      label.textContent = "API ONLINE";
      detail.textContent = "SQLite " + health.database;
    } catch (_) {
      indicator.className = "status-orb offline";
      label.textContent = "API OFFLINE";
      detail.textContent = "Start the FastAPI service on port 8000 to receive events.";
    }
  }

  function initializeSearch() {
    const search = document.querySelector("#product-search");
    if (!search) return;
    const cards = Array.from(document.querySelectorAll("[data-product-card]"));
    const result = document.querySelector("#search-result");
    const empty = document.querySelector("#empty-state");
    search.addEventListener("input", function () {
      const query = search.value.trim().toLowerCase();
      let visible = 0;
      cards.forEach(function (card) {
        const matches = !query || (card.dataset.search || "").includes(query) || card.textContent.toLowerCase().includes(query);
        card.hidden = !matches;
        if (matches) visible += 1;
      });
      result.textContent = "Showing " + visible + " of " + cards.length + " devices";
      empty.hidden = visible !== 0;
    });
  }

  function initializeCart() {
    const cartKey = "abf.demo_lab_kit_count";
    let count = 0;
    try {
      count = Number(sessionStorage.getItem(cartKey)) || 0;
    } catch (_) {
      count = 0;
    }
    function updateCount() {
      document.querySelectorAll("#cart-count").forEach(function (element) {
        element.textContent = String(count);
      });
    }
    updateCount();
    document.querySelectorAll("[data-add-product]").forEach(function (button) {
      button.addEventListener("click", function () {
        count += 1;
        try {
          sessionStorage.setItem(cartKey, String(count));
        } catch (_) {
          // The in-page count remains functional when storage is unavailable.
        }
        updateCount();
        button.innerHTML = "Added <span aria-hidden=\"true\">✓</span>";
        window.setTimeout(function () {
          button.innerHTML = "Add to lab <span aria-hidden=\"true\">+</span>";
        }, 1100);
      });
    });
  }

  function initializeForms() {
    document.querySelectorAll("[data-demo-form]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        const feedback = form.id === "demo-login"
          ? document.querySelector("#login-feedback")
          : document.querySelector("#activity-feedback");
        if (feedback) feedback.textContent = "Demo submitted locally. No form values were sent.";
        form.reset();
      });
    });
  }

  function initializeDashboard() {
    const dashboard = document.querySelector(".dashboard-main");
    if (!dashboard) return;
    const sessionId = document.querySelector("#session-id");
    const flushButton = document.querySelector("#flush-events");
    const disableButton = document.querySelector("#disable-monitoring");

    function renderMetrics() {
      const data = monitor.getSnapshot();
      sessionId.textContent = monitor.getSessionId().slice(0, 8).toUpperCase();
      document.querySelector("#metric-page-visits").textContent = data.page_visit_count;
      document.querySelector("#metric-clicks").textContent = data.click_count;
      document.querySelector("#metric-forms").textContent = data.form_submission_count;
      document.querySelector("#metric-repeats").textContent = data.repeated_action_count;
      document.querySelector("#metric-interval").innerHTML = data.average_inter_click_ms + '<span class="metric-unit">ms</span>';
      document.querySelector("#metric-page-time").innerHTML = Math.floor(data.page_time_ms / 1000) + '<span class="metric-unit">s</span>';
      document.querySelector("#metric-session-time").textContent = Math.floor(data.session_duration_ms / 1000);
      document.querySelector("#metric-requests").textContent = data.request_frequency_per_minute;
      document.querySelector("#metric-queued").textContent = data.pending_event_count;
    }

    flushButton.addEventListener("click", async function () {
      flushButton.disabled = true;
      flushButton.firstChild.textContent = "Sending batch... ";
      await monitor.flush();
      flushButton.disabled = false;
      flushButton.firstChild.textContent = "Flush event batch ";
      renderMetrics();
    });

    disableButton.addEventListener("click", function () {
      if (monitor.enabled) {
        monitor.disable();
        disableButton.textContent = "Enable monitoring for this page";
      } else {
        monitor.enable();
        disableButton.textContent = "Disable monitoring for this page";
      }
      renderMetrics();
    });

    renderMetrics();
    window.setInterval(renderMetrics, 1000);
  }

  function initializeMenu() {
    const toggle = document.querySelector(".menu-toggle");
    const navigation = document.querySelector(".main-nav");
    if (!toggle || !navigation) return;
    toggle.addEventListener("click", function () {
      const isOpen = navigation.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    });
  }

  checkHealth();
  initializeSearch();
  initializeCart();
  initializeForms();
  initializeDashboard();
  initializeMenu();
})();
