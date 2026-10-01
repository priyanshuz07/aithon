(function (global) {
  "use strict";

  const SDK_VERSION = "1.0.0";
  const DEFAULTS = {
    apiBaseUrl: global.ABF_API_BASE || "/api",
    flushIntervalMs: 5000,
    maxBatchSize: 40,
    maxQueueSize: 160,
    enabled: true,
    onStatus: function () {},
  };

  function create(options) {
    const config = Object.assign({}, DEFAULTS, options || {});
    const baseUrl = String(config.apiBaseUrl).replace(/\/$/, "");
    const storage = global.sessionStorage;
    const storagePrefix = "abf.behavior.v1.";
    const pageStartedAt = Date.now();
    const pageKey = document.body.dataset.monitorPage || "page";
    const apiUrl = new URL(baseUrl, global.location.href);
    const nativeFetch = global.fetch.bind(global);
    let enabled = Boolean(config.enabled);
    let initialized = false;
    let flushing = false;
    let backendSessionId = null;
    let sessionPromise = null;
    let flushTimer = null;
    let observer = null;
    let actionCounts = {};
    let listenersAttached = false;
    let pendingEvents = loadJson("queue", []).map(function (event) {
      return Object.assign({ event_id: createRandomId() }, event);
    });
    let metrics = loadJson("metrics", {
      startedAt: Date.now(),
      pageVisitCount: 0,
      clickCount: 0,
      formSubmissionCount: 0,
      repeatedActionCount: 0,
      requestCount: 0,
      interClickTotalMs: 0,
      interClickCount: 0,
      lastClickAt: null,
    });
    let sdkSessionId = loadString("client_session_id") || createRandomId();

    function loadString(key) {
      try {
        return storage.getItem(storagePrefix + key);
      } catch (_) {
        return null;
      }
    }

    function saveString(key, value) {
      try {
        storage.setItem(storagePrefix + key, String(value));
      } catch (_) {
        // Storage may be unavailable in private browsing; monitoring still works in memory.
      }
    }

    function loadJson(key, fallback) {
      try {
        const value = storage.getItem(storagePrefix + key);
        return value ? JSON.parse(value) : fallback;
      } catch (_) {
        return fallback;
      }
    }

    function saveJson(key, value) {
      try {
        storage.setItem(storagePrefix + key, JSON.stringify(value));
      } catch (_) {
        // Keep the in-memory queue if browser storage is unavailable.
      }
    }

    function createRandomId() {
      if (global.crypto && typeof global.crypto.randomUUID === "function") {
        return global.crypto.randomUUID();
      }
      if (global.crypto && typeof global.crypto.getRandomValues === "function") {
        const bytes = new Uint8Array(16);
        global.crypto.getRandomValues(bytes);
        return Array.from(bytes, function (byte) {
          return byte.toString(16).padStart(2, "0");
        }).join("");
      }
      return "xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx".replace(/[xy]/g, function (character) {
        const random = Math.floor(Math.random() * 16);
        return (character === "x" ? random : (random & 3) | 8).toString(16);
      });
    }

    function reportStatus(status, message) {
      try {
        config.onStatus({ status: status, message: message || "" });
      } catch (_) {
        // A UI callback must never interrupt the page.
      }
    }

    function persistState() {
      saveJson("metrics", metrics);
      saveJson("queue", pendingEvents);
      saveJson("action_counts", actionCounts);
      saveString("client_session_id", sdkSessionId);
      if (backendSessionId !== null) saveString("backend_session_id", backendSessionId);
    }

    function snapshot() {
      const elapsedMs = Math.max(1, Date.now() - metrics.startedAt);
      const averageInterClickMs = metrics.interClickCount
        ? Math.round(metrics.interClickTotalMs / metrics.interClickCount)
        : 0;
      return {
        page: pageKey,
        click_count: metrics.clickCount,
        page_visit_count: metrics.pageVisitCount,
        page_time_ms: Math.max(0, Date.now() - pageStartedAt),
        average_inter_click_ms: averageInterClickMs,
        form_submission_count: metrics.formSubmissionCount,
        repeated_action_count: metrics.repeatedActionCount,
        request_count: metrics.requestCount,
        request_frequency_per_minute: Number((metrics.requestCount * 60000 / elapsedMs).toFixed(2)),
        session_duration_ms: Math.max(0, Date.now() - metrics.startedAt),
        pending_event_count: pendingEvents.length,
      };
    }

    function enqueue(type, payload) {
      pendingEvents.push({
        event_id: createRandomId(),
        type: type,
        at: new Date().toISOString(),
        payload: payload || {},
      });
      if (pendingEvents.length > config.maxQueueSize) {
        pendingEvents.splice(0, pendingEvents.length - config.maxQueueSize);
      }
      persistState();
    }

    function getBackendSessionId() {
      const stored = loadString("backend_session_id");
      return stored && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(stored)
        ? stored
        : null;
    }

    backendSessionId = getBackendSessionId();

    async function ensureBackendSession() {
      if (backendSessionId !== null) return backendSessionId;
      if (sessionPromise) return sessionPromise;
      sessionPromise = nativeFetch(baseUrl + "/session/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sdkSessionId,
          sdk_version: SDK_VERSION,
        }),
      }).then(async function (response) {
        if (!response.ok) throw new Error("Session request returned HTTP " + response.status);
        const result = await response.json();
        backendSessionId = result.session_id;
        saveString("backend_session_id", backendSessionId);
        enqueue("session.start", { sdk_session_id: sdkSessionId, sdk_version: SDK_VERSION });
        reportStatus("online", "Session connected");
        return backendSessionId;
      }).catch(function (error) {
        sessionPromise = null;
        reportStatus("offline", error.message || "Backend unavailable");
        return null;
      });
      return sessionPromise;
    }

    function postEvent(batch, keepalive) {
      if (backendSessionId === null) return Promise.reject(new Error("No backend session"));
      return nativeFetch(baseUrl + "/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: backendSessionId,
          batch_id: createRandomId(),
          events: batch,
          features: snapshot(),
        }),
        keepalive: Boolean(keepalive),
      }).then(function (response) {
        if (!response.ok) throw new Error("Event request returned HTTP " + response.status);
        return response;
      });
    }

    async function flush(options) {
      if (!enabled || flushing || pendingEvents.length === 0) return false;
      flushing = true;
      let batch = [];
      const keepalive = Boolean(options && options.keepalive);
      try {
        const sessionId = await ensureBackendSession();
        if (sessionId === null) return false;
        batch = pendingEvents.splice(0, config.maxBatchSize);
        const result = await postEvent(batch, keepalive);
        saveJson("queue", pendingEvents);
        reportStatus("online", "Last batch sent");
        return result.ok;
      } catch (error) {
        if (batch.length) {
          pendingEvents = batch.concat(pendingEvents).slice(-config.maxQueueSize);
          saveJson("queue", pendingEvents);
        }
        reportStatus("offline", error.message || "Event batch failed");
        return false;
      } finally {
        flushing = false;
        persistState();
      }
    }

    function identifyAction(element) {
      const declared = element.getAttribute("data-monitor-action");
      const id = element.id;
      const type = element.getAttribute("type");
      const fallback = element.tagName.toLowerCase() + (type ? "." + type : "");
      return String(declared || id || fallback).replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 80);
    }

    function onClick(event) {
      const target = event.target instanceof Element ? event.target : null;
      const control = target && target.closest('button, a[href], input[type="button"], input[type="submit"], [role="button"]');
      if (!control) return;
      metrics.clickCount += 1;
      const now = Date.now();
      if (typeof metrics.lastClickAt === "number") {
        metrics.interClickTotalMs += now - metrics.lastClickAt;
        metrics.interClickCount += 1;
      }
      metrics.lastClickAt = now;
      const action = identifyAction(control);
      actionCounts[action] = (actionCounts[action] || 0) + 1;
      if (actionCounts[action] > 1) metrics.repeatedActionCount += 1;
      enqueue("interaction.click", { action_id: action });
    }

    function onSubmit(event) {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      metrics.formSubmissionCount += 1;
      const formId = form.getAttribute("data-monitor-action") || form.id || "form";
      enqueue("interaction.form_submit", {
        form_id: String(formId).replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 80),
      });
    }

    function onResource(entries) {
      entries.getEntries().forEach(function (entry) {
        if (entry.initiatorType !== "fetch" && entry.initiatorType !== "xmlhttprequest") return;
        try {
          const url = new URL(entry.name, global.location.href);
          if (url.origin === apiUrl.origin && url.pathname.indexOf(apiUrl.pathname + "/") === 0) return;
        } catch (_) {
          return;
        }
        metrics.requestCount += 1;
      });
      persistState();
    }

    function attachListeners() {
      if (listenersAttached) return;
      document.addEventListener("click", onClick, true);
      document.addEventListener("submit", onSubmit, true);
      if (typeof global.PerformanceObserver === "function") {
        try {
          observer = new global.PerformanceObserver(onResource);
          observer.observe({ type: "resource", buffered: true });
        } catch (_) {
          observer = null;
        }
      }
      listenersAttached = true;
    }

    function detachListeners() {
      if (!listenersAttached) return;
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("submit", onSubmit, true);
      if (observer) observer.disconnect();
      observer = null;
      listenersAttached = false;
    }

    function start() {
      if (!initialized) {
        initialized = true;
        metrics.pageVisitCount += 1;
        enqueue("navigation.page_view", { page: pageKey });
      }
      attachListeners();
      reportStatus("connecting", "Connecting to local API");
      ensureBackendSession().then(function () {
        if (enabled) flush();
      });
      if (flushTimer === null) {
        flushTimer = global.setInterval(function () {
          ensureBackendSession().then(function () { flush(); });
        }, Math.max(1000, Number(config.flushIntervalMs) || DEFAULTS.flushIntervalMs));
      }
      persistState();
    }

    function setEnabled(value) {
      const next = Boolean(value);
      if (enabled === next) return;
      enabled = next;
      if (enabled) {
        start();
      } else {
        if (flushTimer !== null) global.clearInterval(flushTimer);
        flushTimer = null;
        detachListeners();
        reportStatus("disabled", "Monitoring disabled");
      }
    }

    function destroy() {
      if (enabled) flush({ keepalive: true });
      if (flushTimer !== null) global.clearInterval(flushTimer);
      flushTimer = null;
      detachListeners();
      enabled = false;
      reportStatus("disabled", "Monitoring stopped");
    }

    function onPageHide() {
      flush({ keepalive: true });
    }

    global.addEventListener("pagehide", onPageHide);

    const monitor = {
      get enabled() { return enabled; },
      getSessionId: function () { return sdkSessionId; },
      getSnapshot: snapshot,
      flush: flush,
      disable: function () { setEnabled(false); },
      enable: function () { setEnabled(true); },
      destroy: destroy,
    };

    if (enabled) start();
    return monitor;
  }

  global.ABFBehaviorSDK = { create: create, version: SDK_VERSION };
})(window);
