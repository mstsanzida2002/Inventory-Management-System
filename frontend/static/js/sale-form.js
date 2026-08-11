/* ==========================================================================
   SALE-FORM.JS — New Sale form (header + line items) and the real Cancel
   action for sales/sales.html (Phase 7).

   No requiredFieldIds at the top level — confirmed intentional, not an
   oversight: SaleTransaction has no required field beyond its line items
   (customer_name/notes are both blank=True on the model, matching
   06_SALES.md's "Customer info | Optional" rule exactly). Line items are
   still gated by extraValidate, same as before.

   line-items.js itself is untouched — see purchase-form.js's header for
   the same note on productOptionsHtml now coming from a real, server-
   rendered #realProductOptions template instead of mock-catalog.js.
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var FORM_ID = "addSaleForm";
  var MODAL_ID = "addSaleModal";

  var lineItems = null;

  var SERVER_FIELD_MAP = {
    customer_name: "sale-customer-name",
    notes: "sale-notes"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError() {
    var box = getField("addSaleFormError");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(message) {
    var box = getField("addSaleFormError");
    if (box) { box.hidden = false; box.textContent = message; }
  }

  function applyServerErrors(errors) {
    Object.keys(errors).forEach(function (fieldName) {
      var entries = errors[fieldName];
      var text = (entries && entries.length && entries[0].message) || "This field is invalid.";
      if (fieldName === "items") {
        showFormError(entries.map(function (e) { return e.message; }).join(" "));
        return;
      }
      var fieldId = SERVER_FIELD_MAP[fieldName];
      var field = fieldId ? getField(fieldId) : null;
      if (field) {
        FV.setFieldError(field, text);
      } else {
        showFormError(text);
      }
    });
  }

  function realProductOptionsHtml() {
    var template = getField("realProductOptions");
    return template ? template.innerHTML : "";
  }

  function onSubmit(form) {
    clearFormError();
    var formData = new FormData(form);
    formData.append("items_json", JSON.stringify(lineItems.getItems()));

    return fetch(form.getAttribute("action"), {
      method: "POST",
      body: formData
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
          showFormError("Could not complete this sale. Please try again.");
        }
        return false;
      });
    }).catch(function () {
      showFormError("Could not reach the server. Please try again.");
      return false;
    });
  }

  /* -------------------------------------------------------- cancel --- */

  function handleRowAction(event) {
    var btn = event.target.closest(".sale-cancel-btn");
    if (!btn) return;
    var row = event.target.closest("tr[data-sale-id]");
    if (!row) return;
    var saleId = row.getAttribute("data-sale-id");

    if (!confirm("Cancel this sale? Stock will be restored immediately.")) return;

    var tableBody = getField("salesTableBody");
    var base = tableBody ? tableBody.getAttribute("data-base-url") : "/sales/";
    RowActions.postAction(base + saleId + "/cancel/").then(RowActions.reportResult);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var tableBody = getField("salesTableBody");
    if (tableBody) tableBody.addEventListener("click", handleRowAction);

    if (!getField(FORM_ID)) return;

    lineItems = LineItems.create({
      containerId: "sale-line-items",
      addButtonId: "sale-add-item",
      errorId: "sale-items-error",
      grandTotalId: "sale-grand-total",
      productOptionsHtml: realProductOptionsHtml()
    });

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      resettableFieldIds: ["sale-customer-name", "sale-notes"],
      extraValidate: function () { return lineItems.validate({ minQuantity: 1 }); },
      onReset: function () { lineItems.reset(); clearFormError(); },
      onSubmit: onSubmit
    });
  });
})();
