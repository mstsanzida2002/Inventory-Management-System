/* ==========================================================================
   ROW-ACTIONS.JS — shared fetch()-based POST helper for row actions
   (approve/reject/cancel/submit/receive/deactivate/reactivate/mark-read),
   used by purchase-form.js, sale-form.js, adjustment-form.js,
   user-form.js, notifications.js. Extracted in Phase 8.5 — every one of
   those files had its own copy of getCsrfToken()/postAction(), which is
   exactly the kind of duplication this project's own rule (§18 of
   project_memory.md: "refactor duplicate logic into a shared module
   before adding new code") says to fix rather than grow a sixth copy of.

   Phase 8.5's actual bug fix lives here too: every one of RBAC's mixins
   (frontend/mixins.py's RoleRequiredMixin) denies access with a 302
   redirect to /dashboard/ (or /login/ if not authenticated at all), never
   a 403/JSON error. fetch() follows redirects transparently by default,
   so `response.ok` comes back true (the dashboard page itself is a normal
   200) even though the action the user actually asked for never
   happened — the old per-file postAction() implementations had no way to
   tell "it worked" apart from "it got silently bounced," so a blocked
   staff user just saw the page quietly reload with no explanation.
   `Response.redirected` is the one signal that distinguishes them:
   `postAction()` checks it before ever asking `response.ok`, and reports
   a `blocked: true` result so callers can show a real message instead of
   treating a denial as success.
   ========================================================================== */

(function () {
  "use strict";

  function getCsrfToken() {
    var match = document.cookie.match("(^|;)\\s*csrftoken\\s*=\\s*([^;]+)");
    return match ? decodeURIComponent(match.pop()) : "";
  }

  function postAction(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() },
      body: body || new FormData()
    }).then(function (response) {
      if (response.redirected) {
        // RoleRequiredMixin (or LoginRequiredMixin) bounced this request —
        // the 200 on the other end (dashboard/login) is not a real success.
        return { ok: false, blocked: true, payload: null };
      }
      return response.json().catch(function () { return null; }).then(function (payload) {
        return { ok: response.ok, blocked: false, payload: payload };
      });
    });
  }

  function reportResult(result, onSuccess) {
    if (result.ok) {
      if (typeof onSuccess === "function") {
        onSuccess();
      } else {
        window.location.reload();
      }
      return;
    }
    if (result.blocked) {
      alert("You don't have permission to do that.");
      return;
    }
    var message = (result.payload && (result.payload.error ||
      (result.payload.errors && Object.values(result.payload.errors)[0]))) || "Something went wrong.";
    alert(typeof message === "string" ? message : "Something went wrong.");
  }

  window.RowActions = {
    getCsrfToken: getCsrfToken,
    postAction: postAction,
    reportResult: reportResult
  };
})();
