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

  function saleActionUrl(saleId, action) {
    var tableBody = getField("salesTableBody");
    var base = tableBody ? tableBody.getAttribute("data-base-url") : "/sales/";
    return base + saleId + "/" + action + "/";
  }

  function handleRowAction(event) {
    var row = event.target.closest("tr[data-sale-id]");
    if (!row) return;
    var saleId = row.getAttribute("data-sale-id");

    if (event.target.closest(".sale-submit-btn")) {
      if (!confirm("Submit this sale for approval?")) return;
      RowActions.postAction(saleActionUrl(saleId, "submit")).then(RowActions.reportResult);
    } else if (event.target.closest(".sale-approve-btn")) {
      if (!confirm("Approve this sale? Stock will be deducted immediately.")) return;
      RowActions.postAction(saleActionUrl(saleId, "approve")).then(RowActions.reportResult);
    } else if (event.target.closest(".sale-reject-btn")) {
      var reason = prompt("Reason for rejecting this sale:");
      if (reason === null) return;
      if (!reason.trim()) { alert("A reason is required to reject a sale."); return; }
      var formData = new FormData();
      formData.append("reason", reason.trim());
      RowActions.postAction(saleActionUrl(saleId, "reject"), formData).then(RowActions.reportResult);
    } else if (event.target.closest(".sale-cancel-btn")) {
      var cancelReason = prompt("Reason for cancelling this sale?");
      if (cancelReason === null) return;
      if (!cancelReason.trim()) { alert("A reason is required to cancel a sale."); return; }
      var cancelFormData = new FormData();
      cancelFormData.append("reason", cancelReason.trim());
      RowActions.postAction(saleActionUrl(saleId, "cancel"), cancelFormData).then(RowActions.reportResult);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    // Rule: search/status are server-side GET params, not client-side.
    var tableBody = getField("salesTableBody");
    if (tableBody) tableBody.addEventListener("click", handleRowAction);

    if (!getField(FORM_ID)) return;

    lineItems = LineItems.create({
      containerId: "sale-line-items",
      addButtonId: "sale-add-item",
      errorId: "sale-items-error",
      grandTotalId: "sale-grand-total",
      productOptionsHtml: realProductOptionsHtml(),
      priceAttr: "data-selling-price"
    });

    // Rule: no requiredFieldIds -- SaleTransaction has none beyond line items.
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
