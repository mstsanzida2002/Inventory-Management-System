/* ==========================================================================
   CHART-COLORS.JS — hex mirror of the design tokens in tokens.css, for use
   in <canvas> chart configs (Canvas drawing can't read CSS custom
   properties directly). Single source of truth — extracted from
   dashboard.js so every chart-bearing page (dashboard, forecasting,
   slow-moving) reads the same palette instead of re-declaring it.
   ========================================================================== */

(function () {
  "use strict";

  window.ChartColors = {
    indigo: "#3D4FE0",
    indigoSoft: "rgba(61, 79, 224, 0.12)",
    amber: "#F2A93B",
    amberSoft: "rgba(242, 169, 59, 0.16)",
    success: "#1FA97A",
    successSoft: "rgba(31, 169, 122, 0.14)",
    warning: "#F2A93B",
    danger: "#E14B4B",
    dangerSoft: "rgba(225, 75, 75, 0.12)",
    slate: "#64708A",
    slate200: "#E4E7EF",
    ink: "#10162B"
  };
})();
