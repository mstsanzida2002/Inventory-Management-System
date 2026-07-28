/* ==========================================================================
   TABLE-FILTER.JS — generic client-side row filtering: a search box, any
   number of <select> filters, and an optional .segmented control, all
   matched against data-* attributes on each <tr>. Shared by the Demand
   Forecasting and Slow-Moving & Dead Stock pages instead of each one
   re-implementing its own search/filter wiring.

   Usage:
     TableFilter.init({
       tableBodyId: "forecastTableBody",
       searchInputId: "forecastSearch",        // matches row's data-search
       selectFilters: [{ id: "forecastCategoryFilter", attr: "data-category" }],
       segmentedId: "forecastPeriodToggle",     // buttons need data-value
       segmentAttr: "data-period",
       segmentDefault: "weekly",
       emptyStateId: "forecastEmptyState"
     });
   ========================================================================== */

(function () {
  "use strict";

  function normalize(text) {
    return (text || "").toLowerCase().trim();
  }

  function initTableFilter(config) {
    var tableBody = document.getElementById(config.tableBodyId);
    if (!tableBody) return null;

    var emptyState = config.emptyStateId ? document.getElementById(config.emptyStateId) : null;
    var searchInput = config.searchInputId ? document.getElementById(config.searchInputId) : null;
    var selectFilters = (config.selectFilters || [])
      .map(function (filter) { return { el: document.getElementById(filter.id), attr: filter.attr }; })
      .filter(function (filter) { return filter.el; });
    var segmented = config.segmentedId ? document.getElementById(config.segmentedId) : null;
    var activeSegmentValue = config.segmentDefault || "";

    function applyFilters() {
      var searchTerm = searchInput ? normalize(searchInput.value) : "";
      var visibleCount = 0;

      Array.prototype.forEach.call(tableBody.querySelectorAll("tr"), function (row) {
        var matchesSearch = !searchTerm || normalize(row.getAttribute("data-search")).indexOf(searchTerm) !== -1;

        var matchesSelects = selectFilters.every(function (filter) {
          return !filter.el.value || row.getAttribute(filter.attr) === filter.el.value;
        });

        var matchesSegment = !segmented || !config.segmentAttr || !activeSegmentValue ||
          row.getAttribute(config.segmentAttr) === activeSegmentValue;

        var isVisible = matchesSearch && matchesSelects && matchesSegment;
        row.hidden = !isVisible;
        if (isVisible) visibleCount += 1;
      });

      if (emptyState) emptyState.hidden = visibleCount !== 0;
      if (typeof config.onFilter === "function") config.onFilter(visibleCount);
    }

    if (searchInput) searchInput.addEventListener("input", applyFilters);
    selectFilters.forEach(function (filter) { filter.el.addEventListener("change", applyFilters); });

    if (segmented) {
      segmented.addEventListener("click", function (event) {
        var button = event.target.closest("button[data-value]");
        if (!button) return;
        segmented.querySelectorAll("button").forEach(function (b) { b.classList.remove("is-active"); });
        button.classList.add("is-active");
        activeSegmentValue = button.getAttribute("data-value");
        applyFilters();
      });
    }

    applyFilters();
    return { refresh: applyFilters };
  }

  window.TableFilter = { init: initTableFilter };
})();
