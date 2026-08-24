/* ==========================================================================
   SETTINGS-FORM.JS — Settings page submit. Not modal-form.js — this is a
   plain full-page form (no modal to open/close/reset), so it wires its own
   fetch()-based submit directly rather than going through ModalForm.init.
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var FORM_ID = "settingsForm";

  var SERVER_FIELD_MAP = {
    company_name: "settings-company-name",
    company_logo: "settings-company-logo",
    company_address: "settings-company-address",
    company_email: "settings-company-email",
    company_phone: "settings-company-phone",
    company_tax_number: "settings-company-tax-number",
    company_website: "settings-company-website",
    default_reorder_level: "settings-default-reorder-level",
    forecast_period_weeks: "settings-forecast-period-weeks",
    forecast_retrain_days: "settings-forecast-retrain-days",
    slow_moving_threshold_days: "settings-slow-moving-threshold",
    dead_stock_threshold_days: "settings-dead-stock-threshold",
    weight_recency: "settings-weight-recency",
    weight_turnover: "settings-weight-turnover",
    weight_coverage: "settings-weight-coverage",
    weight_frequency: "settings-weight-frequency",
    slow_index_threshold: "settings-slow-index-threshold",
    dead_index_threshold: "settings-dead-index-threshold",
    target_days_of_cover: "settings-target-days-of-cover",
    min_observation_days: "settings-min-observation-days",
    min_sale_events: "settings-min-sale-events",
    extreme_coverage_days: "settings-extreme-coverage-days",
    session_timeout_seconds: "settings-session-timeout"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearMessages() {
    var errorBox = getField("settingsFormError");
    var successBox = getField("settingsFormSuccess");
    if (errorBox) { errorBox.hidden = true; errorBox.textContent = ""; }
    if (successBox) successBox.hidden = true;
    Object.keys(SERVER_FIELD_MAP).forEach(function (name) {
      var field = getField(SERVER_FIELD_MAP[name]);
      if (field) FV.clearFieldError(field);
    });
  }

  function applyServerErrors(errors) {
    var errorBox = getField("settingsFormError");
    Object.keys(errors).forEach(function (fieldName) {
      var fieldId = SERVER_FIELD_MAP[fieldName];
      var field = fieldId ? getField(fieldId) : null;
      var entries = errors[fieldName];
      var text = (entries && entries.length && entries[0].message) || "This field is invalid.";
      if (field) {
        FV.setFieldError(field, text);
      } else if (errorBox) {
        errorBox.hidden = false;
        errorBox.textContent = text;
      }
    });
  }

  // Phase 13 — instant local preview of a newly-picked logo file, before
  // it's ever uploaded: FileReader reads the selected File straight from
  // the browser's own memory, no round trip needed, and the same <img>
  // stays correct after a successful save without a page reload (it's
  // already showing exactly the file that got submitted).
  function wireLogoPreview() {
    var input = getField("settings-company-logo");
    var preview = getField("settings-company-logo-preview");
    var filename = getField("settings-company-logo-filename");
    if (!input || !preview) return;

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function (e) {
        preview.src = e.target.result;
        preview.hidden = false;
      };
      reader.readAsDataURL(file);
      if (filename) filename.textContent = file.name;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireLogoPreview();

    var form = getField(FORM_ID);
    if (!form) return;

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearMessages();

      fetch(form.getAttribute("action"), {
        method: "POST",
        body: new FormData(form)
      }).then(function (response) {
        return response.json().catch(function () { return null; }).then(function (payload) {
          if (response.ok) {
            var successBox = getField("settingsFormSuccess");
            if (successBox) successBox.hidden = false;
            return;
          }
          if (payload && payload.errors) {
            applyServerErrors(payload.errors);
          } else {
            var errorBox = getField("settingsFormError");
            if (errorBox) { errorBox.hidden = false; errorBox.textContent = "Could not save settings. Please try again."; }
          }
        });
      }).catch(function () {
        var errorBox = getField("settingsFormError");
        if (errorBox) { errorBox.hidden = false; errorBox.textContent = "Could not reach the server. Please try again."; }
      });
    });
  });
})();
