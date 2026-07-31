/* ==========================================================================
   USER-FORM.JS — Add User form: field config + turning a valid submit into
   a new row in the users table. Shares its validation/reset/submit flow
   with product-form.js/category-form.js/supplier-form.js via modal-form.js.
   ========================================================================== */

(function () {
  "use strict";

  var FORM_ID = "addUserForm";
  var MODAL_ID = "addUserModal";
  var TABLE_BODY_ID = "usersTableBody";

  var FIELD_LABELS = {
    "user-full-name": "Full name",
    "user-username": "Username",
    "user-employee-id": "Employee ID",
    "user-email": "Email",
    "user-role": "Role"
  };

  var REQUIRED_FIELD_IDS = [
    "user-full-name", "user-username", "user-employee-id", "user-email", "user-role"
  ];

  var ROLE_LABELS = {
    admin: "System Administrator",
    supervisor: "Inventory Supervisor",
    staff: "Inventory Staff"
  };

  var ROLE_BADGE_CLASSES = {
    admin: "badge-indigo",
    supervisor: "badge-warning",
    staff: "badge-success"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function buildUserRow(data) {
    var row = document.createElement("tr");

    var nameCell = document.createElement("td");
    nameCell.textContent = data.full_name;
    var sub = document.createElement("div");
    sub.className = "cell-sub";
    sub.textContent = data.employee_id;
    nameCell.appendChild(sub);
    row.appendChild(nameCell);

    var usernameCell = document.createElement("td");
    usernameCell.className = "mono";
    usernameCell.textContent = data.username;
    row.appendChild(usernameCell);

    var emailCell = document.createElement("td");
    emailCell.textContent = data.email;
    row.appendChild(emailCell);

    var roleCell = document.createElement("td");
    var roleBadge = document.createElement("span");
    roleBadge.className = "badge " + (ROLE_BADGE_CLASSES[data.role] || "badge-indigo");
    roleBadge.textContent = ROLE_LABELS[data.role] || data.role;
    roleCell.appendChild(roleBadge);
    row.appendChild(roleCell);

    var statusCell = document.createElement("td");
    var statusBadge = document.createElement("span");
    statusBadge.className = "badge badge-success";
    statusBadge.textContent = "Active";
    statusCell.appendChild(statusBadge);
    row.appendChild(statusCell);

    var actionsCell = document.createElement("td");
    var actions = document.createElement("div");
    actions.className = "widget-actions";
    actions.appendChild(DomUtils.buildActionButton("Edit user", "icon-edit"));
    actions.appendChild(DomUtils.buildActionButton("Deactivate user", "icon-x"));
    actionsCell.appendChild(actions);
    row.appendChild(actionsCell);

    return row;
  }

  function addUserToTable(data) {
    var tableBody = getField(TABLE_BODY_ID);
    if (!tableBody) return;
    tableBody.insertBefore(buildUserRow(data), tableBody.firstChild);
  }

  function collectFormData() {
    return {
      full_name: getField("user-full-name").value.trim(),
      username: getField("user-username").value.trim(),
      employee_id: getField("user-employee-id").value.trim(),
      email: getField("user-email").value.trim(),
      role: getField("user-role").value
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!getField(FORM_ID)) return;

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      onSubmit: function () { addUserToTable(collectFormData()); }
    });
  });
})();
