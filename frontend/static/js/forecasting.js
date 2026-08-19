/* ==========================================================================
   FORECASTING.JS — Demand Forecasting page: trend chart + table filtering
   + the "Run forecast now" action. Table search/filter/empty-state is
   handled by the shared table-filter.js; this file owns the chart (real
   data via {{ chart_data|json_script:"forecastChartData" }}, the same
   server-data-into-chart convention dashboard.js/slow-moving.js already
   use) and the Run button's real POST (row-actions.js's postAction(),
   same as Slow-Moving & Dead Stock's Run button — Phase 11 isn't the
   first real backend call on an Intelligence page, no reason to invent a
   second way to make one).
   ========================================================================== */

(function () {
  "use strict";

  function readChartData() {
    var el = document.getElementById("forecastChartData");
    var empty = { weekly: { labels: [], demand: [], reorder: [] }, monthly: { labels: [], demand: [], reorder: [] } };
    if (!el) return empty;
    try {
      return JSON.parse(el.textContent) || empty;
    } catch (e) {
      return empty;
    }
  }

  function initTrendChart() {
    var canvas = document.getElementById("forecastTrendChart");
    if (!canvas || typeof Chart === "undefined") return null;

    var COLORS = window.ChartColors;
    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var ctx = canvas.getContext("2d");
    var TREND_DATA = readChartData();

    var chart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: TREND_DATA.weekly.labels,
        datasets: [
          {
            label: "Forecasted demand",
            data: TREND_DATA.weekly.demand,
            backgroundColor: COLORS.indigo,
            borderRadius: 6,
            barThickness: 22,
            order: 2
          },
          {
            label: "Recommended reorder qty",
            data: TREND_DATA.weekly.reorder,
            type: "line",
            borderColor: COLORS.amber,
            backgroundColor: COLORS.amberSoft,
            tension: 0.35,
            pointRadius: 3,
            pointBackgroundColor: COLORS.amber,
            borderWidth: 2,
            fill: true,
            order: 1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: reduceMotion ? false : { duration: 500 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "bottom",
            align: "start",
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
                return item.dataset.label + ": " + item.formattedValue + " units";
              }
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { family: "Inter", size: 11 }, color: COLORS.slate } },
          y: { grid: { color: COLORS.slate200 }, ticks: { font: { family: "IBM Plex Mono", size: 11 }, color: COLORS.slate } }
        }
      }
    });

    return {
      setPeriod: function (period) {
        var range = TREND_DATA[period];
        if (!range) return;
        chart.data.labels = range.labels;
        chart.data.datasets[0].data = range.demand;
        chart.data.datasets[1].data = range.reorder;
        chart.update();
      }
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    var trendChart = initTrendChart();

    TableFilter.init({
      tableBodyId: "forecastTableBody",
      searchInputId: "forecastSearch",
      selectFilters: [{ id: "forecastCategoryFilter", attr: "data-category" }],
      segmentedId: "forecastPeriodToggle",
      segmentAttr: "data-period",
      segmentDefault: "weekly",
      emptyStateId: "forecastEmptyState"
    });

    var periodToggle = document.getElementById("forecastPeriodToggle");
    if (periodToggle && trendChart) {
      periodToggle.addEventListener("click", function (event) {
        var button = event.target.closest("button[data-value]");
        if (!button) return;
        trendChart.setPeriod(button.getAttribute("data-value"));
      });
    }

    AsyncRunButton.init({
      buttonId: "runForecastBtn",
      runningLabel: "Running…",
      doneLabel: "Forecast updated",
      action: function () {
        return RowActions.postAction(window.location.pathname).then(function (result) {
          if (result.blocked) {
            alert("You don't have permission to do that.");
            throw new Error("blocked");
          }
          if (!result.ok) {
            var message = (result.payload && result.payload.error) || "Forecast run failed.";
            alert(message);
            throw new Error(message);
          }
          return result;
        });
      },
      onComplete: function () {
        // Real KPIs/chart/table/reorder-priorities all come from
        // server-rendered context — a reload is the simplest way to
        // reflect them (same pattern as Slow-Moving & Dead Stock's Run
        // button, and RowActions.reportResult()'s own default elsewhere).
        window.location.reload();
      }
    });
  });
})();
