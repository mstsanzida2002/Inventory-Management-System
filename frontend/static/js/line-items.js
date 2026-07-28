/* ==========================================================================
   LINE-ITEMS.JS — reusable repeatable-row line-item editor, shared by the
   Purchase and Sale forms. Both PurchaseOrderItem and SaleItem (see
   database/SCHEMA.md) share the exact same shape and total formula:
     line_total = (unit_price * qty) * (1 - discount/100) * (1 + tax/100)
   so this is one engine, config-driven, instead of two near-identical
   implementations.

   Usage:
     var items = LineItems.create({
       containerId: "purchase-line-items",
       addButtonId: "purchase-add-item",
       errorId: "purchase-items-error",
       grandTotalId: "purchase-grand-total",
       productOptionsHtml: MockCatalog.productOptionsHtml
     });
     items.validate({ minQuantity: 1 });   // true/false, paints inline errors
     items.getItems();                     // [{ productLabel, quantity, unitPrice, discount, tax }]
     items.reset();                        // back to exactly one empty row
   ========================================================================== */

(function () {
  "use strict";

  function computeLineTotal(quantity, unitPrice, discountPct, taxPct) {
    return (unitPrice * quantity) * (1 - discountPct / 100) * (1 + taxPct / 100);
  }

  function formatCurrency(value) {
    return "$" + (Number(value) || 0).toFixed(2);
  }

  function createController(config) {
    var container = document.getElementById(config.containerId);
    var addButton = document.getElementById(config.addButtonId);
    var errorEl = document.getElementById(config.errorId);
    var grandTotalEl = document.getElementById(config.grandTotalId);
    if (!container || !addButton) return null;

    function clearRowErrors(row) {
      row.querySelectorAll(".has-error").forEach(function (el) { el.classList.remove("has-error"); });
    }

    function recalculate() {
      var grandTotal = 0;
      container.querySelectorAll(".line-item-row").forEach(function (row) {
        var quantity = Number(row.querySelector(".line-item-qty").value) || 0;
        var unitPrice = Number(row.querySelector(".line-item-price").value) || 0;
        var discount = Number(row.querySelector(".line-item-discount").value) || 0;
        var tax = Number(row.querySelector(".line-item-tax").value) || 0;
        var lineTotal = computeLineTotal(quantity, unitPrice, discount, tax);
        row.querySelector(".line-item-total").textContent = formatCurrency(lineTotal);
        grandTotal += lineTotal;
      });
      if (grandTotalEl) grandTotalEl.textContent = formatCurrency(grandTotal);
    }

    function buildRow() {
      var row = document.createElement("div");
      row.className = "line-item-row";

      var productField = document.createElement("div");
      productField.className = "line-item-product-field";
      var select = document.createElement("select");
      select.className = "input line-item-product";
      select.innerHTML = '<option value="">Select product</option>' + (config.productOptionsHtml || "");
      productField.appendChild(select);

      var qtyField = document.createElement("div");
      qtyField.className = "line-item-qty-field";
      var qty = document.createElement("input");
      qty.className = "input input-plain line-item-qty";
      qty.type = "number"; qty.min = "0"; qty.step = "1"; qty.placeholder = "Qty";
      qtyField.appendChild(qty);

      var priceField = document.createElement("div");
      priceField.className = "line-item-price-field";
      var price = document.createElement("input");
      price.className = "input input-plain line-item-price";
      price.type = "number"; price.min = "0"; price.step = "0.01"; price.placeholder = "0.00";
      priceField.appendChild(price);

      var discountField = document.createElement("div");
      discountField.className = "line-item-discount-field";
      var discount = document.createElement("input");
      discount.className = "input input-plain line-item-discount";
      discount.type = "number"; discount.min = "0"; discount.step = "0.01"; discount.placeholder = "0";
      discountField.appendChild(discount);

      var taxField = document.createElement("div");
      taxField.className = "line-item-tax-field";
      var tax = document.createElement("input");
      tax.className = "input input-plain line-item-tax";
      tax.type = "number"; tax.min = "0"; tax.step = "0.01"; tax.placeholder = "0";
      taxField.appendChild(tax);

      var total = document.createElement("div");
      total.className = "line-item-total mono";
      total.textContent = "$0.00";

      var removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "pill-btn line-item-remove";
      removeBtn.setAttribute("aria-label", "Remove line item");
      removeBtn.innerHTML = '<svg class="icon icon-sm"><use href="#icon-trash"></use></svg>';

      row.appendChild(productField);
      row.appendChild(qtyField);
      row.appendChild(priceField);
      row.appendChild(discountField);
      row.appendChild(taxField);
      row.appendChild(total);
      row.appendChild(removeBtn);

      [qty, price, discount, tax].forEach(function (input) {
        input.addEventListener("input", recalculate);
      });
      select.addEventListener("change", function () { clearRowErrors(row); });
      removeBtn.addEventListener("click", function () {
        if (container.querySelectorAll(".line-item-row").length <= 1) return; // always keep one row
        row.remove();
        recalculate();
      });

      return row;
    }

    function addRow() {
      container.appendChild(buildRow());
      recalculate();
    }

    function showSummaryError(message) {
      if (errorEl) errorEl.textContent = message || "";
    }

    function validate(options) {
      var minQuantity = (options && options.minQuantity) || 0;
      var rows = Array.prototype.slice.call(container.querySelectorAll(".line-item-row"));
      var isValid = true;

      rows.forEach(function (row) {
        var select = row.querySelector(".line-item-product");
        var qty = row.querySelector(".line-item-qty");
        var price = row.querySelector(".line-item-price");
        var hasAnyValue = select.value || qty.value || price.value;

        clearRowErrors(row);
        if (!hasAnyValue) return; // an untouched blank row isn't an error by itself

        if (!select.value) { select.classList.add("has-error"); isValid = false; }

        var qtyNum = Number(qty.value);
        if (qty.value === "" || Number.isNaN(qtyNum) || qtyNum < minQuantity) {
          qty.classList.add("has-error"); isValid = false;
        }

        var priceNum = Number(price.value);
        if (price.value === "" || Number.isNaN(priceNum) || priceNum < 0) {
          price.classList.add("has-error"); isValid = false;
        }
      });

      var hasAtLeastOneComplete = rows.some(function (row) {
        return row.querySelector(".line-item-product").value &&
               row.querySelector(".line-item-qty").value &&
               row.querySelector(".line-item-price").value;
      });

      if (!hasAtLeastOneComplete) {
        showSummaryError("At least one complete line item (product, quantity, unit price) is required.");
        isValid = false;
      } else if (!isValid) {
        showSummaryError("Check the highlighted line items — quantity must be at least " + minQuantity +
          " and unit price cannot be negative.");
      } else {
        showSummaryError("");
      }

      return isValid;
    }

    function getItems() {
      return Array.prototype.slice.call(container.querySelectorAll(".line-item-row"))
        .map(function (row) {
          var select = row.querySelector(".line-item-product");
          return {
            productLabel: select.value,
            quantity: Number(row.querySelector(".line-item-qty").value) || 0,
            unitPrice: Number(row.querySelector(".line-item-price").value) || 0,
            discount: Number(row.querySelector(".line-item-discount").value) || 0,
            tax: Number(row.querySelector(".line-item-tax").value) || 0
          };
        })
        .filter(function (item) { return item.productLabel && item.quantity && item.unitPrice; });
    }

    function reset() {
      container.innerHTML = "";
      showSummaryError("");
      addRow();
    }

    addButton.addEventListener("click", addRow);
    addRow(); // start with exactly one row

    return { validate: validate, getItems: getItems, reset: reset, recalculate: recalculate };
  }

  window.LineItems = { create: createController };
})();
