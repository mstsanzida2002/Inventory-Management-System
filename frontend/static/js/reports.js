/* ==========================================================================
   REPORTS.JS — Reports page. Wires table-filter.js for the two mock report
   tables (Sales, Low Stock) — search + category select only; date_from/
   date_to stay decorative since TableFilter only matches search text and
   select attributes, not date ranges. Export buttons are decorative too
   (no PDF/CSV generation exists yet — see docs/10_REPORTS.md).
   ========================================================================== */

(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    if (document.getElementById("salesReportTableBody")) {
      TableFilter.init({
        tableBodyId: "salesReportTableBody",
        selectFilters: [{ id: "salesReportCategory", attr: "data-category" }],
        emptyStateId: "salesReportEmptyState",
      });
    }

    if (document.getElementById("lowStockReportTableBody")) {
      TableFilter.init({
        tableBodyId: "lowStockReportTableBody",
        selectFilters: [{ id: "lowStockReportCategory", attr: "data-category" }],
        emptyStateId: "lowStockReportEmptyState",
      });
    }
  });
})();
