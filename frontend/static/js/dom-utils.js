// Rule: owns DOM-node builders for post-submit insertion, not form wiring.

(function () {
  "use strict";

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
