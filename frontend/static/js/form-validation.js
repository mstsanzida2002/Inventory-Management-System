/* ==========================================================================
   FORM-VALIDATION.JS — generic, reusable field-level validation helpers.
   No DOM wiring, no modal knowledge — just get/set/clear error state on a
   single field, plus two validators. Shared by every modal form (product,
   category, supplier, ...) via modal-form.js.
   ========================================================================== */

(function () {
  "use strict";

  function getField(id) {
    return document.getElementById(id);
  }

  function getErrorElement(field) {
    return document.getElementById(field.id + "-error");
  }

  function setFieldError(field, message) {
    field.classList.add("has-error");
    var errorEl = getErrorElement(field);
    if (errorEl) errorEl.textContent = message;
  }

  function clearFieldError(field) {
    field.classList.remove("has-error");
    var errorEl = getErrorElement(field);
    if (errorEl) errorEl.textContent = "";
  }

  function validateRequired(field, label) {
    if (!field.value.trim()) {
      setFieldError(field, (label || "This field") + " is required.");
      return false;
    }
    clearFieldError(field);
    return true;
  }

  function validateNonNegative(field, label) {
    var value = field.value.trim();
    if (value === "") return true; // optional numeric fields may be left blank

    var number = Number(value);
    if (Number.isNaN(number) || number < 0) {
      setFieldError(field, (label || "This field") + " cannot be negative.");
      return false;
    }
    clearFieldError(field);
    return true;
  }

  function focusFirstInvalid(container) {
    var firstInvalid = container.querySelector(".has-error");
    if (firstInvalid) firstInvalid.focus();
  }

  window.FormValidation = {
    getField: getField,
    setFieldError: setFieldError,
    clearFieldError: clearFieldError,
    validateRequired: validateRequired,
    validateNonNegative: validateNonNegative,
    focusFirstInvalid: focusFirstInvalid
  };
})();
