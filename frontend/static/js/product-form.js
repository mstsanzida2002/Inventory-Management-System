/* ==========================================================================
   PRODUCT-FORM.JS — Add Product form: field config, image preview, and
   submitting to the real /products/ endpoint (Phase 5, updated Phase 5.5).
   Generic validation/reset/submit wiring lives in modal-form.js; generic
   error-state helpers live in form-validation.js. This file only knows
   product-specific things: which fields exist, and how to talk to the
   server.

   Phase 5.5: submission now happens in onSubmit via fetch(), following
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

  var FORM_ID = "addProductForm";
  var MODAL_ID = "addProductModal";

  var FIELD_LABELS = {
    "product-name": "Product name",
    "product-category": "Category",
    "product-supplier": "Supplier",
    "product-purchase-price": "Purchase price",
    "product-selling-price": "Selling price",
    "product-reorder-level": "Reorder level"
  };

  var REQUIRED_FIELD_IDS = [
    "product-name",
    "product-category",
    "product-supplier",
    "product-purchase-price",
    "product-selling-price"
  ];

  var NON_NEGATIVE_FIELD_IDS = [
    "product-purchase-price",
    "product-selling-price",
    "product-reorder-level"
  ];

  // Django field name -> HTML field id, so a server-side validation error
  // (ProductForm.errors, keyed by model/form field name) lands on the
  // right input via form-validation.js's setFieldError.
  var SERVER_FIELD_MAP = {
    name: "product-name",
    sku: "product-sku",
    barcode: "product-barcode",
    category: "product-category",
    supplier: "product-supplier",
    brand: "product-brand",
    unit: "product-unit",
    purchase_price: "product-purchase-price",
    selling_price: "product-selling-price",
    reorder_level: "product-reorder-level",
    description: "product-description",
    image: "product-image"
  };

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
        filenameLabel.textContent = "PNG, JPG, or WEBP, up to 5MB";
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
    if (filenameLabel) filenameLabel.textContent = "PNG, JPG, or WEBP, up to 5MB";
  }

  function clearFormError() {
    var box = getField("addProductFormError");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(message) {
    var box = getField("addProductFormError");
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

  /* modal-form.js's onSubmit contract: return a Promise, resolving to
     `false` on failure (having already reported it via setFieldError/
     showFormError) so the modal stays open, or anything else on success
     so the modal closes. */
  function onSubmit(form) {
    clearFormError();

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
          applyServerErrors(payload.errors);
        } else {
          showFormError("Could not save this product. Please try again.");
        }
        return false;
      });
    }).catch(function () {
      showFormError("Could not reach the server. Please try again.");
      return false;
    });
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
      onReset: function () { resetImagePreview(); clearFormError(); },
      onSubmit: onSubmit
    });
  });
})();
