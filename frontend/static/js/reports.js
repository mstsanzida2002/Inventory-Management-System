/* ==========================================================================
   REPORTS.JS — Reports page (Phase 8). Low Stock preview keeps a real
   client-side category filter via table-filter.js (each row still carries
   a real Category). Sales preview dropped its per-row category (a sale can
   span multiple product categories — see reports.html's own comment), so
   there's nothing left for table-filter.js to match there; its Category
   select is export-only now, read directly by report-export-btn's click
   handler below alongside both panels' date range.
   ========================================================================== */

(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    if (document.getElementById("lowStockReportTableBody")) {
      TableFilter.init({
        tableBodyId: "lowStockReportTableBody",
        selectFilters: [{ id: "lowStockReportCategory", attr: "data-category" }],
        emptyStateId: "lowStockReportEmptyState",
      });
    }

    var PANEL_FILTERS = {
      sales: { from: "salesReportFrom", to: "salesReportTo", category: "salesReportCategory" },
      "low-stock": { category: "lowStockReportCategory" },
    };

    document.querySelectorAll(".report-export-btn").forEach(function (button) {
      button.addEventListener("click", function () {
        var panel = button.getAttribute("data-panel");
        var format = button.getAttribute("data-format");
        var base = button.getAttribute("data-base-url");
        var fields = PANEL_FILTERS[panel] || {};

        var params = new URLSearchParams();
        params.set("format", format);

        var fromField = fields.from && document.getElementById(fields.from);
        var toField = fields.to && document.getElementById(fields.to);
        var categoryField = fields.category && document.getElementById(fields.category);
        if (fromField && fromField.value) params.set("date_from", fromField.value);
        if (toField && toField.value) params.set("date_to", toField.value);
        if (categoryField && categoryField.value) params.set("category", categoryField.value);

        window.location.href = base + "?" + params.toString();
      });
    });
  });
})();
