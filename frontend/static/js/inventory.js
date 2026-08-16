/* ==========================================================================
   INVENTORY.JS — Inventory page (Phase 8.9). Wires table-filter.js: search
   (product/SKU/barcode) + status select. Read-only page — no modal, no
   form, nothing else to wire.
   ========================================================================== */

(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("inventoryTableBody")) return;

    TableFilter.init({
      tableBodyId: "inventoryTableBody",
      searchInputId: "inventorySearch",
      selectFilters: [{ id: "inventoryStatusFilter", attr: "data-status" }],
    });
  });
})();
