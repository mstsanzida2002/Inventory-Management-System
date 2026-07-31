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
  function initSalesChart() {
    var canvas = document.getElementById("salesChart");
    if (!canvas || typeof Chart === "undefined") return;

    var datasets = {
      daily: {
        labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        sales:    [4200, 4830, 3950, 5210, 6040, 7120, 5460],
        purchases:[2100, 1800, 3200, 1500, 2600, 1900, 1200]
      },
      weekly: {
        labels: ["Week 1", "Week 2", "Week 3", "Week 4"],
        sales:    [28400, 31200, 26900, 34700],
        purchases:[14200, 16800, 12100, 18900]
      },
      monthly: {
        labels: ["Feb", "Mar", "Apr", "May", "Jun", "Jul"],
        sales:    [98200, 104500, 112300, 108900, 121400, 126800],
        purchases:[52100, 58300, 49700, 61200, 55600, 64100]
      }
    };

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
  function initInventoryChart() {
    var canvas = document.getElementById("inventoryChart");
    if (!canvas || typeof Chart === "undefined") return;
    var ctx = canvas.getContext("2d");

    new Chart(ctx, {
      type: "line",
      data: {
        labels: ["Feb", "Mar", "Apr", "May", "Jun", "Jul"],
        datasets: [
          {
            label: "Stock In",
            data: [6200, 7100, 5900, 8300, 7600, 8900],
            borderColor: COLORS.success,
            backgroundColor: "rgba(31,169,122,0.10)",
            tension: 0.35,
            pointRadius: 0,
            borderWidth: 2,
            fill: true
          },
          {
            label: "Stock Out",
            data: [5400, 6300, 6800, 7100, 6900, 7700],
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
    initSalesChart();
    initInventoryChart();
  });
})();
