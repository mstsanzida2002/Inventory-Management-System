// Rule: owns field-level validation state only -- no DOM or modal knowledge.

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
    if (value === "") return true; // Rule: blank is valid -- this field is optional.

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
