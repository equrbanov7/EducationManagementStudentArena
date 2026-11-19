// «Cari yükə bərpa et» — AJAX-safe (EMSReady): göndəriş kilidi, saat cəmi, gözləmə bildirişi.
(function () {
  function init() {
    const form = document.querySelector('[data-history-restore]');
    if (!form || form.dataset.restoreReady === '1') return;
    form.dataset.restoreReady = '1';
    const total = Number(form.dataset.total || 0);
    const sum = form.querySelector('[data-restore-sum]');
    const sumValue = form.querySelector('[data-restore-sum-value]');
    const busy = form.querySelector('[data-restore-busy]');
    const button = form.querySelector('[data-restore-submit]');
    const hours = Array.from(form.querySelectorAll('[data-restore-hours]'));

    function refreshSum() {
      if (!sum || !sumValue) return;
      const value = hours.reduce((acc, input) => acc + (Number(input.value) || 0), 0);
      sumValue.textContent = String(value);
      sum.classList.toggle('is-ok', value === total);
      sum.classList.toggle('is-bad', value !== total);
    }
    hours.forEach(input => input.addEventListener('input', refreshSum));
    refreshSum();

    form.addEventListener('submit', event => {
      if (form.getAttribute('aria-busy') === 'true') {
        event.preventDefault();
        return;
      }
      form.setAttribute('aria-busy', 'true');
      if (button) button.disabled = true;
      if (busy) busy.hidden = false;
    });
    const errors = document.querySelector('[data-restore-errors]');
    if (errors) errors.focus();
    window.addEventListener('pageshow', () => {
      form.removeAttribute('aria-busy');
      if (button) button.disabled = false;
      if (busy) busy.hidden = true;
    });
  }
  if (window.EMSReady) window.EMSReady(init);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
