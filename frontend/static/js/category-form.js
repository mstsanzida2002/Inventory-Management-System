/* ==========================================================================
   CATEGORY-FORM.JS — Add Category form (Phase 6) and, since Phase 8.99i,
   Edit/Deactivate/Reactivate/Delete too — mirrors product-form.js's own
   shape exactly (Add and Edit as two independent forms/modals sharing one
   parameterized onSubmit; row actions via the shared row-actions.js).
   Generic validation/reset/submit wiring lives in modal-form.js; generic
   error-state helpers live in form-validation.js.

   Categories renders as a card grid (#categoriesGrid), not a <table> —
   handleRowAction below reads [data-category-id] the same way
   product-form.js reads tr[data-product-id]; .closest() doesn't care
   which element type it's climbing through.

   Edit is pre-filled entirely client-side from the clicked card's own
   data-category JSON attribute (set server-side in
   CategoryListCreateView.get()), the same pattern Products' own Edit
   modal already uses — no new fetch-before-open mechanism.
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var ADD_FORM_ID = "addCategoryForm";
  var ADD_MODAL_ID = "addCategoryModal";
  var EDIT_FORM_ID = "editCategoryForm";
  var EDIT_MODAL_ID = "editCategoryModal";

  var ADD_FIELD_LABELS = { "category-name": "Category name" };
  var EDIT_FIELD_LABELS = { "edit-category-name": "Category name" };

  var ADD_REQUIRED_FIELD_IDS = ["category-name"];
  var EDIT_REQUIRED_FIELD_IDS = ["edit-category-name"];

  var ADD_SERVER_FIELD_MAP = { name: "category-name", description: "category-description" };
  var EDIT_SERVER_FIELD_MAP = { name: "edit-category-name", description: "edit-category-description" };

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
            window.location.reload();
            return true;
          }
          if (payload && payload.errors) {
            applyServerErrors(payload.errors, map, errorBoxId);
          } else {
            showFormError(errorBoxId, "Could not save this category. Please try again.");
          }
          return false;
        });
      }).catch(function () {
        showFormError(errorBoxId, "Could not reach the server. Please try again.");
        return false;
      });
    };
  }

  function prefillEditForm(category) {
    var setValue = function (id, value) {
      var field = getField(id);
      if (field) field.value = value || "";
    };
    setValue("edit-category-name", category.name);
    setValue("edit-category-description", category.description);
  }

  /* ---------------------------------------------------- row actions --- */

  function handleRowAction(event) {
    var card = event.target.closest("[data-category-id]");
    if (!card) return;
    var categoryId = card.getAttribute("data-category-id");
    var grid = getField("categoriesGrid");
    var base = grid.getAttribute("data-base-url");

    if (event.target.closest(".category-edit-btn")) {
      var category;
      try {
        category = JSON.parse(card.getAttribute("data-category") || "{}");
      } catch (e) {
        category = {};
      }
      var form = getField(EDIT_FORM_ID);
      if (form) form.setAttribute("action", base + categoryId + "/update/");
      prefillEditForm(category);
      if (window.InventoryModal) window.InventoryModal.open(EDIT_MODAL_ID);
    } else if (event.target.closest(".category-deactivate-btn")) {
      if (!confirm("Deactivate this category? It will no longer be selectable when adding or editing products; existing products keep it.")) return;
      RowActions.postAction(base + categoryId + "/deactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".category-reactivate-btn")) {
      RowActions.postAction(base + categoryId + "/reactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".category-delete-btn")) {
      if (!confirm("Permanently delete this category? This cannot be undone.")) return;
      RowActions.postAction(base + categoryId + "/delete/").then(RowActions.reportResult);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var grid = getField("categoriesGrid");
    if (grid) grid.addEventListener("click", handleRowAction);

    if (getField(ADD_FORM_ID)) {
      ModalForm.init({
        formId: ADD_FORM_ID,
        modalId: ADD_MODAL_ID,
        fieldLabels: ADD_FIELD_LABELS,
        requiredFieldIds: ADD_REQUIRED_FIELD_IDS,
        resettableFieldIds: ["category-name", "category-description", "category-status"],
        onReset: function () { clearFormError("addCategoryFormError"); },
        onSubmit: makeOnSubmit(ADD_SERVER_FIELD_MAP, "addCategoryFormError")
      });
    }

    if (getField(EDIT_FORM_ID)) {
      ModalForm.init({
        formId: EDIT_FORM_ID,
        modalId: EDIT_MODAL_ID,
        fieldLabels: EDIT_FIELD_LABELS,
        requiredFieldIds: EDIT_REQUIRED_FIELD_IDS,
        resettableFieldIds: ["edit-category-name", "edit-category-description"],
        onReset: function () { clearFormError("editCategoryFormError"); },
        onSubmit: makeOnSubmit(EDIT_SERVER_FIELD_MAP, "editCategoryFormError")
      });
    }
  });
})();
