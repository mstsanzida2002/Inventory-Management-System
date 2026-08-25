/* ==========================================================================
   PURCHASE-FORM.JS — New Purchase Order form (header + line items) and the
   real per-row lifecycle actions (submit/approve/reject/receive/cancel)
   for purchases/purchases.html (Phase 7).

   line-items.js itself is untouched — only the HTML fed into its
   productOptionsHtml config changed (real Product <option value="{{ pk }}">
   from the page's #realProductOptions <template>, not mock-catalog.js's
   name-keyed options). Create-form submission follows the same fetch()-
   based onSubmit contract as product-form.js/category-form.js/
   supplier-form.js (Phase 5.5/6); the client-side line-items shape check
   still runs in extraValidate exactly as before — BUG-33's fix (Phase 5.6)
   means that's now safe by construction, not just in this one case.

   Approve/submit use a plain confirm(); reject and cancel (Phase 8.99c —
   cancel now requires a reason too) both use a plain prompt() for the
   reason, rather than building bespoke confirmation modals the existing
   mock never had — Receive is the one action that genuinely needs a real
   modal (per-line quantities), so that's the only new modal built here.
   ========================================================================== */

(function () {
  "use strict";

  var FV = window.FormValidation;

  var FORM_ID = "addPurchaseForm";
  var MODAL_ID = "addPurchaseModal";

  var FIELD_LABELS = { "purchase-supplier": "Supplier" };
  var REQUIRED_FIELD_IDS = ["purchase-supplier"];

  var lineItems = null;

  var SERVER_FIELD_MAP = {
    supplier: "purchase-supplier",
    expected_delivery: "purchase-expected-delivery",
    notes: "purchase-notes"
  };

  function getField(id) {
    return document.getElementById(id);
  }

  function clearFormError() {
    var box = getField("addPurchaseFormError");
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  function showFormError(message) {
    var box = getField("addPurchaseFormError");
    if (box) { box.hidden = false; box.textContent = message; }
  }

  function applyServerErrors(errors) {
    Object.keys(errors).forEach(function (fieldName) {
      var entries = errors[fieldName];
      var text = (entries && entries.length && entries[0].message) || "This field is invalid.";
      if (fieldName === "items") {
        showFormError(entries.map(function (e) { return e.message; }).join(" "));
        return;
      }
      var fieldId = SERVER_FIELD_MAP[fieldName];
      var field = fieldId ? getField(fieldId) : null;
      if (field) {
        FV.setFieldError(field, text);
      } else {
        showFormError(text);
      }
    });
  }

  function realProductOptionsHtml() {
    var template = getField("realProductOptions");
    return template ? template.innerHTML : "";
  }

  function onSubmit(form) {
    clearFormError();
    var formData = new FormData(form);
    formData.append("items_json", JSON.stringify(lineItems.getItems()));

    return fetch(form.getAttribute("action"), {
      method: "POST",
      body: formData
    }).then(function (response) {
      return response.json().catch(function () {
        return null;
      }).then(function (payload) {
        if (response.ok) {
          window.location.reload();
          return true;
        }
        if (payload && payload.errors) {
          applyServerErrors(payload.errors);
        } else {
          showFormError("Could not save this purchase order. Please try again.");
        }
        return false;
      });
    }).catch(function () {
      showFormError("Could not reach the server. Please try again.");
      return false;
    });
  }

  /* ---------------------------------------------------- row actions --- */

  function poActionUrl(poId, action) {
    var tableBody = getField("purchasesTableBody");
    var base = tableBody ? tableBody.getAttribute("data-base-url") : "/purchases/";
    return base + poId + "/" + action + "/";
  }

  function handleRowAction(event) {
    var row = event.target.closest("tr[data-po-id]");
    if (!row) return;
    var poId = row.getAttribute("data-po-id");

    if (event.target.closest(".po-submit-btn")) {
      if (!confirm("Submit this purchase order for approval?")) return;
      RowActions.postAction(poActionUrl(poId, "submit")).then(RowActions.reportResult);
    } else if (event.target.closest(".po-approve-btn")) {
      if (!confirm("Approve this purchase order?")) return;
      RowActions.postAction(poActionUrl(poId, "approve")).then(RowActions.reportResult);
    } else if (event.target.closest(".po-reject-btn")) {
      var reason = prompt("Reason for rejecting this purchase order:");
      if (reason === null) return; // cancelled
      if (!reason.trim()) { alert("A reason is required to reject a purchase order."); return; }
      var formData = new FormData();
      formData.append("reason", reason.trim());
      RowActions.postAction(poActionUrl(poId, "reject"), formData).then(RowActions.reportResult);
    } else if (event.target.closest(".po-cancel-btn")) {
      var cancelReason = prompt("Reason for cancelling this purchase order? This cannot be undone.");
      if (cancelReason === null) return; // cancelled
      if (!cancelReason.trim()) { alert("A reason is required to cancel a purchase order."); return; }
      var cancelFormData = new FormData();
      cancelFormData.append("reason", cancelReason.trim());
      RowActions.postAction(poActionUrl(poId, "cancel"), cancelFormData).then(RowActions.reportResult);
    } else if (event.target.closest(".po-receive-btn")) {
      openReceiveModal(poId, event.target.closest(".po-receive-btn"));
    }
  }

  /* --------------------------------------------------- receive modal --- */

  var receiveTargetPoId = null;

  function openReceiveModal(poId, button) {
    var items;
    try {
      items = JSON.parse(button.getAttribute("data-items") || "[]");
    } catch (e) {
      items = [];
    }

    receiveTargetPoId = poId;
    var body = getField("receiveItemsBody");
    body.innerHTML = "";

    items.forEach(function (item) {
      if (item.remaining <= 0) return;
      var row = document.createElement("tr");

      var nameCell = document.createElement("td");
      nameCell.textContent = item.product_name;
      row.appendChild(nameCell);

      var orderedCell = document.createElement("td");
      orderedCell.className = "mono";
      orderedCell.textContent = item.ordered_qty;
      row.appendChild(orderedCell);

      var receivedCell = document.createElement("td");
      receivedCell.className = "mono";
      receivedCell.textContent = item.received_qty;
      row.appendChild(receivedCell);

      var remainingCell = document.createElement("td");
      remainingCell.className = "mono";
      remainingCell.textContent = item.remaining;
      row.appendChild(remainingCell);

      var inputCell = document.createElement("td");
      var input = document.createElement("input");
      input.type = "number";
      input.className = "input input-plain receive-qty-input";
      input.min = "0";
      input.max = String(item.remaining);
      input.step = "1";
      input.placeholder = "0";
      input.setAttribute("data-item-id", item.item_id);
      inputCell.appendChild(input);
      row.appendChild(inputCell);

      body.appendChild(row);
    });

    var errorBox = getField("receivePurchaseFormError");
    if (errorBox) { errorBox.hidden = true; errorBox.textContent = ""; }

    var overlay = getField("receivePurchaseModal");
    if (overlay) {
      overlay.classList.add("is-open");
      overlay.setAttribute("aria-hidden", "false");
      document.body.classList.add("modal-open");
    }
  }

  function initReceiveForm() {
    var form = getField("receivePurchaseForm");
    if (!form) return;

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var errorBox = getField("receivePurchaseFormError");
      var entries = Array.prototype.slice.call(document.querySelectorAll(".receive-qty-input"))
        .map(function (input) {
          return { item_id: Number(input.getAttribute("data-item-id")), received_qty: Number(input.value) || 0 };
        })
        .filter(function (entry) { return entry.received_qty > 0; });

      if (!entries.length) {
        if (errorBox) { errorBox.hidden = false; errorBox.textContent = "Enter a quantity for at least one item."; }
        return;
      }

      var formData = new FormData();
      formData.append("receive_json", JSON.stringify(entries));
      RowActions.postAction(poActionUrl(receiveTargetPoId, "receive"), formData).then(function (result) {
        if (result.ok) {
          window.location.reload();
          return;
        }
        if (errorBox) {
          errorBox.hidden = false;
          errorBox.textContent = result.blocked
            ? "You don't have permission to receive items."
            : (result.payload && result.payload.error) || "Could not receive items.";
        }
      });
    });

    document.querySelectorAll('#receivePurchaseModal [data-modal-close]').forEach(function (btn) {
      btn.addEventListener("click", function () {
        var overlay = getField("receivePurchaseModal");
        if (overlay) {
          overlay.classList.remove("is-open");
          overlay.setAttribute("aria-hidden", "true");
          document.body.classList.remove("modal-open");
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    // Pagination pass (2026-08-25) — search/status are real server-side
    // GET params now (frontend.filters.filter_purchases()), submitted via
    // the page's own <form method="get">; client-side TableFilter would
    // only ever see the current page's 10 rows.
    var tableBody = getField("purchasesTableBody");
    if (tableBody) tableBody.addEventListener("click", handleRowAction);
    initReceiveForm();

    if (!getField(FORM_ID)) return;

    lineItems = LineItems.create({
      containerId: "purchase-line-items",
      addButtonId: "purchase-add-item",
      errorId: "purchase-items-error",
      grandTotalId: "purchase-grand-total",
      productOptionsHtml: realProductOptionsHtml()
    });

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      resettableFieldIds: ["purchase-supplier", "purchase-expected-delivery", "purchase-notes"],
      extraValidate: function () { return lineItems.validate({ minQuantity: 1 }); },
      onReset: function () { lineItems.reset(); clearFormError(); },
      onSubmit: onSubmit
    });
  });
})();
