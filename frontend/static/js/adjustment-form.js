/* ==========================================================================
   ADJUSTMENT-FORM.JS — New Adjustment form: field config + turning a valid
   submit into a new "Pending approval" row in the adjustments table.
   Single-entity form (no line items) — plugs straight into modal-form.js
   like product-form.js / category-form.js / supplier-form.js.
   ========================================================================== */

(function () {
  "use strict";

  var FORM_ID = "addAdjustmentForm";
  var MODAL_ID = "addAdjustmentModal";
  var TABLE_BODY_ID = "adjustmentsTableBody";

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

  var referenceCounter = 521; // seed matches the highest AJ-#### already in the mock table

  function getField(id) {
    return document.getElementById(id);
  }

  function buildReference() {
    referenceCounter += 1;
    return "AJ-" + String(referenceCounter).padStart(4, "0");
  }

  function buildAdjustmentRow(data) {
    var row = document.createElement("tr");

    var refCell = document.createElement("td");
    refCell.className = "mono";
    refCell.textContent = data.reference;
    row.appendChild(refCell);

    var productCell = document.createElement("td");
    productCell.textContent = data.productLabel;
    row.appendChild(productCell);

    var typeCell = document.createElement("td");
    var typeBadge = document.createElement("span");
    typeBadge.className = "badge " + (data.adjustmentType === "Increase" ? "badge-success" : "badge-danger");
    typeBadge.textContent = data.adjustmentType;
    typeCell.appendChild(typeBadge);
    row.appendChild(typeCell);

    var qtyCell = document.createElement("td");
    qtyCell.className = "mono";
    qtyCell.textContent = data.quantity + (data.quantity === 1 ? " unit" : " units");
    row.appendChild(qtyCell);

    var reasonCell = document.createElement("td");
    reasonCell.textContent = data.reason;
    row.appendChild(reasonCell);

    var requestedByCell = document.createElement("td");
    requestedByCell.textContent = "You";
    row.appendChild(requestedByCell);

    var statusCell = document.createElement("td");
    var statusBadge = document.createElement("span");
    statusBadge.className = "badge badge-warning";
    statusBadge.textContent = "Pending approval";
    statusCell.appendChild(statusBadge);
    row.appendChild(statusCell);

    var actionsCell = document.createElement("td");
    var actionsWrap = document.createElement("div");
    actionsWrap.className = "widget-actions";
    var approveBtn = DomUtils.buildActionButton("Approve adjustment", "icon-check-circle");
    approveBtn.classList.add("approve");
    var rejectBtn = DomUtils.buildActionButton("Reject adjustment", "icon-x");
    rejectBtn.classList.add("reject");
    actionsWrap.appendChild(approveBtn);
    actionsWrap.appendChild(rejectBtn);
    actionsCell.appendChild(actionsWrap);
    row.appendChild(actionsCell);

    return row;
  }

  function addAdjustmentToTable(data) {
    var tableBody = getField(TABLE_BODY_ID);
    if (!tableBody) return;
    tableBody.insertBefore(buildAdjustmentRow(data), tableBody.firstChild);
  }

  function collectFormData() {
    var productSelect = getField("adjustment-product");
    return {
      reference: buildReference(),
      productLabel: productSelect.value,
      adjustmentType: getField("adjustment-type").value,
      quantity: Number(getField("adjustment-quantity").value),
      reason: getField("adjustment-reason").value.trim()
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!getField(FORM_ID)) return;

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      nonNegativeFieldIds: NON_NEGATIVE_FIELD_IDS,
      onSubmit: function () { addAdjustmentToTable(collectFormData()); }
    });
  });
})();
