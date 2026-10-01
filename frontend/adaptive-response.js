(function (global) {
  "use strict";

  const apiBase = global.ABF_API_BASE || "/api";
  let initialized = false;
  let overlay = null;
  let bypassedElement = null;
  let accessPromise = null;
  let pageAllowed = false;

  function createOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "adaptive-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "adaptive-title");
    const panel = document.createElement("section");
    panel.className = "adaptive-panel";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "AEGIS / DEMO RESPONSE";
    const title = document.createElement("h1");
    title.id = "adaptive-title";
    const message = document.createElement("p");
    message.className = "adaptive-message";
    panel.append(eyebrow, title, message);
    overlay.append(panel);
    document.body.append(overlay);
    overlay._title = title;
    overlay._message = message;
    overlay._panel = panel;
    return overlay;
  }

  function removeOverlay() {
    if (!overlay) return;
    overlay.remove();
    overlay = null;
  }

  async function requestJson(path, options) {
    const response = await fetch(apiBase + path, options);
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok) throw new Error(data.detail || "Adaptive policy service unavailable");
    return data;
  }

  async function fetchAccess() {
    const monitor = global.ABFBehaviorMonitor;
    if (!monitor) return null;
    const sessionId = monitor.getSessionId();
    if (monitor.enabled) {
      await monitor.flush();
    }
    await requestJson("/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, sdk_version: "1.0.0" }),
    });
    return requestJson("/session/" + encodeURIComponent(sessionId) + "/access");
  }

  function showBlock(access) {
    const destination = "blocked.html?request_id=" + encodeURIComponent(access.request_id);
    global.location.assign(destination);
    return false;
  }

  function showDelay(access) {
    const current = createOverlay();
    current.classList.add("is-delay");
    current._title.textContent = "Request is being checked";
    current._message.textContent = access.reason + " This demo is applying a short review delay.";
    const countdown = document.createElement("strong");
    countdown.className = "adaptive-countdown";
    current._panel.append(countdown);
    let remaining = Math.ceil(access.delay_ms / 1000);
    countdown.textContent = "Continuing in " + remaining + " seconds";
    return new Promise(function (resolve) {
      let completed = false;
      let timer = null;
      let timeout = null;
      function finish() {
        if (completed) return;
        completed = true;
        if (timer) global.clearInterval(timer);
        if (timeout) global.clearTimeout(timeout);
        removeOverlay();
        resolve(true);
      }
      timer = global.setInterval(function () {
        remaining -= 1;
        if (remaining > 0) {
          countdown.textContent = "Continuing in " + remaining + " seconds";
          return;
        }
        finish();
      }, 1000);
      timeout = global.setTimeout(finish, access.delay_ms);
    });
  }

  async function showChallenge(access) {
    const challenge = await requestJson("/session/" + encodeURIComponent(access.session_id) + "/challenge", { method: "POST" });
    const current = createOverlay();
    current.classList.add("is-challenge");
    current._title.textContent = "Verify this interaction";
    current._message.textContent = challenge.notice;
    const form = document.createElement("form");
    form.className = "adaptive-challenge-form";
    const question = document.createElement("label");
    question.htmlFor = "adaptive-answer";
    question.textContent = challenge.question;
    const answer = document.createElement("input");
    answer.id = "adaptive-answer";
    answer.name = "answer";
    answer.type = "number";
    answer.inputMode = "numeric";
    answer.min = "0";
    answer.max = "99";
    answer.required = true;
    const button = document.createElement("button");
    button.className = "button button-primary";
    button.type = "submit";
    button.textContent = "Verify and continue";
    const feedback = document.createElement("p");
    feedback.className = "adaptive-feedback";
    feedback.setAttribute("role", "status");
    form.append(question, answer, button, feedback);
    current._panel.append(form);
    answer.focus();

    return new Promise(function (resolve) {
      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        button.disabled = true;
        feedback.textContent = "Checking answer...";
        try {
          await requestJson(
            "/session/" + encodeURIComponent(access.session_id) + "/challenge/" + encodeURIComponent(challenge.challenge_id) + "/verify",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ answer: answer.value }),
            },
          );
          removeOverlay();
          resolve(true);
        } catch (error) {
          feedback.textContent = error.message;
          answer.value = "";
          answer.focus();
          button.disabled = false;
        }
      });
    });
  }

  async function enforceAccess() {
    if (accessPromise) return accessPromise;
    accessPromise = (async function () {
      let policyReceived = false;
      try {
        const access = await fetchAccess();
        if (!access) return true;
        policyReceived = true;
        if (access.actual_response === "allow") {
          pageAllowed = true;
          return true;
        }
        pageAllowed = false;
        if (access.actual_response === "challenge") {
          pageAllowed = await showChallenge(access);
          return pageAllowed;
        }
        if (access.actual_response === "delay") {
          pageAllowed = await showDelay(access);
          return pageAllowed;
        }
        if (access.actual_response === "block") return showBlock(access);
        pageAllowed = true;
        return true;
      } catch (_) {
        if (policyReceived) {
          const current = createOverlay();
          current._title.textContent = "Verification could not be completed";
          current._message.textContent = "The server required an additional response, but it could not be completed. No protected action was allowed.";
          pageAllowed = false;
          return false;
        }
        removeOverlay();
        pageAllowed = true;
        return true;
      } finally {
        accessPromise = null;
      }
    })();
    return accessPromise;
  }

  function isPolicyExemptLink(link) {
    if (!link || !link.href || link.target === "_blank" || link.hasAttribute("download")) return true;
    if (link.origin !== global.location.origin || link.pathname.endsWith("/blocked.html")) return true;
    if (link.pathname.endsWith("/dashboard.html")) return true;
    return link.hash && link.pathname === global.location.pathname;
  }

  function handleClick(event) {
    if (bypassedElement === event.target || (bypassedElement && bypassedElement.contains(event.target))) {
      bypassedElement = null;
      return;
    }
    const target = event.target instanceof Element ? event.target : null;
    const link = target && target.closest("a[href]");
    const productButton = target && target.closest("[data-add-product]");
    if (link && isPolicyExemptLink(link)) return;
    if (!link && !productButton) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    enforceAccess().then(function (allowed) {
      if (!allowed) return;
      if (link) {
        bypassedElement = link;
        link.click();
      } else {
        bypassedElement = productButton;
        productButton.click();
      }
    });
  }

  function handleSubmit(event) {
    if (bypassedElement === event.target) {
      bypassedElement = null;
      return;
    }
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.closest(".adaptive-overlay")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    enforceAccess().then(function (allowed) {
      if (!allowed) return;
      bypassedElement = form;
      form.requestSubmit(event.submitter || undefined);
    });
  }

  function initialize() {
    if (initialized || !document.body.hasAttribute("data-adaptive-guard")) return;
    initialized = true;
    document.addEventListener("click", handleClick, true);
    document.addEventListener("submit", handleSubmit, true);
    const initial = createOverlay();
    initial._title.textContent = "Checking session";
    initial._message.textContent = "The server is evaluating the current session policy.";
    if (document.body.hasAttribute("data-adaptive-public")) {
      removeOverlay();
      return;
    }
    global.setTimeout(function () {
      enforceAccess().then(function (allowed) {
        if (allowed && pageAllowed) removeOverlay();
      });
    }, 0);
  }

  global.ABFAdaptiveAccess = { initialize: initialize };
})(window);
