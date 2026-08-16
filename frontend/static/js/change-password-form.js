/* ==========================================================================
   CHANGE-PASSWORD-FORM.JS — Change Password modal on the Profile page
   (Phase 8.98a). Same fetch()-based onSubmit contract as every other real
   modal in this app (Phase 5.5) — posts to frontend:change_password,
   which returns JSON, not a page redirect (unlike profile_view's own
   plain-form POST for name/contact/photo).
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var FORM_ID = "changePasswordForm";
  var MODAL_ID = "changePasswordModal";

  var FIELD_LABELS = {
    "cp-current-password": "Current password",
    "cp-new-password": "New password",
    "cp-confirm-password": "Confirm new password",
  };

  var REQUIRED_FIELD_IDS = ["cp-current-password", "cp-new-password", "cp-confirm-password"];

  // Django field name -> HTML field id, for server-side validation errors.
  var SERVER_FIELD_MAP = {
    current_password: "cp-current-password",
    new_password: "cp-new-password",
    confirm_password: "cp-confirm-password",
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError() {
    var box = getField("changePasswordFormError");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(message) {
    var box = getField("changePasswordFormError");
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

    return fetch(form.getAttribute("action"), {
      method: "POST",
      body: new FormData(form)
    }).then(function (response) {
      return response.json().catch(function () {
        return null;
      }).then(function (payload) {
        if (response.ok) {
          // Real, server-flashed success message (Django messages,
          // rendered by dashboard_base.html) — needs a real reload to
          // actually show up, same as every other real modal in this app.
          window.location.reload();
          return true;
        }
        if (payload && payload.errors) {
          applyServerErrors(payload.errors);
        } else {
          showFormError("Could not change your password. Please try again.");
        }
        return false;
      });
    }).catch(function () {
      showFormError("Could not reach the server. Please try again.");
      return false;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!getField(FORM_ID)) return;

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      resettableFieldIds: Object.keys(FIELD_LABELS),
      onReset: clearFormError,
      onSubmit: onSubmit
    });
  });
})();
