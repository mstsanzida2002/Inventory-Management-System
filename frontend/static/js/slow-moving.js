(function () {
  "use strict";

  function readChartData() {
    var el = document.getElementById("classificationChartData");
    if (!el) return { fast: 0, slow: 0, dead: 0, insufficient_data: 0 };
    try {
      // Assumption: json_script-rendered chart_data from SlowMovingDeadStockView.
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
          // Rule: insufficient_data gets its own neutral color -- not a problem state.
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
        window.location.reload();
      }
    });
  });
})();
