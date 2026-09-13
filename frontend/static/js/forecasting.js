(function () {
  "use strict";

  function readChartData() {
    var el = document.getElementById("forecastChartData");
    var empty = { weekly: { labels: [], demand: [], reorder: [] }, monthly: { labels: [], demand: [], reorder: [] } };
    if (!el) return empty;
    try {
      // Assumption: json_script-rendered chart_data from DemandForecastingView.
      return JSON.parse(el.textContent) || empty;
    } catch (e) {
      return empty;
    }
  }

  function activePeriod() {
    // Assumption: reads the server-rendered is-active toggle link.
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
        window.location.reload();
      }
    });
  });
})();
