/* ==========================================================================
   REPORTS.JS — Reports page (Phase 8). Low Stock preview keeps a real
   client-side category filter via table-filter.js (each row still carries
   a real Category). Sales preview dropped its per-row category (a sale can
   span multiple product categories — see reports.html's own comment), so
   there's nothing left for table-filter.js to match there; its Category
   select is export-only now, read directly by report-export-btn's click
   handler below alongside both panels' date range.

   Phase 13 — the Sales Report panel's revenue-by-day chart, same Chart.js
   setup dashboard.js's own sales/purchases chart already uses (Chart.js +
   window.ChartColors, both loaded globally in dashboard_base.html) — not
   a new charting convention.
   ========================================================================== */

(function () {
  "use strict";

  var COLORS = window.ChartColors;

  function readSalesChartData() {
    var el = document.getElementById("salesChartData");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function initSalesRevenueChart() {
    var canvas = document.getElementById("salesRevenueChart");
    var chartData = readSalesChartData();
    if (!canvas || typeof Chart === "undefined" || !chartData || !COLORS) return;

    new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: chartData.labels,
        datasets: [{
          label: "Revenue",
          data: chartData.values,
          backgroundColor: COLORS.indigo,
          borderRadius: 6,
          barThickness: 18
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: COLORS.ink,
            titleFont: { family: "Inter", size: 12, weight: "600" },
            bodyFont: { family: "IBM Plex Mono", size: 12 },
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: function (item) { return "Revenue: $" + item.formattedValue; }
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
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSalesRevenueChart();

    if (document.getElementById("lowStockReportTableBody")) {
      TableFilter.init({
        tableBodyId: "lowStockReportTableBody",
        selectFilters: [{ id: "lowStockReportCategory", attr: "data-category" }],
        emptyStateId: "lowStockReportEmptyState",
      });
    }

    var PANEL_FILTERS = {
      sales: { from: "salesReportFrom", to: "salesReportTo", category: "salesReportCategory" },
      "low-stock": { category: "lowStockReportCategory" },
    };

    document.querySelectorAll(".report-export-btn").forEach(function (button) {
      button.addEventListener("click", function () {
        var panel = button.getAttribute("data-panel");
        var format = button.getAttribute("data-format");
        var base = button.getAttribute("data-base-url");
        var fields = PANEL_FILTERS[panel] || {};

        var params = new URLSearchParams();
        params.set("format", format);

        var fromField = fields.from && document.getElementById(fields.from);
        var toField = fields.to && document.getElementById(fields.to);
        var categoryField = fields.category && document.getElementById(fields.category);
        if (fromField && fromField.value) params.set("date_from", fromField.value);
        if (toField && toField.value) params.set("date_to", toField.value);
        if (categoryField && categoryField.value) params.set("category", categoryField.value);

        window.location.href = base + "?" + params.toString();
      });
    });
  });
})();
