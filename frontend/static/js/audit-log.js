/* ==========================================================================
   AUDIT-LOG.JS — Audit Log page. Wires table-filter.js: search (user/
   action), module select, and a success/failure segmented toggle. date
   range stays decorative (TableFilter doesn't support date ranges).
   ========================================================================== */

(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("auditTableBody")) return;

    TableFilter.init({
      tableBodyId: "auditTableBody",
      searchInputId: "auditSearch",
      selectFilters: [{ id: "auditModuleFilter", attr: "data-module" }],
      segmentedId: "auditStatusToggle",
      segmentAttr: "data-status",
      segmentDefault: "",
      emptyStateId: "auditEmptyState",
    });
  });
})();
