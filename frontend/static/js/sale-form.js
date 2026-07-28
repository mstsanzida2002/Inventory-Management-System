/* ==========================================================================
   SALE-FORM.JS — New Sale form: header fields + line items, turning a valid
   submit into a new "Completed" row in the sales table. Mirrors
   modules/06_SALES.md's SaleCreateSerializer: quantity uses min_value=1
   (documented explicitly, unlike the Purchase form's ordered_qty, which
   the docs only constrain to non-negative).
   ========================================================================== */

(function () {
  "use strict";

  var FORM_ID = "addSaleForm";
  var MODAL_ID = "addSaleModal";
  var TABLE_BODY_ID = "salesTableBody";

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

  function buildInvoiceNumber() {
    var now = new Date();
    var y = now.getFullYear();
    var m = String(now.getMonth() + 1).padStart(2, "0");
    var d = String(now.getDate()).padStart(2, "0");
    var rand = Math.floor(1000 + Math.random() * 9000);
    return "INV-" + y + m + d + "-" + rand;
  }

  function computeTotal(items) {
    return items.reduce(function (sum, item) {
      return sum + (item.unitPrice * item.quantity) * (1 - item.discount / 100) * (1 + item.tax / 100);
    }, 0);
  }

  function buildSaleRow(data) {
    var row = document.createElement("tr");

    var invoiceCell = document.createElement("td");
    invoiceCell.className = "mono";
    invoiceCell.textContent = data.invoiceNumber;
    row.appendChild(invoiceCell);

    var customerCell = document.createElement("td");
    customerCell.textContent = data.customerName || "Walk-in customer";
    row.appendChild(customerCell);

    var dateCell = document.createElement("td");
    dateCell.className = "mono";
    dateCell.textContent = formatDate(new Date());
    row.appendChild(dateCell);

    var itemsCell = document.createElement("td");
    itemsCell.className = "mono";
    itemsCell.textContent = String(data.items.length);
    row.appendChild(itemsCell);

    var totalCell = document.createElement("td");
    totalCell.className = "mono";
    totalCell.textContent = formatCurrency(computeTotal(data.items));
    row.appendChild(totalCell);

    var statusCell = document.createElement("td");
    var badge = document.createElement("span");
    badge.className = "badge badge-success";
    badge.textContent = "Completed";
    statusCell.appendChild(badge);
    row.appendChild(statusCell);

    var actionsCell = document.createElement("td");
    var actionsWrap = document.createElement("div");
    actionsWrap.className = "widget-actions";
    actionsWrap.appendChild(DomUtils.buildActionButton("View invoice", "icon-external"));
    var cancelBtn = DomUtils.buildActionButton("Cancel sale", "icon-x");
    cancelBtn.classList.add("reject");
    actionsWrap.appendChild(cancelBtn);
    actionsCell.appendChild(actionsWrap);
    row.appendChild(actionsCell);

    return row;
  }

  function addSaleToTable(data) {
    var tableBody = getField(TABLE_BODY_ID);
    if (!tableBody) return;
    tableBody.insertBefore(buildSaleRow(data), tableBody.firstChild);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!getField(FORM_ID)) return;

    lineItems = LineItems.create({
      containerId: "sale-line-items",
      addButtonId: "sale-add-item",
      errorId: "sale-items-error",
      grandTotalId: "sale-grand-total",
      productOptionsHtml: window.MockCatalog ? MockCatalog.productOptionsHtml : ""
    });

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      extraValidate: function () { return lineItems.validate({ minQuantity: 1 }); },
      onReset: function () { lineItems.reset(); },
      onSubmit: function () {
        addSaleToTable({
          invoiceNumber: buildInvoiceNumber(),
          customerName: getField("sale-customer-name").value.trim(),
          items: lineItems.getItems()
        });
      }
    });
  });
})();
