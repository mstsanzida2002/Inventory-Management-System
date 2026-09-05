/* ==========================================================================
   PRODUCT-FORM.JS — Add Product form (Phase 5, updated Phase 5.5) and,
   since Phase 8.99e, Edit Product too — this project's first per-entity
   edit UI (see docs/project_memory.md §13). Generic validation/reset/
   submit wiring lives in modal-form.js; generic error-state helpers live
   in form-validation.js. This file only knows product-specific things:
   which fields exist on each of the two forms, and how to talk to the
   server.

   Add and Edit are two separate forms/modals (#addProductForm/
   #addProductModal, #editProductForm/#editProductModal) sharing this
   file's logic via small parameterized helpers, not two copies of it —
   modal-form.js's ModalForm.init() is explicitly designed to be called
   once per (formId, modalId) pair on the same page (see its own header),
   which is exactly what two independent forms need.

   Edit is pre-filled entirely client-side from the clicked row's own
   data-product JSON attribute (set server-side in ProductListCreateView.
   get(), frontend/views.py) — the same "compute once server-side, read
   via a data-* attribute" pattern the Receive modal already uses for its
   per-line quantities (purchases.html's receive_items_json), not a new
   fetch-before-open mechanism.

   SKU's <input> on the edit form has no `name` attribute (disabled, and
   deliberately not just visually so) — it can never be part of what's
   posted. Read-only-on-edit is a disclosed decision (see ProductUpdateView's
   own docstring, frontend/views.py) enforced server-side regardless.

   Phase 5.5: submission happens in onSubmit via fetch(), following
   modal-form.js's Promise-returning onSubmit contract (see that file's
   header) — the earlier synchronous-XHR-inside-extraValidate workaround
   is gone. modal-form.js now keeps the modal open/unreset while an async
   onSubmit is pending, and only closes it once the returned Promise
   resolves to something other than `false`/`{success:false}`, so there's
   no longer a need to smuggle the real request through extraValidate.
   ========================================================================== */

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

  // Django field name -> HTML field id, so a server-side validation error
  // (ProductForm.errors, keyed by model/form field name) lands on the
  // right input via form-validation.js's setFieldError.
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

  /* modal-form.js's onSubmit contract: return a Promise, resolving to
     `false` on failure (having already reported it via setFieldError/
     showFormError) so the modal stays open, or anything else on success
     so the modal closes. Shared by both Add and Edit — they only differ
     in which URL the form's own `action` attribute points to (static for
     Add, set per-row for Edit — see handleRowAction below) and which
     field-id map/error box errors should land on. */
  function makeOnSubmit(map, errorBoxId) {
    return function onSubmit(form) {
      clearFormError(errorBoxId);

      return fetch(form.getAttribute("action"), {
        method: "POST",
        body: new FormData(form)
      }).then(function (response) {
        return response.json().catch(function () {
          return null; // non-JSON response body
        }).then(function (payload) {
          if (response.ok) {
            // Real, server-rendered data (real Category/Supplier FK display,
            // real computed stock status) beats maintaining a second,
            // client-side row-building function that has to stay in sync
            // with the backend.
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

  /* ---------------------------------------------------- row actions --- */

  function handleRowAction(event) {
    var row = event.target.closest("tr[data-product-id]");
    if (!row) return;
    var productId = row.getAttribute("data-product-id");
    var tableBody = getField("productsTableBody");
    var base = tableBody.getAttribute("data-base-url");

    if (event.target.closest(".product-edit-btn")) {
      var product;
      try {
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
    // Pagination pass (2026-08-25) — search/category/status are real
    // server-side GET params now (frontend.filters.filter_products()),
    // submitted via the page's own <form method="get">; TableFilter's
    // client-side row-hiding would only ever see the current page's 10
    // rows, silently missing matches on later pages (REQ 14.11).
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
