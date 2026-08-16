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
  // Phase 8.99f-2: the sidebar's own notification badge (nav-item-badge,
  // includes/sidebar.html) used to be a hardcoded "6" from the Phase 3.6
  // mock era. Rather than give it a second query/poll of its own, this
  // one fetch now drives both it and the topbar dot — same data, same
  // instant, same "hide entirely at zero" rule, so the two can't disagree.
  function pollUnreadCount() {
    var dot = document.getElementById("notifBadge");
    var sidebarBadge = document.getElementById("sidebarNotifBadge");
    if (!dot && !sidebarBadge) return;
    fetch("/notifications/unread-count/")
      .then(function (response) { return response.json(); })
      .then(function (data) {
        var hasUnread = !!data.unread_count;
        if (dot) dot.hidden = !hasUnread;
        if (sidebarBadge) {
          sidebarBadge.hidden = !hasUnread;
          sidebarBadge.textContent = data.unread_count;
        }
      })
      .catch(function () { /* leave both badges as-is on a transient network error */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initListPage();
    if (document.getElementById("notifBadge") || document.getElementById("sidebarNotifBadge")) {
      pollUnreadCount();
      setInterval(pollUnreadCount, 30000);
    }
  });
})();
