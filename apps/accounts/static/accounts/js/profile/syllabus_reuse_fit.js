/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus təkrar istifadəsi — «Dərs saatları fərqlidir» (sahib 2026-11-26)
   ───────────────────────────────────────────────────────────────────────────
   Mənbənin saatı bu jurnalın saatından fərqlidirsə (və ya köhnə sistemdən gələn
   mənbənin saatı bilinmirsə) «Kopyala və uyğunlaşdır» SƏSSİZ işləmir:
     * mənbə kartında «Mənbə: 45 saat (15 həftə) · Bu jurnal: 25 saat (13 sətir)»
       və «Dərs saatları fərqlidir» görünür;
     * birinci klik xəbərdarlıq qutusunu açır («N sətir kəsiləcək» / «N boş sətir
       əlavə olunacaq») və düymə «Bəli, uyğunlaşdırıb kopyala» olur — ikinci klik
       icra edir; mənbə dəyişəndə təsdiq sıfırlanır.
   Mətnlər serverdən (`siblings[].copy_fit`) gəlir; cədvəlin kəsilməsi/uzadılması
   SERVERDƏ eyni qaydadır (apps/syllabus/services/copy_fit.py) — burada yalnız göstəriş.

   `syllabus_reuse.js` bu modulu null-safe çağırır (`window.EMSSyllabusReuseFit`);
   qlobal dinləyici yoxdur, ona görə AJAX ilə təkrar yüklənmə təhlükəsizdir.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    if (window.EMSSyllabusReuseFit) {
        return; /* idempotent — skript təkrar yüklənsə də bir dəfə */
    }

    var ARMED = "data-syl-reuse-fit-armed";

    function el(tag, className, text) {
        var node = document.createElement(tag);
        node.className = className;
        node.textContent = text;
        return node;
    }

    function fitOf(source) {
        return (source && source.copy_fit) || null;
    }

    function setText(box, selector, text) {
        var node = box.querySelector(selector);
        if (node) {
            node.textContent = text || "";
            node.hidden = !text;
        }
    }

    function label(modal) {
        return modal.querySelector("[data-syl-reuse-do='copy'] [data-syl-reuse-copy-label]");
    }

    /* Mənbə kartı: saat müqayisəsi + xəbərdarlıq. */
    function card(body, row) {
        var fit = fitOf(row);
        if (!body || !fit || !fit.line) {
            return;
        }
        body.appendChild(el("span", "syl-reuse__fit-line", fit.line));
        if (fit.warning) {
            body.appendChild(el("span", "syl-reuse__fit-warn", "⚠ " + fit.warning));
        }
    }

    /* «Kopyala» izahı: xəbərdarlıq + nə olacaq + adi izah. */
    function hint(source, okText) {
        var fit = fitOf(source);
        if (!fit) {
            return okText;
        }
        return [fit.warning ? fit.warning + "." : "", fit.action, fit.confirm ? "" : okText]
            .filter(Boolean)
            .join(" ");
    }

    function reset(modal) {
        if (!modal) {
            return;
        }
        modal.removeAttribute(ARMED);
        var box = modal.querySelector("[data-syl-reuse-fit]");
        if (box) {
            box.hidden = true;
        }
        var text = label(modal);
        if (text && text.hasAttribute("data-default")) {
            text.textContent = text.getAttribute("data-default");
        }
    }

    /* Birinci klik → xəbərdarlıq + düymə mətni dəyişir (``true`` — hələ icra etmə); ikinci klik → ``false``. */
    function needsConfirm(modal, source) {
        var fit = fitOf(source);
        if (!modal || !fit || !fit.confirm) {
            return false;
        }
        if (modal.getAttribute(ARMED) === source.id) {
            return false;
        }
        modal.setAttribute(ARMED, source.id);
        var box = modal.querySelector("[data-syl-reuse-fit]");
        if (box) {
            setText(box, "[data-syl-reuse-fit-warning]", fit.warning);
            setText(box, "[data-syl-reuse-fit-line]", fit.line);
            setText(box, "[data-syl-reuse-fit-action]", fit.action);
            setText(box, "[data-syl-reuse-fit-hint]", fit.confirm_hint);
            box.hidden = false;
        }
        var text = label(modal);
        if (text && fit.confirm_label) {
            if (!text.hasAttribute("data-default")) {
                text.setAttribute("data-default", text.textContent.trim());
            }
            text.textContent = fit.confirm_label;
        }
        return true;
    }

    window.EMSSyllabusReuseFit = { card: card, hint: hint, reset: reset, needsConfirm: needsConfirm };
})();
