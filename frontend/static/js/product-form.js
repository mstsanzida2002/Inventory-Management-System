/* ==========================================================================
   PRODUCT-FORM.JS — Add Product form: field config, image preview, and
   turning a valid submit into a new products-table row.
   Generic validation/reset/submit wiring lives in modal-form.js; generic
   error-state helpers live in form-validation.js; the shared pill-button
   builder lives in dom-utils.js. This file only knows product-specific
   things: which fields exist, and how to render a product table row.
   ========================================================================== */

(function () {
  "use strict";

  var FORM_ID = "addProductForm";
  var MODAL_ID = "addProductModal";
  var TABLE_BODY_ID = "productsTableBody";

  var FIELD_LABELS = {
    "product-name": "Product name",
    "product-category": "Category",
    "product-purchase-price": "Purchase price",
    "product-selling-price": "Selling price",
    "product-initial-stock": "Initial stock",
    "product-reorder-level": "Reorder level"
  };

  var REQUIRED_FIELD_IDS = [
    "product-name",
    "product-category",
    "product-purchase-price",
    "product-selling-price",
    "product-initial-stock"
  ];

  var NON_NEGATIVE_FIELD_IDS = [
    "product-purchase-price",
    "product-selling-price",
    "product-initial-stock",
    "product-reorder-level"
  ];

  function getField(id) {
    return document.getElementById(id);
  }

  function initImagePreview() {
    var input = getField("product-image");
    var preview = getField("product-image-preview");
    var filenameLabel = getField("product-image-filename");
    if (!input || !preview || !filenameLabel) return;

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];

      if (!file) {
        filenameLabel.textContent = "PNG or JPG, up to 5MB";
        preview.hidden = true;
        preview.src = "";
        return;
      }

      filenameLabel.textContent = file.name;
      var reader = new FileReader();
      reader.onload = function (event) {
        preview.src = event.target.result;
        preview.hidden = false;
      };
      reader.readAsDataURL(file);
    });
  }

  function resetImagePreview() {
    var preview = getField("product-image-preview");
    var filenameLabel = getField("product-image-filename");
    if (preview) { preview.hidden = true; preview.src = ""; }
    if (filenameLabel) filenameLabel.textContent = "PNG or JPG, up to 5MB";
  }

  function formatCurrency(value) {
    var number = Number(value) || 0;
    return "$" + number.toFixed(2);
  }

  function deriveStatus(stock, reorderLevel) {
    if (stock <= 0) return { label: "Out of stock", badgeClass: "badge-danger" };
    if (reorderLevel && stock <= reorderLevel) return { label: "Low stock", badgeClass: "badge-warning" };
    return { label: "In stock", badgeClass: "badge-success" };
  }

  function buildProductRow(data) {
    var row = document.createElement("tr");

    var nameCell = document.createElement("td");
    nameCell.appendChild(document.createTextNode(data.name));
    var skuSub = document.createElement("div");
    skuSub.className = "cell-sub";
    skuSub.textContent = data.sku || "No SKU";
    nameCell.appendChild(skuSub);
    row.appendChild(nameCell);

    var categoryCell = document.createElement("td");
    categoryCell.textContent = data.category;
    row.appendChild(categoryCell);

    var supplierCell = document.createElement("td");
    supplierCell.textContent = data.supplier || "—";
    row.appendChild(supplierCell);

    var stockCell = document.createElement("td");
    stockCell.className = "mono";
    stockCell.textContent = data.stock + (data.unit ? " " + data.unit : " units");
    row.appendChild(stockCell);

    var priceCell = document.createElement("td");
    priceCell.className = "mono";
    priceCell.textContent = formatCurrency(data.sellingPrice);
    row.appendChild(priceCell);

    var statusCell = document.createElement("td");
    var status = deriveStatus(data.stock, data.reorderLevel);
    var badge = document.createElement("span");
    badge.className = "badge " + status.badgeClass;
    badge.textContent = status.label;
    statusCell.appendChild(badge);
    row.appendChild(statusCell);

    var actionsCell = document.createElement("td");
    var actionsWrap = document.createElement("div");
    actionsWrap.className = "widget-actions";
    actionsWrap.appendChild(DomUtils.buildActionButton("Edit product", "icon-edit"));
    actionsWrap.appendChild(DomUtils.buildActionButton("Delete product", "icon-trash"));
    actionsCell.appendChild(actionsWrap);
    row.appendChild(actionsCell);

    return row;
  }

  function addProductToTable(data) {
    var tableBody = getField(TABLE_BODY_ID);
    if (!tableBody) return;
    tableBody.insertBefore(buildProductRow(data), tableBody.firstChild);
  }

  function collectFormData() {
    return {
      name: getField("product-name").value.trim(),
      sku: getField("product-sku").value.trim(),
      category: getField("product-category").value,
      supplier: getField("product-supplier").value,
      unit: getField("product-unit").value,
      purchasePrice: Number(getField("product-purchase-price").value),
      sellingPrice: Number(getField("product-selling-price").value),
      stock: Number(getField("product-initial-stock").value),
      reorderLevel: getField("product-reorder-level").value ? Number(getField("product-reorder-level").value) : 0
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
      resettableFieldIds: Object.keys(FIELD_LABELS).concat([
        "product-sku", "product-barcode", "product-brand", "product-supplier",
        "product-unit", "product-expiry-date", "product-description", "product-image"
      ]),
      onInit: initImagePreview,
      onReset: resetImagePreview,
      onSubmit: function () { addProductToTable(collectFormData()); }
    });
  });
})();
