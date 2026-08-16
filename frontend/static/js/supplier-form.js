/* ==========================================================================
   SUPPLIER-FORM.JS — Add Supplier form (Phase 6) and, since Phase 8.99i,
   Edit/Deactivate/Reactivate/Delete too — mirrors product-form.js's/
   category-form.js's own shape exactly (Add and Edit as two independent
   forms/modals sharing one parameterized onSubmit; row actions via the
   shared row-actions.js).

   Edit is pre-filled client-side from the clicked row's own data-supplier
   JSON attribute (SupplierListCreateView.get()) — the same pattern
   Products'/Categories' own Edit modals already use.
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var ADD_FORM_ID = "addSupplierForm";
  var ADD_MODAL_ID = "addSupplierModal";
  var EDIT_FORM_ID = "editSupplierForm";
  var EDIT_MODAL_ID = "editSupplierModal";

  var ADD_FIELD_LABELS = {
    "supplier-name": "Supplier name",
    "supplier-company-name": "Company name",
    "supplier-contact-person": "Contact person",
    "supplier-email": "Email",
    "supplier-phone": "Phone",
    "supplier-address": "Address"
  };
  var EDIT_FIELD_LABELS = {
    "edit-supplier-name": "Supplier name",
    "edit-supplier-company-name": "Company name",
    "edit-supplier-contact-person": "Contact person",
    "edit-supplier-email": "Email",
    "edit-supplier-phone": "Phone",
    "edit-supplier-address": "Address"
  };

  var ADD_REQUIRED_FIELD_IDS = [
    "supplier-name", "supplier-company-name", "supplier-contact-person",
    "supplier-email", "supplier-phone", "supplier-address"
  ];
  var EDIT_REQUIRED_FIELD_IDS = [
    "edit-supplier-name", "edit-supplier-company-name", "edit-supplier-contact-person",
    "edit-supplier-email", "edit-supplier-phone", "edit-supplier-address"
  ];

  var ADD_SERVER_FIELD_MAP = {
    supplier_name: "supplier-name", company_name: "supplier-company-name",
    contact_person: "supplier-contact-person", email: "supplier-email",
    phone: "supplier-phone", address: "supplier-address"
  };
  var EDIT_SERVER_FIELD_MAP = {
    supplier_name: "edit-supplier-name", company_name: "edit-supplier-company-name",
    contact_person: "edit-supplier-contact-person", email: "edit-supplier-email",
    phone: "edit-supplier-phone", address: "edit-supplier-address"
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
            showFormError(errorBoxId, "Could not save this supplier. Please try again.");
          }
          return false;
        });
      }).catch(function () {
        showFormError(errorBoxId, "Could not reach the server. Please try again.");
        return false;
      });
    };
  }

  function prefillEditForm(supplier) {
    var setValue = function (id, value) {
      var field = getField(id);
      if (field) field.value = value || "";
    };
    setValue("edit-supplier-name", supplier.supplier_name);
    setValue("edit-supplier-company-name", supplier.company_name);
    setValue("edit-supplier-contact-person", supplier.contact_person);
    setValue("edit-supplier-email", supplier.email);
    setValue("edit-supplier-phone", supplier.phone);
    setValue("edit-supplier-address", supplier.address);
  }

  /* ---------------------------------------------------- row actions --- */

  function handleRowAction(event) {
    var row = event.target.closest("tr[data-supplier-id]");
    if (!row) return;
    var supplierId = row.getAttribute("data-supplier-id");
    var tableBody = getField("suppliersTableBody");
    var base = tableBody.getAttribute("data-base-url");

    if (event.target.closest(".supplier-edit-btn")) {
      var supplier;
      try {
        supplier = JSON.parse(row.getAttribute("data-supplier") || "{}");
      } catch (e) {
        supplier = {};
      }
      var form = getField(EDIT_FORM_ID);
      if (form) form.setAttribute("action", base + supplierId + "/update/");
      prefillEditForm(supplier);
      if (window.InventoryModal) window.InventoryModal.open(EDIT_MODAL_ID);
    } else if (event.target.closest(".supplier-deactivate-btn")) {
      if (!confirm("Deactivate this supplier? It will no longer be selectable when adding products or purchase orders; existing records keep it.")) return;
      RowActions.postAction(base + supplierId + "/deactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".supplier-reactivate-btn")) {
      RowActions.postAction(base + supplierId + "/reactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".supplier-delete-btn")) {
      if (!confirm("Permanently delete this supplier? This cannot be undone.")) return;
      RowActions.postAction(base + supplierId + "/delete/").then(RowActions.reportResult);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (window.TableFilter && getField("suppliersTableBody")) {
      TableFilter.init({
        tableBodyId: "suppliersTableBody",
        searchInputId: "supplierSearch",
        selectFilters: [{ id: "supplierStatusFilter", attr: "data-status" }]
      });
    }

    var tableBody = getField("suppliersTableBody");
    if (tableBody) tableBody.addEventListener("click", handleRowAction);

    if (getField(ADD_FORM_ID)) {
      ModalForm.init({
        formId: ADD_FORM_ID,
        modalId: ADD_MODAL_ID,
        fieldLabels: ADD_FIELD_LABELS,
        requiredFieldIds: ADD_REQUIRED_FIELD_IDS,
        resettableFieldIds: Object.keys(ADD_FIELD_LABELS).concat(["supplier-status"]),
        onReset: function () { clearFormError("addSupplierFormError"); },
        onSubmit: makeOnSubmit(ADD_SERVER_FIELD_MAP, "addSupplierFormError")
      });
    }

    if (getField(EDIT_FORM_ID)) {
      ModalForm.init({
        formId: EDIT_FORM_ID,
        modalId: EDIT_MODAL_ID,
        fieldLabels: EDIT_FIELD_LABELS,
        requiredFieldIds: EDIT_REQUIRED_FIELD_IDS,
        resettableFieldIds: Object.keys(EDIT_FIELD_LABELS),
        onReset: function () { clearFormError("editSupplierFormError"); },
        onSubmit: makeOnSubmit(EDIT_SERVER_FIELD_MAP, "editSupplierFormError")
      });
    }
  });
})();
