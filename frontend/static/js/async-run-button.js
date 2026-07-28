/* ==========================================================================
   ASYNC-RUN-BUTTON.JS — button loading-state for a "queue a background
   task" action (e.g. "Run forecast now" -> POST /api/v1/ai/forecasts/run/,
   which the docs describe as an async Celery task, not an inline result).
   No backend is wired here, so this only simulates the queued/running
   affordance; shared by both Intelligence pages instead of duplicating the
   same disable/spinner/restore sequence twice.
   ========================================================================== */

(function () {
  "use strict";

  function initAsyncRunButton(config) {
    var button = document.getElementById(config.buttonId);
    if (!button) return;

    var idleHtml = button.innerHTML;
    var isRunning = false;

    button.addEventListener("click", function () {
      if (isRunning) return;
      isRunning = true;
      button.disabled = true;
      button.innerHTML = '<svg class="icon icon-sm spin"><use href="#icon-refresh"></use></svg>' +
        (config.runningLabel || "Running…");

      window.setTimeout(function () {
        button.innerHTML = '<svg class="icon icon-sm"><use href="#icon-check-circle"></use></svg>' +
          (config.doneLabel || "Task queued");

        if (typeof config.onComplete === "function") config.onComplete();

        window.setTimeout(function () {
          button.innerHTML = idleHtml;
          button.disabled = false;
          isRunning = false;
        }, 1600);
      }, config.duration || 1400);
    });
  }

  window.AsyncRunButton = { init: initAsyncRunButton };
})();
