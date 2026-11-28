// Səhifəyə `addInitScript` ilə qoşulan overlay: kursor, klik dalğası, vurğu halqası,
// fəsil nişanı, başlıq kartı və izah «balonu». Headless brauzerdə sistem kursoru
// yazılmır, ona görə hamısını özümüz çəkirik. Kart və fəsil sessionStorage-da saxlanır
// ki, səhifə dəyişəndə (və ya istifadəçi dəyişəndə) dərhal bərpa olunsun.
(() => {
  if (window.__tut) return;
  const BRAND = "#2563eb";
  const ACCENT = "#f97316";
  const Z = 2147483000;
  const css = `
  #__tut_cursor{position:fixed;left:0;top:0;width:26px;height:26px;pointer-events:none;z-index:${Z + 2};
    transform:translate(-100px,-100px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
  .__tut_ripple{position:fixed;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;
    border:3px solid ${ACCENT};pointer-events:none;z-index:${Z + 1};animation:__tutR .6s ease-out forwards}
  @keyframes __tutR{to{transform:scale(3.4);opacity:0}}
  .__tut_ring{position:fixed;border:3px solid ${ACCENT};border-radius:10px;pointer-events:none;z-index:${Z};
    box-shadow:0 0 0 4px rgba(249,115,22,.18),0 0 18px rgba(249,115,22,.35);transition:opacity .3s;animation:__tutP 1.2s ease-in-out infinite}
  @keyframes __tutP{50%{box-shadow:0 0 0 7px rgba(249,115,22,.10),0 0 24px rgba(249,115,22,.45)}}
  #__tut_chapter{position:fixed;right:18px;bottom:18px;z-index:${Z};background:rgba(15,23,42,.88);color:#fff;
    font:600 14px/1.2 -apple-system,"Segoe UI",Roboto,sans-serif;padding:9px 14px;border-radius:10px;
    border-left:4px solid ${ACCENT};pointer-events:none;max-width:420px}
  #__tut_card{position:fixed;inset:0;z-index:${Z + 5};display:flex;align-items:center;justify-content:center;
    background:radial-gradient(1200px 600px at 20% 10%,#1d4ed8 0%,#0f172a 60%);color:#fff;
    font-family:-apple-system,"Segoe UI",Roboto,sans-serif;opacity:0;transition:opacity .45s}
  #__tut_card.__on{opacity:1}
  #__tut_card .__in{max-width:980px;padding:0 60px}
  #__tut_card .__k{font:700 16px/1 inherit;letter-spacing:.14em;text-transform:uppercase;color:#fdba74;margin-bottom:22px}
  #__tut_card .__t{font:800 46px/1.12 inherit;margin:0 0 18px}
  #__tut_card .__s{font:400 21px/1.45 inherit;color:#cbd5e1}
  #__tut_card table{margin-top:26px;border-collapse:collapse;font:500 18px/1.3 inherit;width:100%}
  #__tut_card td{padding:9px 14px;border-bottom:1px solid rgba(255,255,255,.12)}
  #__tut_card td:first-child{color:#fff;font-weight:700;white-space:nowrap}
  #__tut_card td:last-child{color:#bfdbfe}
  #__tut_card ul{margin:24px 0 0;padding:0;list-style:none;font:400 20px/1.5 inherit;color:#e2e8f0}
  #__tut_card li{padding:6px 0 6px 30px;position:relative}
  #__tut_card li:before{content:"✓";position:absolute;left:0;color:#fdba74;font-weight:800}
  #__tut_card .__logo{display:flex;align-items:center;gap:10px;font:700 15px/1 inherit;color:#93c5fd;margin-bottom:34px}
  #__tut_card ol{margin:22px 0 0;padding:0;list-style:none;counter-reset:tutc;columns:2;column-gap:40px;font:500 18px/1.4 inherit;color:#e2e8f0}
  #__tut_card ol li{counter-increment:tutc;padding:6px 0 6px 38px;break-inside:avoid}
  #__tut_card ol li:before{content:counter(tutc);left:0;top:7px;width:26px;height:26px;border-radius:50%;background:rgba(253,186,116,.18);color:#fdba74;font:800 14px/26px inherit;text-align:center}
  #__tut_card .__toch{margin-top:26px;font:700 14px/1 inherit;letter-spacing:.14em;text-transform:uppercase;color:#93c5fd}
  #__tut_card .__credit{position:fixed;left:0;right:0;bottom:28px;text-align:center;font:500 15px/1 inherit;color:#94a3b8;letter-spacing:.02em}
  #__tut_card .__credit b{color:#e2e8f0;font-weight:700}
  #__tut_card .__logo i{width:12px;height:12px;border-radius:3px;background:${ACCENT};display:inline-block}
  .__tut_callout{position:fixed;z-index:${Z + 3};background:#0f172a;color:#fff;border-radius:12px;padding:12px 16px;
    font:600 15px/1.4 -apple-system,"Segoe UI",Roboto,sans-serif;max-width:330px;pointer-events:none;
    box-shadow:0 10px 30px rgba(0,0,0,.35);border:2px solid ${ACCENT};opacity:0;transition:opacity .3s,transform .3s;transform:translateY(6px)}
  .__tut_callout.__on{opacity:1;transform:none}
  .__tut_callout b{color:#fdba74;display:block;font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px}
  `;
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  let cursor, chapterEl, cardEl, calloutEl;

  function mount() {
    if (document.getElementById("__tut_cursor")) return;
    const st = document.createElement("style");
    st.textContent = css;
    document.documentElement.appendChild(st);
    cursor = document.createElement("div");
    cursor.id = "__tut_cursor";
    cursor.innerHTML =
      '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l15 11.5-6.6.9 3.9 7.4-2.9 1.5-3.9-7.5L4 20.3z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(cursor);
    const ch = sessionStorage.getItem("__tutChapter");
    if (ch) api.chapter(ch);
    const card = sessionStorage.getItem("__tutCard");
    if (card) api.card(JSON.parse(card), true);
  }

  document.addEventListener("mousemove", (e) => {
    if (cursor) cursor.style.transform = `translate(${e.clientX - 3}px,${e.clientY - 2}px)`;
  }, true);
  document.addEventListener("mousedown", (e) => {
    const r = document.createElement("div");
    r.className = "__tut_ripple";
    r.style.left = e.clientX + "px";
    r.style.top = e.clientY + "px";
    document.documentElement.appendChild(r);
    setTimeout(() => r.remove(), 700);
  }, true);

  const api = {
    ring(x, y, w, h, ms) {
      const r = document.createElement("div");
      r.className = "__tut_ring";
      const pad = 6;
      Object.assign(r.style, { left: x - pad + "px", top: y - pad + "px", width: w + pad * 2 + "px", height: h + pad * 2 + "px" });
      document.documentElement.appendChild(r);
      setTimeout(() => { r.style.opacity = "0"; setTimeout(() => r.remove(), 350); }, ms || 1600);
    },
    chapter(text) {
      if (!text) {
        sessionStorage.removeItem("__tutChapter");
        if (chapterEl) chapterEl.remove();
        chapterEl = null;
        return;
      }
      sessionStorage.setItem("__tutChapter", text);
      if (!chapterEl) {
        chapterEl = document.createElement("div");
        chapterEl.id = "__tut_chapter";
        document.documentElement.appendChild(chapterEl);
      }
      chapterEl.textContent = text;
    },
    card(d, instant) {
      sessionStorage.setItem("__tutCard", JSON.stringify(d));
      if (!cardEl) {
        cardEl = document.createElement("div");
        cardEl.id = "__tut_card";
        document.documentElement.appendChild(cardEl);
      }
      const rows = (d.rows || []).map((r) => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`).join("");
      const bullets = (d.bullets || []).map((b) => `<li>${esc(b)}</li>`).join("");
      const toc = (d.toc || []).map((b) => `<li>${esc(b)}</li>`).join("");
      cardEl.innerHTML =
        `<div class="__in"><div class="__logo"><i></i>${esc(d.brand || "")}</div>` +
        (d.kicker ? `<div class="__k">${esc(d.kicker)}</div>` : "") +
        `<h1 class="__t">${esc(d.title || "")}</h1>` +
        (d.sub ? `<div class="__s">${esc(d.sub)}</div>` : "") +
        (rows ? `<table>${rows}</table>` : "") +
        (bullets ? `<ul>${bullets}</ul>` : "") +
        (toc ? `<div class="__toch">${esc(d.tocTitle || "Mündəricat")}</div><ol>${toc}</ol>` : "") +
        "</div>" +
        `<div class="__credit">Hazırladı: <b>RİM</b> · Elvin Qurbanov</div>`;
      if (instant) cardEl.style.transition = "none";
      requestAnimationFrame(() => { cardEl.classList.add("__on"); if (instant) setTimeout(() => (cardEl.style.transition = ""), 50); });
    },
    cardHide() {
      sessionStorage.removeItem("__tutCard");
      if (!cardEl) return;
      const el = cardEl;
      cardEl = null;
      el.classList.remove("__on");
      setTimeout(() => el.remove(), 500);
    },
    callout(box, title, text, side) {
      api.calloutHide();
      if (!text) return;
      const el = document.createElement("div");
      el.className = "__tut_callout";
      el.innerHTML = (title ? `<b>${esc(title)}</b>` : "") + esc(text);
      document.documentElement.appendChild(el);
      const w = el.offsetWidth, h = el.offsetHeight, gap = 18;
      let x = side === "left" ? box.x - w - gap : box.x + box.w + gap;
      let y = box.y + box.h / 2 - h / 2;
      x = Math.max(10, Math.min(window.innerWidth - w - 10, x));
      y = Math.max(10, Math.min(window.innerHeight - h - 10, y));
      el.style.left = x + "px";
      el.style.top = y + "px";
      calloutEl = el;
      requestAnimationFrame(() => el.classList.add("__on"));
    },
    calloutHide() {
      if (!calloutEl) return;
      const el = calloutEl;
      calloutEl = null;
      el.classList.remove("__on");
      setTimeout(() => el.remove(), 350);
    },
  };
  window.__tut = api;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
