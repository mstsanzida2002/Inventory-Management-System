/* ==========================================================================
   USER-FORM.JS — Add User form (fetch()-based onSubmit, Phase 5.5 contract)
   plus the real Deactivate/Reactivate row actions and the search/role/
   status client-side filter (table-filter.js), for users/users.html
   (Phase 8).
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

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

  var SERVER_FIELD_MAP = {
    full_name: "user-full-name",
    username: "user-username",
    employee_id: "user-employee-id",
    email: "user-email",
    role: "user-role"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError() {
    var box = getField("addUserFormError");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(message) {
    var box = getField("addUserFormError");
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
    return fetch(form.getAttribute("action") || window.location.pathname, {
      method: "POST",
      body: new FormData(form)
    }).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (payload) {
        if (response.ok) {
          // Phase 8.99f-3/8.99f-4: every successful create now carries
          // either `message` (credentials really were emailed) or
          // `warning` (created, but the email failed to send) — never
          // both. Before this, a real success and a real failed-send
          // looked identical (a silent reload, nothing shown), which is
          // exactly the "no confirmation appears" report. alert() is the
          // same mechanism this file already used for the warning case,
          // not a new toast component.
          var feedback = payload && (payload.message || payload.warning);
          if (feedback) {
            alert(feedback);
          }
          window.location.reload();
          return true;
        }
        if (payload && payload.errors) {
          applyServerErrors(payload.errors);
        } else {
          showFormError("Could not create this user. Please try again.");
        }
        return false;
      });
    }).catch(function () {
      showFormError("Could not reach the server. Please try again.");
      return false;
    });
  }

  /* --------------------------------------------------- row actions --- */

  function handleRowAction(event) {
    var row = event.target.closest("tr[data-user-id]");
    if (!row) return;
    var userId = row.getAttribute("data-user-id");
    var tableBody = getField(TABLE_BODY_ID);
    var base = tableBody.getAttribute("data-base-url");

    if (event.target.closest(".user-deactivate-btn")) {
      if (!confirm("Deactivate this user? They will no longer be able to log in.")) return;
      RowActions.postAction(base + userId + "/deactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".user-reactivate-btn")) {
      RowActions.postAction(base + userId + "/reactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".user-delete-btn")) {
      if (!confirm("Permanently delete this user? This cannot be undone.")) return;
      RowActions.postAction(base + userId + "/delete/").then(RowActions.reportResult);
    } else if (event.target.closest(".user-resend-btn")) {
      if (!confirm("Resend credentials to this user? A new temporary password will be generated and emailed, replacing the old one.")) return;
      RowActions.postAction(base + userId + "/resend-credentials/").then(function (result) {
        // Phase 8.99f-7: reuses postAction()/reportResult() unchanged
        // (no new fetch helper) — only supplies reportResult()'s existing
        // onSuccess hook so the message/warning from
        // _credentials_email_feedback() is actually shown, the same way
        // the Add User form's own onSubmit() already does.
        RowActions.reportResult(result, function () {
          var feedback = result.payload && (result.payload.message || result.payload.warning);
          if (feedback) alert(feedback);
          window.location.reload();
        });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var tableBody = getField(TABLE_BODY_ID);
    if (tableBody) tableBody.addEventListener("click", handleRowAction);

    if (window.TableFilter && getField(TABLE_BODY_ID)) {
      TableFilter.init({
        tableBodyId: TABLE_BODY_ID,
        searchInputId: "userSearch",
        selectFilters: [
          { id: "userRoleFilter", attr: "data-role" },
          { id: "userStatusFilter", attr: "data-status" }
        ],
        emptyStateId: "usersEmptyState"
      });
    }

    if (!getField(FORM_ID)) return;

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      onReset: clearFormError,
      onSubmit: onSubmit
    });
  });
})();
