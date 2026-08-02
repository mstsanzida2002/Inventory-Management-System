/* ==========================================================================
   CATEGORY-FORM.JS — Add Category form: field config and submitting to the
   real /categories/ endpoint (Phase 6). Generic validation/reset/submit
   wiring lives in modal-form.js; generic error-state helpers live in
   form-validation.js. This file only knows category-specific things.

   Submission happens in onSubmit via fetch(), following modal-form.js's
   Promise-returning onSubmit contract (documented in that file's header,
   added Phase 5.5) — unlike Phase 5's original product-form.js, this
   never needed a synchronous-XHR-in-extraValidate workaround, since that
   contract already existed by the time this module was built.
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var FORM_ID = "addCategoryForm";
  var MODAL_ID = "addCategoryModal";

  var FIELD_LABELS = {
    "category-name": "Category name"
  };

  var REQUIRED_FIELD_IDS = ["category-name"];

  // Django field name -> HTML field id, for server-side validation errors.
  var SERVER_FIELD_MAP = {
    name: "category-name",
    description: "category-description"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError() {
    var box = getField("addCategoryFormError");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(message) {
    var box = getField("addCategoryFormError");
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

  function onSubmit(form) {
    clearFormError();

    return fetch(form.getAttribute("action"), {
      method: "POST",
      body: new FormData(form)
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
          showFormError("Could not save this category. Please try again.");
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
      resettableFieldIds: ["category-name", "category-description", "category-status"],
      onReset: clearFormError,
      onSubmit: onSubmit
    });
  });
})();
