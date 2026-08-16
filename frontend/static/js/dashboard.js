/* ==========================================================================
   DASHBOARD JS — dashboard.js
   Mobile sidebar toggle + Chart.js initialization for the overview page.
   Depends on Chart.js (loaded via CDN in dashboard_base.html) and
   window.ChartColors (chart-colors.js) for the tokens.css color mirror.
   ========================================================================== */

(function () {
  "use strict";

  var COLORS = window.ChartColors;

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------- Mobile sidebar */
  function initSidebarToggle() {
    var toggle = document.getElementById("sidebarToggle");
    var sidebar = document.getElementById("sidebar");
    var scrim = document.getElementById("sidebarScrim");
    if (!toggle || !sidebar || !scrim) return;

    function open() {
      sidebar.classList.add("is-open");
      scrim.classList.add("is-visible");
    }
    function close() {
      sidebar.classList.remove("is-open");
      scrim.classList.remove("is-visible");
    }
    toggle.addEventListener("click", function () {
      sidebar.classList.contains("is-open") ? close() : open();
    });
    scrim.addEventListener("click", close);
  }

  /* -------------------------------------------------- Topbar dropdowns */
  function initDropdowns() {
    var dropdowns = document.querySelectorAll(".dropdown");
    if (!dropdowns.length) return;

    function closeAll() {
      dropdowns.forEach(function (d) {
        d.classList.remove("is-open");
        var toggle = d.querySelector("[data-dropdown-toggle]");
        if (toggle) toggle.setAttribute("aria-expanded", "false");
      });
    }

    dropdowns.forEach(function (dropdown) {
      var toggle = dropdown.querySelector("[data-dropdown-toggle]");
      if (!toggle) return;
      toggle.addEventListener("click", function (event) {
        event.stopPropagation();
        var isOpen = dropdown.classList.contains("is-open");
        closeAll();
        if (!isOpen) {
          dropdown.classList.add("is-open");
          toggle.setAttribute("aria-expanded", "true");
        }
      });
    });

    document.addEventListener("click", closeAll);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeAll();
    });
  }

  /* ------------------------------------------------- Sales/Purchases chart */
  function readDashboardChartData() {
    var el = document.getElementById("dashboardChartData");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function initSalesChart(chartData) {
    var canvas = document.getElementById("salesChart");
    if (!canvas || typeof Chart === "undefined" || !chartData) return;

    // Real data (Phase 8.96, docs/09_DASHBOARD.md §3a) — daily/weekly/monthly
    // series computed server-side in frontend/views.py's dashboard(), passed
    // via {{ chart_data|json_script:"dashboardChartData" }}. Keys match the
    // segmented control's data-range values exactly.
    var datasets = chartData.sales_purchases;

    var ctx = canvas.getContext("2d");
    var chart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: datasets.daily.labels,
        datasets: [
          {
            label: "Sales",
            data: datasets.daily.sales,
            backgroundColor: COLORS.indigo,
            borderRadius: 6,
            barThickness: 18,
            order: 2
          },
          {
            label: "Purchases",
            data: datasets.daily.purchases,
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
                return item.dataset.label + ": $" + item.formattedValue;
              }
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { family: "Inter", size: 11 }, color: COLORS.slate } },
          y: {
            grid: { color: COLORS.slate200 },
            ticks: {
              font: { family: "IBM Plex Mono", size: 11 },
              color: COLORS.slate,
              callback: function (v) { return "$" + (v >= 1000 ? (v / 1000) + "k" : v); }
            }
          }
        }
      }
    });

    var segmented = document.getElementById("salesChartRange");
    if (segmented) {
      segmented.addEventListener("click", function (e) {
        var btn = e.target.closest("button[data-range]");
        if (!btn) return;
        segmented.querySelectorAll("button").forEach(function (b) { b.classList.remove("is-active"); });
        btn.classList.add("is-active");
        var range = datasets[btn.dataset.range];
        chart.data.labels = range.labels;
        chart.data.datasets[0].data = range.sales;
        chart.data.datasets[1].data = range.purchases;
        chart.update();
      });
    }
  }

  /* --------------------------------------------------- Inventory movement */
  function initInventoryChart(chartData) {
    var canvas = document.getElementById("inventoryChart");
    if (!canvas || typeof Chart === "undefined" || !chartData) return;
    var ctx = canvas.getContext("2d");

    // Real data (Phase 8.96, docs/09_DASHBOARD.md §3b) — received/dispatched
    // by InventoryMovement.quantity_change sign, last 6 months.
    var series = chartData.inventory_movement;

    new Chart(ctx, {
      type: "line",
      data: {
        labels: series.labels,
        datasets: [
          {
            label: "Stock In",
            data: series.received,
            borderColor: COLORS.success,
            backgroundColor: "rgba(31,169,122,0.10)",
            tension: 0.35,
            pointRadius: 0,
            borderWidth: 2,
            fill: true
          },
          {
            label: "Stock Out",
            data: series.dispatched,
            borderColor: COLORS.danger,
            backgroundColor: "rgba(225,75,75,0.08)",
            tension: 0.35,
            pointRadius: 0,
            borderWidth: 2,
            fill: true
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: reduceMotion ? false : { duration: 500 },
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
            cornerRadius: 8
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { family: "Inter", size: 11 }, color: COLORS.slate } },
          y: { grid: { color: COLORS.slate200 }, ticks: { font: { family: "IBM Plex Mono", size: 11 }, color: COLORS.slate } }
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSidebarToggle();
    initDropdowns();
    var chartData = readDashboardChartData();
    initSalesChart(chartData);
    initInventoryChart(chartData);
  });
})();
