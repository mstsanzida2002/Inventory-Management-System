/* ==========================================================================
   ASYNC-RUN-BUTTON.JS — button loading-state for a "run this now" action.
   Two modes:
   - config.action (Promise-returning function): real, synchronous server
     call — Phase 10's "Run classification now" (no Celery in this
     project; the classifier runs inline and returns a real result before
     this resolves). Used on Slow-Moving & Dead Stock.
   - no config.action: original simulated queued/running affordance for an
     async Celery task this project doesn't build (Demand Forecasting's
     "Run forecast now" — Phase 11 decides whether that page ever gets a
     real backend). Unchanged behavior, so this page needed no edits.
   Shared by both Intelligence pages instead of duplicating the disable/
   spinner/restore sequence twice.
   ========================================================================== */

(function () {
  "use strict";

  function initAsyncRunButton(config) {
    var button = document.getElementById(config.buttonId);
    if (!button) return;

    var idleHtml = button.innerHTML;
    var isRunning = false;

    function restore() {
      button.innerHTML = idleHtml;
      button.disabled = false;
      isRunning = false;
    }

    function showDone(label) {
      button.innerHTML = '<svg class="icon icon-sm"><use href="#icon-check-circle"></use></svg>' +
        (label || config.doneLabel || "Task queued");
      window.setTimeout(restore, 1600);
    }

    button.addEventListener("click", function () {
      if (isRunning) return;
      isRunning = true;
      button.disabled = true;
      button.innerHTML = '<svg class="icon icon-sm spin"><use href="#icon-refresh"></use></svg>' +
        (config.runningLabel || "Running…");

      if (typeof config.action === "function") {
        config.action().then(function (result) {
          if (typeof config.onComplete === "function") config.onComplete(result);
          showDone();
        }).catch(function (error) {
          restore();
          if (typeof config.onError === "function") config.onError(error);
        });
        return;
      }

      window.setTimeout(function () {
        if (typeof config.onComplete === "function") config.onComplete();
        showDone();
      }, config.duration || 1400);
    });
  }

  window.AsyncRunButton = { init: initAsyncRunButton };
})();
