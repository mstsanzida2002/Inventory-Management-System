/* ==========================================================================
   ADJUSTMENT-FORM.JS — New Adjustment form and the real Approve/Reject
   row actions for adjustments/adjustments.html (Phase 7). Single-entity
   form (no line items) — plugs straight into modal-form.js like
   product-form.js/category-form.js/supplier-form.js, following the same
   fetch()-based onSubmit contract (Phase 5.5).

   The adjustment-type <select>'s option values changed from the mock's
   "Increase"/"Decrease" (display-only, since nothing read them before) to
   the model's real lowercase choice values ("increase"/"decrease") — the
   ModelForm validates against AdjustmentType.choices exactly, so the
   posted value has to match one of those, not just look right.
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var FORM_ID = "addAdjustmentForm";
  var MODAL_ID = "addAdjustmentModal";

  var FIELD_LABELS = {
    "adjustment-product": "Product",
    "adjustment-type": "Adjustment type",
    "adjustment-quantity": "Quantity",
    "adjustment-reason": "Reason"
  };

  var REQUIRED_FIELD_IDS = [
    "adjustment-product",
    "adjustment-type",
    "adjustment-quantity",
    "adjustment-reason"
  ];

  var NON_NEGATIVE_FIELD_IDS = ["adjustment-quantity"];

  var SERVER_FIELD_MAP = {
    product: "adjustment-product",
    adjustment_type: "adjustment-type",
    quantity: "adjustment-quantity",
    reason: "adjustment-reason"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError() {
    var box = getField("addAdjustmentFormError");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(message) {
    var box = getField("addAdjustmentFormError");
    if (box) { box.hidden = false; box.textContent = message; }
  }

  function applyServerErrors(errors) {
    Object.keys(errors).forEach(function (fieldName) {
      var fieldId = SERVER_FIELD_MAP[fieldName];
      var field = fieldId ? getField(fieldId) : null;
      var entries = errors[fieldName];
      var text = (entries && entries.length && entries[0].message) || "This field is invalid.";
      if (field) {
        FV.setFieldError(field, text);
      } else {
        showFormError(text);
      }
    });
  }

  function onSubmit(form) {
    clearFormError();
    return fetch(form.getAttribute("action"), {
      method: "POST",
      body: new FormData(form)
    }).then(function (response) {
      return response.json().catch(function () {
        return null;
      }).then(function (payload) {
        if (response.ok) {
          window.location.reload();
          return true;
        }
        if (payload && payload.errors) {
          applyServerErrors(payload.errors);
        } else {
          showFormError("Could not submit this adjustment. Please try again.");
        }
        return false;
      });
    }).catch(function () {
      showFormError("Could not reach the server. Please try again.");
      return false;
    });
  }

  /* --------------------------------------------------- row actions --- */

  function handleRowAction(event) {
    var row = event.target.closest("tr[data-adjustment-id]");
    if (!row) return;
    var adjustmentId = row.getAttribute("data-adjustment-id");
    var tableBody = getField("adjustmentsTableBody");
    var base = tableBody ? tableBody.getAttribute("data-base-url") : "/adjustments/";

    if (event.target.closest(".adj-approve-btn")) {
      if (!confirm("Approve this adjustment? Stock will change immediately.")) return;
      RowActions.postAction(base + adjustmentId + "/approve/").then(RowActions.reportResult);
    } else if (event.target.closest(".adj-reject-btn")) {
      var reason = prompt("Reason for rejecting this adjustment:");
      if (reason === null) return;
      if (!reason.trim()) { alert("A reason is required to reject an adjustment."); return; }
      var formData = new FormData();
      formData.append("reason", reason.trim());
      RowActions.postAction(base + adjustmentId + "/reject/", formData).then(RowActions.reportResult);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var tableBody = getField("adjustmentsTableBody");
    if (tableBody) tableBody.addEventListener("click", handleRowAction);

    if (!getField(FORM_ID)) return;

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      nonNegativeFieldIds: NON_NEGATIVE_FIELD_IDS,
      onReset: clearFormError,
      onSubmit: onSubmit
    });
  });
})();
