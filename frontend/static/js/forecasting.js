/* ==========================================================================
   FORECASTING.JS — Demand Forecasting page: trend chart + the "Run
   forecast now" action. Search/category/period are real server-side GET
   params now (Pagination pass, 2026-08-25 — frontend.filters.filter_
   forecasts()), submitted via the page's own <form method="get"> and the
   period toggle's real links, so this file no longer wires
   table-filter.js and no longer client-side-switches the chart on
   toggle click — the toggle is a real navigation now, and the reload it
   causes already re-renders {{ chart_data|json_script:"forecastChartData" }}
   fresh; initTrendChart() just needs to open on whichever period the
   reload landed on (read off the server-rendered is-active toggle link)
   instead of always hardcoding weekly. This file still owns the chart
   (same server-data-into-chart convention dashboard.js/slow-moving.js
   use) and the Run button's real POST (row-actions.js's postAction(),
   same as Slow-Moving & Dead Stock's Run button).
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

  function activePeriod() {
    var active = document.querySelector("#forecastPeriodToggle .is-active");
    return (active && active.getAttribute("data-value")) || "weekly";
  }

  function initTrendChart() {
    var canvas = document.getElementById("forecastTrendChart");
    if (!canvas || typeof Chart === "undefined") return null;

    var COLORS = window.ChartColors;
    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var ctx = canvas.getContext("2d");
    var TREND_DATA = readChartData();
    var initial = TREND_DATA[activePeriod()] || TREND_DATA.weekly;

    var chart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: initial.labels,
        datasets: [
          {
            label: "Forecasted demand",
            data: initial.demand,
            backgroundColor: COLORS.indigo,
            borderRadius: 6,
            barThickness: 22,
            order: 2
          },
          {
            label: "Recommended reorder qty",
            data: initial.reorder,
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

    return chart;
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTrendChart();

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
