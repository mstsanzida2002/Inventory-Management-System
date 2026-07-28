/* ==========================================================================
   MODAL-FORM.JS — generic controller for "a form that lives inside a
   modal". This is the one place that wires: live validation, submit ->
   validate -> callback -> close, and modal:close -> reset. Every concrete
   form (product, category, supplier, ...) just describes its fields and
   plugs in via ModalForm.init(config) instead of re-implementing this flow.

   Depends on:
     - form-validation.js  (window.FormValidation)
     - modal.js             (window.InventoryModal + the "modal:close" event)

   config shape:
     {
       formId: "addCategoryForm",
       modalId: "addCategoryModal",
       fieldLabels: { "category-name": "Category name" },
       requiredFieldIds: ["category-name"],
       nonNegativeFieldIds: [],            // optional, defaults to []
       resettableFieldIds: [...],          // optional, defaults to required + non-negative
       onSubmit: function (formEl) {...},  // called only once the form is valid
       onReset: function (formEl) {...},   // optional, for extra state (e.g. image preview)
       onInit: function (formEl) {...},    // optional, for one-time wiring (e.g. file input)
       extraValidate: function () {...}    // optional, e.g. a repeatable line-items block;
                                            // return false to block submit (and show its own errors)
     }
   ========================================================================== */

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

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      var isStandardValid = validateAll();
      var isExtraValid = typeof config.extraValidate === "function" ? config.extraValidate() : true;

      if (!isStandardValid || !isExtraValid) {
        FV.focusFirstInvalid(form);
        return;
      }

      if (typeof config.onSubmit === "function") config.onSubmit(form);
      if (window.InventoryModal) window.InventoryModal.close(config.modalId);
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
