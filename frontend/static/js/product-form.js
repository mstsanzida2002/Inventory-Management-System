(function () {
  "use strict";

  var FV = window.FormValidation;

  var ADD_FORM_ID = "addProductForm";
  var ADD_MODAL_ID = "addProductModal";
  var EDIT_FORM_ID = "editProductForm";
  var EDIT_MODAL_ID = "editProductModal";

  var ADD_FIELD_LABELS = {
    "product-name": "Product name",
    "product-category": "Category",
    "product-supplier": "Supplier",
    "product-purchase-price": "Purchase price",
    "product-selling-price": "Selling price",
    "product-tax-rate": "Tax rate",
    "product-reorder-level": "Reorder level"
  };

  var EDIT_FIELD_LABELS = {
    "edit-product-name": "Product name",
    "edit-product-category": "Category",
    "edit-product-supplier": "Supplier",
    "edit-product-purchase-price": "Purchase price",
    "edit-product-selling-price": "Selling price",
    "edit-product-tax-rate": "Tax rate",
    "edit-product-reorder-level": "Reorder level"
  };

  var ADD_REQUIRED_FIELD_IDS = [
    "product-name", "product-category", "product-supplier",
    "product-purchase-price", "product-selling-price", "product-tax-rate"
  ];
  var EDIT_REQUIRED_FIELD_IDS = [
    "edit-product-name", "edit-product-category", "edit-product-supplier",
    "edit-product-purchase-price", "edit-product-selling-price", "edit-product-tax-rate"
  ];

  var ADD_NON_NEGATIVE_FIELD_IDS = [
    "product-purchase-price", "product-selling-price", "product-tax-rate", "product-reorder-level"
  ];
  var EDIT_NON_NEGATIVE_FIELD_IDS = [
    "edit-product-purchase-price", "edit-product-selling-price", "edit-product-tax-rate", "edit-product-reorder-level"
  ];

  // Assumption: maps Django field names to HTML ids for setFieldError().
  var ADD_SERVER_FIELD_MAP = {
    name: "product-name", sku: "product-sku", barcode: "product-barcode",
    category: "product-category", supplier: "product-supplier", brand: "product-brand",
    unit: "product-unit", purchase_price: "product-purchase-price",
    selling_price: "product-selling-price", tax_rate: "product-tax-rate",
    reorder_level: "product-reorder-level"
  };
  var EDIT_SERVER_FIELD_MAP = {
    name: "edit-product-name", sku: "edit-product-sku", barcode: "edit-product-barcode",
    category: "edit-product-category", supplier: "edit-product-supplier", brand: "edit-product-brand",
    unit: "edit-product-unit", purchase_price: "edit-product-purchase-price",
    selling_price: "edit-product-selling-price", tax_rate: "edit-product-tax-rate",
    reorder_level: "edit-product-reorder-level"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError(errorBoxId) {
    var box = getField(errorBoxId);
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(errorBoxId, message) {
    var box = getField(errorBoxId);
    if (box) { box.hidden = false; box.textContent = message; }
  }

  function applyServerErrors(errors, map, errorBoxId) {
    Object.keys(errors).forEach(function (fieldName) {
      var fieldId = map[fieldName];
      var field = fieldId ? getField(fieldId) : null;
      var entries = errors[fieldName];
      var text = (entries && entries.length && entries[0].message) || "This field is invalid.";
      if (field) {
        FV.setFieldError(field, text);
      } else {
        showFormError(errorBoxId, text);
      }
    });
  }

  function makeOnSubmit(map, errorBoxId) {
    return function onSubmit(form) {
      clearFormError(errorBoxId);

      return fetch(form.getAttribute("action"), {
        method: "POST",
        body: new FormData(form)
      }).then(function (response) {
        return response.json().catch(function () {
          return null;
        }).then(function (payload) {
          if (response.ok) {
            // Rule: reload for real server-rendered rows, not a client-side rebuild.
            window.location.reload();
            return true;
          }
          if (payload && payload.errors) {
            applyServerErrors(payload.errors, map, errorBoxId);
          } else {
            showFormError(errorBoxId, "Could not save this product. Please try again.");
          }
          return false;
        });
      }).catch(function () {
        showFormError(errorBoxId, "Could not reach the server. Please try again.");
        return false;
      });
    };
  }

  function prefillEditForm(product) {
    var setValue = function (id, value) {
      var field = getField(id);
      if (field) field.value = value || "";
    };
    setValue("edit-product-name", product.name);
    setValue("edit-product-sku", product.sku);
    setValue("edit-product-barcode", product.barcode);
    setValue("edit-product-category", product.category);
    setValue("edit-product-supplier", product.supplier);
    setValue("edit-product-brand", product.brand);
    setValue("edit-product-unit", product.unit);
    setValue("edit-product-purchase-price", product.purchase_price);
    setValue("edit-product-selling-price", product.selling_price);
    setValue("edit-product-tax-rate", product.tax_rate);
    setValue("edit-product-reorder-level", product.reorder_level);
  }

  function handleRowAction(event) {
    var row = event.target.closest("tr[data-product-id]");
    if (!row) return;
    var productId = row.getAttribute("data-product-id");
    var tableBody = getField("productsTableBody");
    var base = tableBody.getAttribute("data-base-url");

    if (event.target.closest(".product-edit-btn")) {
      var product;
      try {
        // Assumption: data-product is server-rendered by ProductListCreateView.
        product = JSON.parse(row.getAttribute("data-product") || "{}");
      } catch (e) {
        product = {};
      }
      var form = getField(EDIT_FORM_ID);
      if (form) form.setAttribute("action", base + productId + "/update/");
      prefillEditForm(product);
      if (window.InventoryModal) window.InventoryModal.open(EDIT_MODAL_ID);
    } else if (event.target.closest(".product-deactivate-btn")) {
      if (!confirm("Deactivate this product? It will no longer appear in purchase or sale forms; its past transactions still will.")) return;
      RowActions.postAction(base + productId + "/deactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".product-reactivate-btn")) {
      RowActions.postAction(base + productId + "/reactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".product-delete-btn")) {
      if (!confirm("Permanently delete this product? This cannot be undone.")) return;
      RowActions.postAction(base + productId + "/delete/").then(RowActions.reportResult);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    // Rule: search/category/status are server-side GET params, not client-side.
    var tableBody = getField("productsTableBody");
    if (tableBody) tableBody.addEventListener("click", handleRowAction);

    if (getField(ADD_FORM_ID)) {
      ModalForm.init({
        formId: ADD_FORM_ID,
        modalId: ADD_MODAL_ID,
        fieldLabels: ADD_FIELD_LABELS,
        requiredFieldIds: ADD_REQUIRED_FIELD_IDS,
        nonNegativeFieldIds: ADD_NON_NEGATIVE_FIELD_IDS,
        resettableFieldIds: Object.keys(ADD_FIELD_LABELS).concat([
          "product-sku", "product-barcode", "product-brand", "product-supplier",
          "product-unit", "product-expiry-date"
        ]),
        onReset: function () { clearFormError("addProductFormError"); },
        onSubmit: makeOnSubmit(ADD_SERVER_FIELD_MAP, "addProductFormError")
      });
    }

    if (getField(EDIT_FORM_ID)) {
      ModalForm.init({
        formId: EDIT_FORM_ID,
        modalId: EDIT_MODAL_ID,
        fieldLabels: EDIT_FIELD_LABELS,
        requiredFieldIds: EDIT_REQUIRED_FIELD_IDS,
        nonNegativeFieldIds: EDIT_NON_NEGATIVE_FIELD_IDS,
        resettableFieldIds: Object.keys(EDIT_FIELD_LABELS).concat([
          "edit-product-sku", "edit-product-barcode", "edit-product-brand", "edit-product-supplier",
          "edit-product-unit"
        ]),
        onReset: function () { clearFormError("editProductFormError"); },
        onSubmit: makeOnSubmit(EDIT_SERVER_FIELD_MAP, "editProductFormError")
      });
    }
  });
})();
