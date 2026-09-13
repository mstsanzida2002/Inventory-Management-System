// Rule: owns the form-in-a-modal lifecycle -- validate, submit, close/reset.

(function () {
  "use strict";

  var FV = window.FormValidation;

  function initModalForm(config) {
    var form = FV.getField(config.formId);
    if (!form) return;

    var requiredIds = config.requiredFieldIds || [];
    var nonNegativeIds = config.nonNegativeFieldIds || [];
    var labels = config.fieldLabels || {};
    var resettableIds = config.resettableFieldIds || requiredIds.concat(nonNegativeIds);

    function validateAll() {
      var isValid = true;

      requiredIds.forEach(function (id) {
        var field = FV.getField(id);
        if (field && !FV.validateRequired(field, labels[id])) isValid = false;
      });

      nonNegativeIds.forEach(function (id) {
        var field = FV.getField(id);
        if (field && !FV.validateNonNegative(field, labels[id])) isValid = false;
      });

      return isValid;
    }

    requiredIds.forEach(function (id) {
      var field = FV.getField(id);
      if (field) field.addEventListener("blur", function () { FV.validateRequired(field, labels[id]); });
    });

    nonNegativeIds.forEach(function (id) {
      var field = FV.getField(id);
      if (field) field.addEventListener("input", function () { FV.validateNonNegative(field, labels[id]); });
    });

    function closeModal() {
      if (window.InventoryModal) window.InventoryModal.close(config.modalId);
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      // Rule: extraValidate() short-circuits -- only runs once standard fields pass.
      var isStandardValid = validateAll();
      var isExtraValid = isStandardValid && (
        typeof config.extraValidate === "function" ? config.extraValidate() : true
      );

      if (!isStandardValid || !isExtraValid) {
        FV.focusFirstInvalid(form);
        return;
      }

      var result = typeof config.onSubmit === "function" ? config.onSubmit(form) : undefined;

      // Assumption: a resolved false or {success:false} means failure.
      if (result && typeof result.then === "function") {
        result.then(function (outcome) {
          var failed = outcome === false || (outcome && typeof outcome === "object" && outcome.success === false);
          if (!failed) closeModal();
        }, function () {
          // Rule: a rejection is a failure too -- onSubmit reports its own error.
        });
        return;
      }

      closeModal();
    });

    document.addEventListener("modal:close", function (event) {
      if (!event.detail || event.detail.id !== config.modalId) return;

      form.reset();
      resettableIds.forEach(function (id) {
        var field = FV.getField(id);
        if (field) FV.clearFieldError(field);
      });
      if (typeof config.onReset === "function") config.onReset(form);
    });

    if (typeof config.onInit === "function") config.onInit(form);
  }

  window.ModalForm = { init: initModalForm };
})();
