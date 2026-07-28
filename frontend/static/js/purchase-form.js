/* ==========================================================================
   PURCHASE-FORM.JS — New Purchase Order form: header fields + line items,
   turning a valid submit into a new "Draft" row in the purchase-orders
   table. Mirrors modules/05_PURCHASES.md: this performs only the documented
   "create PO as draft" step (PurchaseService.submit_for_approval is a
   separate, later action, not part of this form).
   ========================================================================== */

(function () {
  "use strict";

  var FORM_ID = "addPurchaseForm";
  var MODAL_ID = "addPurchaseModal";
  var TABLE_BODY_ID = "purchasesTableBody";

  var FIELD_LABELS = { "purchase-supplier": "Supplier" };
  var REQUIRED_FIELD_IDS = ["purchase-supplier"];

  var lineItems = null;

  function getField(id) {
    return document.getElementById(id);
  }

  function formatCurrency(value) {
    return "$" + (Number(value) || 0).toFixed(2);
  }

  function formatDate(date) {
    return date.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" });
  }

  function buildPoNumber() {
    var now = new Date();
    var y = now.getFullYear();
    var m = String(now.getMonth() + 1).padStart(2, "0");
    var d = String(now.getDate()).padStart(2, "0");
    var rand = Math.floor(1000 + Math.random() * 9000);
    return "PO-" + y + m + d + "-" + rand;
  }

  function computeTotal(items) {
    return items.reduce(function (sum, item) {
      return sum + (item.unitPrice * item.quantity) * (1 - item.discount / 100) * (1 + item.tax / 100);
    }, 0);
  }

  function buildPurchaseRow(data) {
    var row = document.createElement("tr");

    var poCell = document.createElement("td");
    poCell.className = "mono";
    poCell.textContent = data.poNumber;
    row.appendChild(poCell);

    var supplierCell = document.createElement("td");
    supplierCell.appendChild(document.createTextNode(data.supplier));
    var sub = document.createElement("div");
    sub.className = "cell-sub";
    sub.textContent = data.items.length + (data.items.length === 1 ? " line item" : " line items");
    supplierCell.appendChild(sub);
    row.appendChild(supplierCell);

    var createdByCell = document.createElement("td");
    createdByCell.textContent = "You";
    row.appendChild(createdByCell);

    var dateCell = document.createElement("td");
    dateCell.className = "mono";
    dateCell.textContent = formatDate(new Date());
    row.appendChild(dateCell);

    var totalCell = document.createElement("td");
    totalCell.className = "mono";
    totalCell.textContent = formatCurrency(computeTotal(data.items));
    row.appendChild(totalCell);

    var statusCell = document.createElement("td");
    var badge = document.createElement("span");
    badge.className = "badge badge-indigo";
    badge.textContent = "Draft";
    statusCell.appendChild(badge);
    row.appendChild(statusCell);

    var actionsCell = document.createElement("td");
    var actionsWrap = document.createElement("div");
    actionsWrap.className = "widget-actions";
    actionsWrap.appendChild(DomUtils.buildActionButton("Edit PO", "icon-edit"));
    actionsWrap.appendChild(DomUtils.buildActionButton("Delete PO", "icon-trash"));
    actionsCell.appendChild(actionsWrap);
    row.appendChild(actionsCell);

    return row;
  }

  function addPurchaseToTable(data) {
    var tableBody = getField(TABLE_BODY_ID);
    if (!tableBody) return;
    tableBody.insertBefore(buildPurchaseRow(data), tableBody.firstChild);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!getField(FORM_ID)) return;

    lineItems = LineItems.create({
      containerId: "purchase-line-items",
      addButtonId: "purchase-add-item",
      errorId: "purchase-items-error",
      grandTotalId: "purchase-grand-total",
      productOptionsHtml: window.MockCatalog ? MockCatalog.productOptionsHtml : ""
    });

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      extraValidate: function () { return lineItems.validate({ minQuantity: 0 }); },
      onReset: function () { lineItems.reset(); },
      onSubmit: function () {
        addPurchaseToTable({
          poNumber: buildPoNumber(),
          supplier: getField("purchase-supplier").value,
          items: lineItems.getItems()
        });
      }
    });
  });
})();
