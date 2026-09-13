// Rule: shared POST helper for every row action (approve/reject/cancel/...).

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
      // Assumption: a redirect means RBAC bounced this, not response.ok's 200.
      if (response.redirected) {
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
