/* ==========================================================================
   SLOW-MOVING.JS — Slow-Moving & Dead Stock page: classification doughnut
   chart + "Run classification now". Search/category/classification are
   real server-side GET params now (Pagination pass, 2026-08-25 —
   frontend.filters.filter_classifications()), submitted via the page's
   own <form method="get"> and the classification toggle's real links, so
   this file no longer wires table-filter.js. It owns the chart (real
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
    if (!el) return { fast: 0, slow: 0, dead: 0, insufficient_data: 0 };
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return { fast: 0, slow: 0, dead: 0, insufficient_data: 0 };
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
        labels: ["Fast-Moving", "Slow-Moving", "Dead Stock", "Insufficient Data"],
        datasets: [{
          data: [data.fast, data.slow, data.dead, data.insufficient_data],
          // Prompt 2 (2026-08-24) — muted grey (slate200), visually
          // distinct from the three status colors: insufficient_data
          // isn't a problem state and shouldn't read as a fourth
          // severity level.
          backgroundColor: [COLORS.success, COLORS.warning, COLORS.danger, COLORS.slate200],
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
