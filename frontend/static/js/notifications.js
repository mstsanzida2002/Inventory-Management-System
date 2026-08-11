/* ==========================================================================
   NOTIFICATIONS.JS — Notifications list page (mark one/mark all read) and
   the topbar bell badge's 30s polling, shared across every dashboard page
   (loaded from dashboard_base.html, not just notifications.html).

   Row-action POSTs go through row-actions.js's shared postAction()/
   reportResult() (Phase 8.5) rather than a local copy — these endpoints
   are LoginRequiredMixin-only (no role check), but a mid-session logout/
   expiry still bounces through the same redirect-instead-of-JSON shape
   RowActions already knows how to detect and report honestly.
   ========================================================================== */

(function () {
  "use strict";

  /* ------------------------------------------------- List page actions --- */
  function initListPage() {
    var list = document.getElementById("notificationsList");
    if (!list) return;
    var base = list.getAttribute("data-base-url");

    list.addEventListener("click", function (event) {
      if (!event.target.closest(".notif-mark-read-btn")) return;
      var row = event.target.closest("[data-notification-id]");
      if (!row) return;
      RowActions.postAction(base + row.getAttribute("data-notification-id") + "/read/").then(RowActions.reportResult);
    });

    var markAllBtn = document.getElementById("markAllReadBtn");
    if (markAllBtn) {
      markAllBtn.addEventListener("click", function () {
        RowActions.postAction(base + "read-all/").then(RowActions.reportResult);
      });
    }
  }

  /* --------------------------------------------------------- Badge poll --- */
  function pollUnreadCount() {
    var badge = document.getElementById("notifBadge");
    if (!badge) return;
    fetch("/notifications/unread-count/")
      .then(function (response) { return response.json(); })
      .then(function (data) { badge.hidden = !data.unread_count; })
      .catch(function () { /* leave the badge as-is on a transient network error */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initListPage();
    if (document.getElementById("notifBadge")) {
      pollUnreadCount();
      setInterval(pollUnreadCount, 30000);
    }
  });
})();
