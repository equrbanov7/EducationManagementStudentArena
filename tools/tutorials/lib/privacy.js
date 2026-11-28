// Məxfilik qatı: klon real bazanın surətidir. Ssenarinin `privacy.selectors`-ına uyğun elementlərdən
// mətnində `privacy.allow` sözlərindən heç biri olmayanlar videoda bulanıqlaşdırılır (real ad/soyad görünməsin).
(function (cfg) {
  if (!cfg || !cfg.selectors || !cfg.selectors.length) return;
  const allow = (cfg.allow || []).map((s) => s.toLocaleLowerCase("az"));
  const sel = cfg.selectors.join(",");
  const apply = () => {
    document.querySelectorAll(sel).forEach((el) => {
      if (el.closest("#__tut_card")) { el.style.filter = ""; return; } // video kartı (overlay) real məlumat deyil
      const t = (el.innerText || el.textContent || "").toLocaleLowerCase("az").trim();
      const ok = !t || allow.some((a) => t.includes(a));
      el.style.filter = ok ? "" : "blur(6px)";
    });
  };
  const start = () => {
    apply();
    new MutationObserver(() => { clearTimeout(start.t); start.t = setTimeout(apply, 30); })
      .observe(document.documentElement, { childList: true, subtree: true, characterData: true });
    setInterval(apply, 400);
  };
  if (document.documentElement) start(); else document.addEventListener("DOMContentLoaded", start);
})(window.__tutPrivacy);
