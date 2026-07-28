/* ==========================================================================
   MAIN.JS — small, dependency-free interactivity.
   No framework needed for a Django-templates + Bootstrap-utility frontend.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
  initNavToggle();
  initTickerLoop();
  initPasswordToggles();
});

/* ---- Mobile nav ---- */
function initNavToggle() {
  const toggle = document.querySelector('[data-nav-toggle]');
  const links = document.querySelector('[data-nav-links]');
  if (!toggle || !links) return;

  toggle.addEventListener('click', () => {
    const isOpen = links.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(isOpen));
  });
}

/* ---- Ledger ticker: duplicate its content once so the CSS
   translateX(-50%) loop is seamless regardless of how many
   items the template renders. ---- */
function initTickerLoop() {
  const track = document.querySelector('[data-ticker-track]');
  if (!track) return;
  track.innerHTML += track.innerHTML;
}

/* ---- Show/hide password ---- */
function initPasswordToggles() {
  document.querySelectorAll('[data-toggle-password]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-toggle-password');
      const input = document.getElementById(targetId);
      if (!input) return;
      const isHidden = input.type === 'password';
      input.type = isHidden ? 'text' : 'password';
      btn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
      btn.classList.toggle('is-visible', isHidden);
    });
  });
}
