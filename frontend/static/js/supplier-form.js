/* ==========================================================================
   SUPPLIER-FORM.JS — Add Supplier form: field config and submitting to the
   real /suppliers/ endpoint (Phase 6). Generic validation/reset/submit
   wiring lives in modal-form.js; generic error-state helpers live in
   form-validation.js. This file only knows supplier-specific things.

   Submission happens in onSubmit via fetch(), following modal-form.js's
   Promise-returning onSubmit contract (see category-form.js's header for
   the same note — no sync-XHR workaround needed here either).
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var FORM_ID = "addSupplierForm";
  var MODAL_ID = "addSupplierModal";

  var FIELD_LABELS = {
    "supplier-name": "Supplier name",
    "supplier-company-name": "Company name",
    "supplier-contact-person": "Contact person",
    "supplier-email": "Email",
    "supplier-phone": "Phone",
    "supplier-address": "Address"
  };

  var REQUIRED_FIELD_IDS = [
    "supplier-name",
    "supplier-company-name",
    "supplier-contact-person",
    "supplier-email",
    "supplier-phone",
    "supplier-address"
  ];

  // Django field name -> HTML field id, for server-side validation errors.
  var SERVER_FIELD_MAP = {
    supplier_name: "supplier-name",
    company_name: "supplier-company-name",
    contact_person: "supplier-contact-person",
    email: "supplier-email",
    phone: "supplier-phone",
    address: "supplier-address"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError() {
    var box = getField("addSupplierFormError");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(message) {
    var box = getField("addSupplierFormError");
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
          showFormError("Could not save this supplier. Please try again.");
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
      resettableFieldIds: Object.keys(FIELD_LABELS).concat(["supplier-status"]),
      onReset: clearFormError,
      onSubmit: onSubmit
    });
  });
})();
