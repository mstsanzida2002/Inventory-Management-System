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

  function buildDropdownRow(notif) {
    var row = document.createElement("a");
    row.href = "/notifications/";
    row.className = "dropdown-notif" + (notif.is_read ? "" : " is-unread");
    row.setAttribute("role", "menuitem");
    row.setAttribute("data-notification-id", notif.id);

    var icon = document.createElement("span");
    icon.className = "widget-icon";
    icon.setAttribute("style", notif.icon_style);
    icon.innerHTML = '<svg class="icon icon-sm"><use href="#' + notif.icon_name + '"></use></svg>';
    row.appendChild(icon);

    var main = document.createElement("div");
    main.className = "widget-main";
    var title = document.createElement("div");
    title.className = "widget-title";
    title.textContent = notif.title;
    var meta = document.createElement("div");
    meta.className = "widget-meta";
    meta.textContent = notif.created_at;
    main.appendChild(title);
    main.appendChild(meta);
    row.appendChild(main);

    return row;
  }

  function renderDropdownList(notifications) {
    var container = document.getElementById("topbarNotifList");
    if (!container) return;
    container.innerHTML = "";
    if (!notifications.length) {
      var empty = document.createElement("p");
      empty.className = "text-slate text-sm";
      empty.setAttribute("style", "padding: var(--sp-4); margin:0;");
      empty.textContent = "No notifications yet.";
      container.appendChild(empty);
      return;
    }
    notifications.forEach(function (notif) {
      container.appendChild(buildDropdownRow(notif));
    });
  }

  // Rule: one fetch drives the topbar dot, sidebar badge, and dropdown list.
  function refreshNotifications() {
    var dot = document.getElementById("notifBadge");
    var sidebarBadge = document.getElementById("sidebarNotifBadge");
    var dropdownList = document.getElementById("topbarNotifList");
    if (!dot && !sidebarBadge && !dropdownList) return;
    fetch("/notifications/recent/")
      .then(function (response) { return response.json(); })
      .then(function (data) {
        var hasUnread = !!data.unread_count;
        if (dot) dot.hidden = !hasUnread;
        if (sidebarBadge) {
          sidebarBadge.hidden = !hasUnread;
          sidebarBadge.textContent = data.unread_count;
        }
        if (dropdownList) renderDropdownList(data.notifications);
      })
      .catch(function () { /* Edge: a transient network error leaves the UI as-is. */ });
  }

  function initDropdownMarkRead() {
    var container = document.getElementById("topbarNotifList");
    if (!container) return;
    container.addEventListener("click", function (event) {
      var row = event.target.closest("[data-notification-id]");
      if (!row) return;
      event.preventDefault();
      RowActions.postAction("/notifications/" + row.getAttribute("data-notification-id") + "/read/")
        .then(function (result) {
          if (result.ok) refreshNotifications();
        });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initListPage();
    initDropdownMarkRead();
    if (document.getElementById("notifBadge") || document.getElementById("sidebarNotifBadge") || document.getElementById("topbarNotifList")) {
      refreshNotifications();
      setInterval(refreshNotifications, 30000);
    }
  });
})();
