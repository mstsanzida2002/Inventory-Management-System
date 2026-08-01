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
       onSubmit: function (formEl) {...},  // called only once the form is valid — see contract below
       onReset: function (formEl) {...},   // optional, for extra state (e.g. image preview)
       onInit: function (formEl) {...},    // optional, for one-time wiring (e.g. file input)
       extraValidate: function () {...}    // optional, e.g. a repeatable line-items block;
                                            // return false to block submit (and show its own errors)
     }

   extraValidate's ordering guarantee (Phase 5.6, fixes BUG-33):
     extraValidate() only runs once every requiredFieldIds/nonNegativeFieldIds
     field already passes — it is short-circuited, not just evaluated and
     then discarded, if standard validation already failed. Do not put
     expensive or server-side work in extraValidate expecting it to be
     skipped on an obviously-invalid submit unless this guarantee holds;
     it now does, for every module. (Previously extraValidate() ran
     unconditionally on every submit click, even ones standard validation
     was already going to block — harmless for Purchase/Sale's pre-Phase-6
     synchronous line-items check, but would have re-fired a real request
     on every keystroke-free submit attempt the moment any extraValidate
     did real work. See docs/bugsfound.md BUG-33.)

   onSubmit's return-value contract (Phase 5.5):
     - Sync (the common case — anything that isn't a Promise, including
       returning nothing): behavior is unchanged from before this contract
       existed — the modal closes and the form resets immediately, every
       time, regardless of what (if anything) onSubmit returns. Every
       module's onSubmit that doesn't need the network yet keeps working
       with zero changes.
     - Async (onSubmit returns a Promise — i.e. it used fetch() or is an
       `async function`): the modal stays open, NOT reset, until that
       Promise settles. On resolve, the modal closes/resets UNLESS the
       resolved value is `false` or an object with `success: false` — in
       either of those two failure shapes, the modal stays open and
       nothing is reset, so field values and any errors onSubmit already
       set via FormValidation.setFieldError() remain visible. A rejected
       Promise is treated the same as a `false` resolve (modal stays
       open) — onSubmit is expected to catch its own errors and report
       them (e.g. via a form-level error banner) before the rejection
       reaches here; this is just a safety net, not the primary path.
       See product-form.js for the reference implementation.
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

    function closeModal() {
      if (window.InventoryModal) window.InventoryModal.close(config.modalId);
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      // extraValidate() only runs once the required/non-negative fields
      // already pass (short-circuit — see the ordering guarantee in this
      // file's header). Required-field failures never used to reach it in
      // practice, since a blank line-items table already stopped submit,
      // but the old code called it unconditionally regardless — costly the
      // moment extraValidate does real (e.g. server-side) work.
      var isStandardValid = validateAll();
      var isExtraValid = isStandardValid && (
        typeof config.extraValidate === "function" ? config.extraValidate() : true
      );

      if (!isStandardValid || !isExtraValid) {
        FV.focusFirstInvalid(form);
        return;
      }

      var result = typeof config.onSubmit === "function" ? config.onSubmit(form) : undefined;

      // Async onSubmit (returns a Promise) — see the return-value contract
      // in this file's header. Keep the modal open/unreset until it
      // settles; only close on a genuine success.
      if (result && typeof result.then === "function") {
        result.then(function (outcome) {
          var failed = outcome === false || (outcome && typeof outcome === "object" && outcome.success === false);
          if (!failed) closeModal();
        }, function () {
          /* Rejected — treated as failure. onSubmit is expected to have
             already reported the error itself; just leave the modal open. */
        });
        return;
      }

      // Sync onSubmit (or none) — unchanged from before this contract
      // existed: always close/reset immediately.
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
