/* ==========================================================================
   SLOW-MOVING.JS — Slow-Moving & Dead Stock page: classification doughnut
   chart + table filtering + "Run classification now". Table filtering is
   handled by the shared table-filter.js; this file owns the chart (real
   counts, via {{ chart_data|json_script:"classificationChartData" }} —
   the same server-data-into-chart convention dashboard.js already uses)
   and the Run button's real POST (row-actions.js's postAction(), the same
   fetch()+CSRF+blocked-redirect handling every other action in this app
   already shares — Phase 10 is this page's first real backend call, not a
   reason to invent a second way to make one).
   ========================================================================== */

(function () {
  "use strict";

  function readChartData() {
    var el = document.getElementById("classificationChartData");
    if (!el) return { fast: 0, slow: 0, dead: 0 };
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return { fast: 0, slow: 0, dead: 0 };
    }
  }

  function initClassificationChart() {
    var canvas = document.getElementById("classificationChart");
    if (!canvas || typeof Chart === "undefined") return;

    var COLORS = window.ChartColors;
    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var ctx = canvas.getContext("2d");
    var data = readChartData();

    new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Fast-Moving", "Slow-Moving", "Dead Stock"],
        datasets: [{
          data: [data.fast, data.slow, data.dead],
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
      doneLabel: "Classification updated",
      action: function () {
        return RowActions.postAction(window.location.pathname).then(function (result) {
          if (result.blocked) {
            alert("You don't have permission to do that.");
            throw new Error("blocked");
          }
          if (!result.ok) {
            var message = (result.payload && result.payload.error) || "Classification run failed.";
            alert(message);
            throw new Error(message);
          }
          return result;
        });
      },
      onComplete: function () {
        // Real counts (KPIs, doughnut, table, Needs Attention) all come
        // from server-rendered context — a reload is the simplest way to
        // reflect them, matching every other action in this app
        // (RowActions.reportResult()'s own default behavior).
        window.location.reload();
      }
    });
  });
})();
