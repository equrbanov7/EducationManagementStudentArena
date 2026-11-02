(() => {
  const form = document.querySelector('[data-history-restore]');
  if (!form) return;
  form.addEventListener('submit', event => {
    if (form.getAttribute('aria-busy') === 'true') {
      event.preventDefault();
      return;
    }
    form.setAttribute('aria-busy', 'true');
    const button = form.querySelector('[data-restore-submit]');
    if (button) button.disabled = true;
  });
  const errors = document.querySelector('[data-restore-errors]');
  if (errors) errors.focus();
  window.addEventListener('pageshow', () => {
    form.removeAttribute('aria-busy');
    const button = form.querySelector('[data-restore-submit]');
    if (button) button.disabled = false;
  });
})();
