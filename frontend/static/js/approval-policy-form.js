/* ==========================================================================
   APPROVAL-POLICY-FORM.JS — Add/Edit ApprovalPolicy (Phase 12), same shape
   as category-form.js: two independent forms/modals sharing one
   parameterized onSubmit, row actions (edit/deactivate/reactivate) via the
   shared row-actions.js, edit pre-filled client-side from the clicked
   row's own data-policy JSON attribute (ApprovalPolicyListCreateView.get()).

   Phase 12.2 — the rule simulator (a plain fetch() against a dedicated
   simulate endpoint) and every abc_class field reference are removed;
   this file is back to the plain add/edit/row-action shape every other
   module's *-form.js already uses.
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var ADD_FORM_ID = "addPolicyForm";
  var ADD_MODAL_ID = "addPolicyModal";
  var EDIT_FORM_ID = "editPolicyForm";
  var EDIT_MODAL_ID = "editPolicyModal";

  var REQUIRED_SUFFIXES = ["name", "transaction-type", "priority", "min-value", "required-level"];

  function fieldIds(prefix) {
    return REQUIRED_SUFFIXES.map(function (suffix) { return prefix + "-" + suffix; });
  }

  function fieldLabels(prefix) {
    var labels = {};
    labels[prefix + "-name"] = "Policy name";
    labels[prefix + "-transaction-type"] = "Transaction type";
    labels[prefix + "-priority"] = "Priority";
    labels[prefix + "-min-value"] = "Min value";
    labels[prefix + "-required-level"] = "Outcome";
    return labels;
  }

  var SERVER_FIELD_SUFFIX_MAP = {
    name: "name", transaction_type: "transaction-type", reason_code: "reason-code",
    min_value: "min-value", max_value: "max-value",
    max_variance_pct: "max-variance",
    cumulative_window_days: "cumulative-window", cumulative_value_cap: "cumulative-cap",
    required_level: "required-level",
    block_self_approval: "block-self-approval", priority: "priority", notes: "notes"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError(prefix) {
    var box = getField(prefix + "-form-error");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(prefix, message) {
    var box = getField(prefix + "-form-error");
    if (box) { box.hidden = false; box.textContent = message; }
  }

  function applyServerErrors(prefix, errors) {
    Object.keys(errors).forEach(function (fieldName) {
      var suffix = SERVER_FIELD_SUFFIX_MAP[fieldName];
      var field = suffix ? getField(prefix + "-" + suffix) : null;
      var entries = errors[fieldName];
      var text = (entries && entries.length && entries[0].message) || "This field is invalid.";
      if (field) {
        FV.setFieldError(field, text);
      } else {
        showFormError(prefix, text);
      }
    });
  }

  function makeOnSubmit(prefix) {
    return function onSubmit(form) {
      clearFormError(prefix);
      return fetch(form.getAttribute("action"), {
        method: "POST",
        body: new FormData(form)
      }).then(function (response) {
        return response.json().catch(function () { return null; }).then(function (payload) {
          if (response.ok) {
            window.location.reload();
            return true;
          }
          if (payload && payload.errors) {
            applyServerErrors(prefix, payload.errors);
          } else {
            showFormError(prefix, (payload && payload.error) || "Could not save this policy. Please try again.");
          }
          return false;
        });
      }).catch(function () {
        showFormError(prefix, "Could not reach the server. Please try again.");
        return false;
      });
    };
  }

  function prefillEditForm(policy) {
    var setValue = function (id, value) {
      var field = getField(id);
      if (field) field.value = (value === null || value === undefined) ? "" : value;
    };
    setValue("edit-policy-name", policy.name);
    setValue("edit-policy-transaction-type", policy.transaction_type);
    setValue("edit-policy-reason-code", policy.reason_code);
    setValue("edit-policy-min-value", policy.min_value);
    setValue("edit-policy-max-value", policy.max_value);
    setValue("edit-policy-max-variance", policy.max_variance_pct);
    setValue("edit-policy-cumulative-window", policy.cumulative_window_days);
    setValue("edit-policy-cumulative-cap", policy.cumulative_value_cap);
    setValue("edit-policy-required-level", policy.required_level);
    setValue("edit-policy-priority", policy.priority);
    setValue("edit-policy-notes", policy.notes);
    var selfApproval = getField("edit-policy-block-self-approval");
    if (selfApproval) selfApproval.checked = !!policy.block_self_approval;
  }

  /* ---------------------------------------------------- row actions --- */

  function handleRowAction(event) {
    var row = event.target.closest("[data-policy-id]");
    if (!row) return;
    var policyId = row.getAttribute("data-policy-id");
    var base = "/settings/approval-policies/";

    if (event.target.closest(".policy-edit-btn")) {
      var policy;
      try {
        policy = JSON.parse(row.getAttribute("data-policy") || "{}");
      } catch (e) {
        policy = {};
      }
      var form = getField(EDIT_FORM_ID);
      if (form) form.setAttribute("action", base + policyId + "/update/");
      prefillEditForm(policy);
      if (window.InventoryModal) window.InventoryModal.open(EDIT_MODAL_ID);
    } else if (event.target.closest(".policy-deactivate-btn")) {
      if (!confirm("Deactivate this policy? Transactions it used to match will fall through to the next rule (or escalate to Admin if none matches).")) return;
      RowActions.postAction(base + policyId + "/deactivate/").then(RowActions.reportResult);
    } else if (event.target.closest(".policy-reactivate-btn")) {
      RowActions.postAction(base + policyId + "/reactivate/").then(RowActions.reportResult);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-tx-group] tbody").forEach(function (tbody) {
      tbody.addEventListener("click", handleRowAction);
    });

    if (getField(ADD_FORM_ID)) {
      ModalForm.init({
        formId: ADD_FORM_ID,
        modalId: ADD_MODAL_ID,
        fieldLabels: fieldLabels("policy"),
        requiredFieldIds: fieldIds("policy"),
        nonNegativeFieldIds: ["policy-min-value", "policy-max-value", "policy-max-variance", "policy-priority"],
        onReset: function () { clearFormError("policy"); },
        onSubmit: makeOnSubmit("policy")
      });
    }

    if (getField(EDIT_FORM_ID)) {
      ModalForm.init({
        formId: EDIT_FORM_ID,
        modalId: EDIT_MODAL_ID,
        fieldLabels: fieldLabels("edit-policy"),
        requiredFieldIds: fieldIds("edit-policy"),
        nonNegativeFieldIds: ["edit-policy-min-value", "edit-policy-max-value", "edit-policy-max-variance", "edit-policy-priority"],
        onReset: function () { clearFormError("edit-policy"); },
        onSubmit: makeOnSubmit("edit-policy")
      });
    }
  });
})();
