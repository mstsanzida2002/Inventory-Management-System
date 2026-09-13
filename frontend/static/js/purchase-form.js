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
      if (reason === null) return;
      if (!reason.trim()) { alert("A reason is required to reject a purchase order."); return; }
      var formData = new FormData();
      formData.append("reason", reason.trim());
      RowActions.postAction(poActionUrl(poId, "reject"), formData).then(RowActions.reportResult);
    } else if (event.target.closest(".po-cancel-btn")) {
      var cancelReason = prompt("Reason for cancelling this purchase order? This cannot be undone.");
      if (cancelReason === null) return;
      if (!cancelReason.trim()) { alert("A reason is required to cancel a purchase order."); return; }
      var cancelFormData = new FormData();
      cancelFormData.append("reason", cancelReason.trim());
      RowActions.postAction(poActionUrl(poId, "cancel"), cancelFormData).then(RowActions.reportResult);
    } else if (event.target.closest(".po-receive-btn")) {
      openReceiveModal(poId, event.target.closest(".po-receive-btn"));
    }
  }

  var receiveTargetPoId = null;

  function openReceiveModal(poId, button) {
    var items;
    try {
      // Assumption: data-items is server-rendered from receive_items_json.
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
    // Rule: search/status are server-side GET params, not client-side.
    var tableBody = getField("purchasesTableBody");
    if (tableBody) tableBody.addEventListener("click", handleRowAction);
    initReceiveForm();

    if (!getField(FORM_ID)) return;

    lineItems = LineItems.create({
      containerId: "purchase-line-items",
      addButtonId: "purchase-add-item",
      errorId: "purchase-items-error",
      grandTotalId: "purchase-grand-total",
      productOptionsHtml: realProductOptionsHtml(),
      priceAttr: "data-purchase-price"
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
