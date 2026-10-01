(function (global) {
  "use strict";

  const localHosts = ["localhost", "127.0.0.1", "[::1]"];
  const localFrontendPorts = ["5500", "5501", "5173"];
  const useSeparateLocalApi = localHosts.includes(global.location.hostname)
    && localFrontendPorts.includes(global.location.port);
  const configuredBase = global.ABF_API_BASE;
  const apiBase = configuredBase || (useSeparateLocalApi ? "http://127.0.0.1:8000/api" : "/api");

  global.ABF_API_BASE = String(apiBase).replace(/\/$/, "");
  global.ABF_API_DOCS_URL = global.ABF_API_BASE.replace(/\/api$/, "") + "/docs";
  document.querySelectorAll("[data-api-docs]").forEach(function (link) {
    link.href = global.ABF_API_DOCS_URL;
  });
})(window);