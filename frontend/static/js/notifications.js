// Rule: loaded on every dashboard page, not just notifications.html.

(function () {
  "use strict";

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

  // Rule: one fetch drives both the topbar dot and the sidebar badge.
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
      .catch(function () { /* Edge: a transient network error leaves both badges as-is. */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initListPage();
    if (document.getElementById("notifBadge") || document.getElementById("sidebarNotifBadge")) {
      pollUnreadCount();
      setInterval(pollUnreadCount, 30000);
    }
  });
})();
