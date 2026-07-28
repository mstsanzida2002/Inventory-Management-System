/* ==========================================================================
   SLOW-MOVING.JS — Slow-Moving & Dead Stock page: classification doughnut
   chart + table filtering + "Run classification now". Table filtering is
   handled by the shared table-filter.js; this file only owns the chart,
   which reuses the exact labels/colors documented in
   DEAD_STOCK_DETECTION.md's "Dashboard Display" section (mapped to this
   project's real design tokens instead of the doc's illustrative Bootstrap
   hex values).
   ========================================================================== */

(function () {
  "use strict";

  function initClassificationChart() {
    var canvas = document.getElementById("classificationChart");
    if (!canvas || typeof Chart === "undefined") return;

    var COLORS = window.ChartColors;
    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var ctx = canvas.getContext("2d");

    new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Fast-Moving", "Slow-Moving", "Dead Stock"],
        datasets: [{
          data: [1142, 118, 24],
          backgroundColor: [COLORS.success, COLORS.warning, COLORS.danger],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: reduceMotion ? false : { duration: 500 },
        cutout: "68%",
        plugins: {
          legend: {
            position: "bottom",
            align: "center",
            labels: { usePointStyle: true, boxWidth: 7, boxHeight: 7, font: { family: "Inter", size: 12 }, color: COLORS.slate, padding: 16 }
          },
          tooltip: {
            backgroundColor: COLORS.ink,
            titleFont: { family: "Inter", size: 12, weight: "600" },
            bodyFont: { family: "IBM Plex Mono", size: 12 },
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: function (item) {
                return item.label + ": " + item.formattedValue + " products";
              }
            }
          }
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initClassificationChart();

    TableFilter.init({
      tableBodyId: "classificationTableBody",
      searchInputId: "classificationSearch",
      selectFilters: [{ id: "classificationCategoryFilter", attr: "data-category" }],
      segmentedId: "classificationToggle",
      segmentAttr: "data-classification",
      segmentDefault: "",
      emptyStateId: "classificationEmptyState"
    });

    AsyncRunButton.init({
      buttonId: "runClassificationBtn",
      runningLabel: "Running…",
      doneLabel: "Classification queued"
    });
  });
})();
