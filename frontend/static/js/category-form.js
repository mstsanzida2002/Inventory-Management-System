/* ==========================================================================
   CATEGORY-FORM.JS — Add Category form: field config + turning a valid
   submit into a new category card. Shares its validation/reset/submit
   flow with product-form.js and supplier-form.js via modal-form.js.
   ========================================================================== */

(function () {
  "use strict";

  var FORM_ID = "addCategoryForm";
  var MODAL_ID = "addCategoryModal";
  var GRID_ID = "categoriesGrid";

  var FIELD_LABELS = {
    "category-name": "Category name"
  };

  var REQUIRED_FIELD_IDS = ["category-name"];

  function getField(id) {
    return document.getElementById(id);
  }

  function buildCategoryCard(data) {
    var card = document.createElement("div");
    card.className = "card-flat";

    var topRow = document.createElement("div");
    topRow.className = "flex items-center justify-between gap-3";
    topRow.style.marginBottom = "var(--sp-4)";

    var icon = document.createElement("span");
    icon.className = "kpi-icon tint-indigo";
    icon.innerHTML = '<svg class="icon"><use href="#icon-tag"></use></svg>';
    topRow.appendChild(icon);

    var actions = document.createElement("div");
    actions.className = "flex gap-2";
    actions.appendChild(DomUtils.buildActionButton("Edit category", "icon-edit"));
    actions.appendChild(DomUtils.buildActionButton("Delete category", "icon-trash"));
    topRow.appendChild(actions);

    card.appendChild(topRow);

    var title = document.createElement("h4");
    title.style.marginBottom = "0.3rem";
    title.textContent = data.name;
    card.appendChild(title);

    var description = document.createElement("p");
    description.className = "text-slate text-sm";
    description.style.marginBottom = "var(--sp-3)";
    description.textContent = data.description || "No description provided.";
    card.appendChild(description);

    var badge = document.createElement("span");
    badge.className = "badge badge-indigo";
    badge.textContent = "0 products";
    card.appendChild(badge);

    return card;
  }

  function addCategoryToGrid(data) {
    var grid = getField(GRID_ID);
    if (!grid) return;
    grid.insertBefore(buildCategoryCard(data), grid.firstChild);
  }

  function collectFormData() {
    return {
      name: getField("category-name").value.trim(),
      parent: getField("category-parent").value,
      code: getField("category-code").value.trim(),
      description: getField("category-description").value.trim(),
      status: getField("category-status").value
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!getField(FORM_ID)) return;

    ModalForm.init({
      formId: FORM_ID,
      modalId: MODAL_ID,
      fieldLabels: FIELD_LABELS,
      requiredFieldIds: REQUIRED_FIELD_IDS,
      onSubmit: function () { addCategoryToGrid(collectFormData()); }
    });
  });
})();
