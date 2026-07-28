/* ==========================================================================
   SUPPLIER-FORM.JS — Add Supplier form: field config + turning a valid
   submit into a new suppliers-table row. Shares its validation/reset/submit
   flow with product-form.js and category-form.js via modal-form.js.
   ========================================================================== */

(function () {
  "use strict";

  var FORM_ID = "addSupplierForm";
  var MODAL_ID = "addSupplierModal";
  var TABLE_BODY_ID = "suppliersTableBody";

  var FIELD_LABELS = {
    "supplier-name": "Supplier name"
  };

  var REQUIRED_FIELD_IDS = ["supplier-name"];

  function getField(id) {
    return document.getElementById(id);
  }

  function buildSupplierRow(data) {
    var row = document.createElement("tr");

    var nameCell = document.createElement("td");
    nameCell.textContent = data.name;
    row.appendChild(nameCell);

    var contactCell = document.createElement("td");
    contactCell.textContent = data.contactPerson || "—";
    row.appendChild(contactCell);

    var emailCell = document.createElement("td");
    emailCell.className = "mono";
    emailCell.textContent = data.email || "—";
    row.appendChild(emailCell);

    var phoneCell = document.createElement("td");
    phoneCell.className = "mono";
    phoneCell.textContent = data.phone || "—";
    row.appendChild(phoneCell);

    var productsCell = document.createElement("td");
    productsCell.className = "mono";
    productsCell.textContent = "0";
    row.appendChild(productsCell);

    var statusCell = document.createElement("td");
    var badge = document.createElement("span");
    var isActive = data.status === "Active";
    badge.className = "badge " + (isActive ? "badge-success" : "badge-danger");
    badge.textContent = data.status;
    statusCell.appendChild(badge);
    row.appendChild(statusCell);

    var actionsCell = document.createElement("td");
    var actionsWrap = document.createElement("div");
    actionsWrap.className = "widget-actions";
    actionsWrap.appendChild(DomUtils.buildActionButton("Edit supplier", "icon-edit"));
    actionsWrap.appendChild(DomUtils.buildActionButton("Delete supplier", "icon-trash"));
    actionsCell.appendChild(actionsWrap);
    row.appendChild(actionsCell);

    return row;
  }

  function addSupplierToTable(data) {
    var tableBody = getField(TABLE_BODY_ID);
    if (!tableBody) return;
    tableBody.insertBefore(buildSupplierRow(data), tableBody.firstChild);
  }

  function collectFormData() {
    return {
      name: getField("supplier-name").value.trim(),
      code: getField("supplier-code").value.trim(),
      contactPerson: getField("supplier-contact-person").value.trim(),
      email: getField("supplier-email").value.trim(),
      phone: getField("supplier-phone").value.trim(),
      status: getField("supplier-status").value,
      address: getField("supplier-address").value.trim(),
      city: getField("supplier-city").value.trim(),
      country: getField("supplier-country").value.trim(),
      postalCode: getField("supplier-postal-code").value.trim(),
      website: getField("supplier-website").value.trim(),
      taxId: getField("supplier-tax-id").value.trim(),
      notes: getField("supplier-notes").value.trim()
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!getField(FORM_ID)) return;

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      onSubmit: function () { addSupplierToTable(collectFormData()); }
    });
  });
})();
