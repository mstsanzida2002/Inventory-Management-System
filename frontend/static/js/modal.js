// Rule: owns generic modal mechanics only; no form or field knowledge.

(function () {
  "use strict";

  var OPEN_CLASS = "is-open";
  var openModals = [];

  function getFocusableElements(container) {
    var selector = 'a[href], button:not([disabled]), input:not([disabled]), ' +
      'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    return Array.prototype.slice.call(container.querySelectorAll(selector));
  }

  function lockScroll() {
    document.body.classList.add("modal-open");
  }

  function unlockScroll() {
    document.body.classList.remove("modal-open");
  }

  function openModal(overlay, trigger) {
    if (!overlay || overlay.classList.contains(OPEN_CLASS)) return;

    overlay.classList.add(OPEN_CLASS);
    overlay.setAttribute("aria-hidden", "false");
    overlay._returnFocusTo = trigger || null;
    openModals.push(overlay);
    lockScroll();

    var dialog = overlay.querySelector(".modal");
    var focusable = dialog ? getFocusableElements(dialog) : [];
    if (focusable.length) focusable[0].focus();

    document.dispatchEvent(new CustomEvent("modal:open", { detail: { id: overlay.id } }));
  }

  function closeModal(overlay) {
    if (!overlay || !overlay.classList.contains(OPEN_CLASS)) return;

    overlay.classList.remove(OPEN_CLASS);
    overlay.setAttribute("aria-hidden", "true");
    openModals = openModals.filter(function (m) { return m !== overlay; });
    if (!openModals.length) unlockScroll();

    if (overlay._returnFocusTo) overlay._returnFocusTo.focus();
    overlay._returnFocusTo = null;

    document.dispatchEvent(new CustomEvent("modal:close", { detail: { id: overlay.id } }));
  }

  function closeTopModal() {
    if (!openModals.length) return;
    closeModal(openModals[openModals.length - 1]);
  }

  function initTriggers() {
    document.querySelectorAll("[data-modal-open]").forEach(function (trigger) {
      trigger.addEventListener("click", function () {
        var overlay = document.getElementById(trigger.getAttribute("data-modal-open"));
        openModal(overlay, trigger);
      });
    });

    document.querySelectorAll("[data-modal]").forEach(function (overlay) {
      overlay.addEventListener("click", function (event) {
        if (event.target === overlay) closeModal(overlay);
      });
      overlay.querySelectorAll("[data-modal-close]").forEach(function (closeBtn) {
        closeBtn.addEventListener("click", function () { closeModal(overlay); });
      });
    });
  }

  function initEscapeKey() {
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeTopModal();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTriggers();
    initEscapeKey();
  });

  // Rule: open() lets a caller populate fields before the modal shows.
  window.InventoryModal = {
    close: function (id) { closeModal(document.getElementById(id)); },
    open: function (id, trigger) { openModal(document.getElementById(id), trigger); }
  };
})();
