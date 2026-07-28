/* ==========================================================================
   DOM-UTILS.JS — tiny shared DOM builders used when a form's successful
   submit inserts a new row/card into an existing table or grid (products,
   suppliers, categories, ...). Kept separate from modal-form.js since it's
   plain DOM construction, not form/modal wiring.
   ========================================================================== */

(function () {
  "use strict";

  /* A pill-shaped icon-only button, matching the .pill-btn markup already
     used for every "Edit"/"Delete" action across the product/supplier
     tables and the category cards. */
  function buildActionButton(label, iconId) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "pill-btn";
    button.setAttribute("aria-label", label);
    button.innerHTML = '<svg class="icon icon-sm"><use href="#' + iconId + '"></use></svg>';
    return button;
  }

  window.DomUtils = {
    buildActionButton: buildActionButton
  };
})();
