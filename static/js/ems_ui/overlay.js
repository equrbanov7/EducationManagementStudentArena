/* =========================================================================
   ems_ui/overlay.js — Drawer + dialoq davranışı (handoff §4 · §7 · §8/6)

   NƏ EDİR
   -------
   * açılışda fokusu içəri aparır  (ilk fokuslana bilən element / [autofocus])
   * FOKUS TƏLƏSİ: Tab və Shift+Tab overlay-dən çıxmır
   * Escape bağlayır
   * bağlananda fokus AÇAN elementə qayıdır
   * `aria-modal="true"` + `aria-labelledby` overlay markup-ından gəlir
   * arxa fon sürüşməsi kilidlənir (mövcud `modal_scroll_lock.css` class-ı)
   * səbəb dialoqu: textarea ≥ MIN_REASON simvol olmadan OK disabled qalır

   AJAX-SAFE
   ---------
   Bütün handler-lər `EMSDelegate` (document-səviyyəli, swap-a davamlı) və ya
   `EMSReady.once` ilə qeydiyyatdan keçir — heç bir şey stack-lənmir.

   AÇMAQ / BAĞLAMAQ
   ----------------
   Deklarativ:   <button data-ems-overlay-open="myDialogId">
                 <button data-ems-overlay-close>
   Proqramla:    EMSOverlay.open("myDialogId") / EMSOverlay.close(el)

   Overlay markup-ı `templates/partials/ems_ui/_dialog.html` /
   `_drawer.html`-dədir; bu fayl YALNIZ davranışdır.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSOverlay) {
        return; // İdempotent — script panel swap-da yenidən icra oluna bilər.
    }

    /* Handoff §8 qayda 6: səbəb ≥ 20 simvol, audit-ə yazılır. */
    var MIN_REASON = 20;

    var FOCUSABLE = [
        "a[href]",
        "button:not([disabled])",
        "input:not([disabled]):not([type=hidden])",
        "select:not([disabled])",
        "textarea:not([disabled])",
        '[tabindex]:not([tabindex="-1"])',
    ].join(",");

    /* Açılış anındakı fokus sahibi — bağlananda ora qayıdırıq. */
    var returnFocusTo = null;

    function visibleFocusable(root) {
        var out = [];
        var nodes = root.querySelectorAll(FOCUSABLE);
        for (var i = 0; i < nodes.length; i += 1) {
            var el = nodes[i];
            if (el.offsetWidth || el.offsetHeight || el.getClientRects().length) {
                out.push(el);
            }
        }
        return out;
    }

    function openOverlays() {
        return document.querySelectorAll(".ems-overlay:not([hidden])");
    }

    function topOverlay() {
        var open = openOverlays();
        return open.length ? open[open.length - 1] : null;
    }

    /* Səhifənin ƏSL scroller-i SPA kontekstində `<html>`-dir (bax
     * static/js/modal_scroll_lock.js) — Bootstrap-ın `body.modal-open`-u fonu
     * saxlamırdı: qrup dialoqu açıq ikən arxadakı cədvəl siçan təkəri ilə
     * sürüşürdü (sahib şikayəti 2026-09-07). `html.ems-modal-open` layihənin
     * öz kilididir (`modal_scroll_lock.css`); hər iki sinif qoyulur. */
    function lockScroll() {
        document.body.classList.add("modal-open");
        document.documentElement.classList.add("ems-modal-open");
    }

    function unlockScroll() {
        if (!openOverlays().length) {
            document.body.classList.remove("modal-open");
            // Bootstrap modalı hələ açıqdırsa onun kilidi qalsın.
            if (!document.querySelector(".modal.show")) {
                document.documentElement.classList.remove("ems-modal-open");
            }
        }
    }

    function open(target) {
        var el = typeof target === "string" ? document.getElementById(target) : target;
        if (!el || !el.classList.contains("ems-overlay")) {
            return null;
        }
        returnFocusTo = document.activeElement;
        el.hidden = false;
        lockScroll();

        var preferred = el.querySelector("[autofocus]");
        var focusables = visibleFocusable(el);
        var first = preferred || focusables[0] || el;
        if (first && typeof first.focus === "function") {
            first.focus();
        }
        syncReason(el);
        el.dispatchEvent(new CustomEvent("ems:overlay:open", { bubbles: true }));
        return el;
    }

    function close(target) {
        var el = typeof target === "string" ? document.getElementById(target) : target;
        if (!el) {
            return;
        }
        var overlay = el.classList && el.classList.contains("ems-overlay") ? el : el.closest(".ems-overlay");
        if (!overlay || overlay.hidden) {
            return;
        }
        overlay.hidden = true;
        unlockScroll();
        overlay.dispatchEvent(new CustomEvent("ems:overlay:close", { bubbles: true }));

        // Fokus AÇAN elementə qayıdır (handoff §7).
        if (returnFocusTo && document.contains(returnFocusTo)) {
            try {
                returnFocusTo.focus();
            } catch (err) {
                /* fokus verilə bilməyən element — səssiz keç */
            }
        }
        returnFocusTo = null;
    }

    /* ---- Səbəb dialoqu validasiyası ------------------------------------- */

    function syncReason(scope) {
        var boxes = (scope || document).querySelectorAll(".ems-reason");
        for (var i = 0; i < boxes.length; i += 1) {
            syncOneReason(boxes[i]);
        }
    }

    function syncOneReason(box) {
        var field = box.querySelector(".ems-textarea, .ems-input");
        if (!field) {
            return;
        }
        var min = parseInt(box.dataset.emsMinLength || "", 10);
        if (isNaN(min)) {
            min = MIN_REASON;
        }
        var length = field.value.trim().length;
        var ok = length >= min;

        box.classList.toggle("is-invalid", !ok && length > 0);
        field.setAttribute("aria-invalid", ok ? "false" : "true");

        // ⚠️ Sayğac dialoqun FOOTER-indədir, `.ems-reason` gövdəsinin İÇİNDƏ
        // DEYİL — ona görə axtarış overlay səviyyəsində aparılır. (Əvvəl
        // `box.querySelector` idi və sayğac heç vaxt yenilənmirdi; canlı
        // yoxlamada «0 / 20» donub qalırdı — Mərhələ 1-də tapılıb düzəldilib.)
        var counterScope = box.closest(".ems-overlay") || box;
        var counter = counterScope.querySelector(".ems-reason__counter");
        if (counter) {
            counter.textContent = length + " / " + min;
        }

        // İpucu mətni iki variantlıdır: normal hint ↔ xəta hint-i.
        var hint = box.querySelector(".ems-reason__hint");
        if (hint) {
            var normal = hint.dataset.hint || "";
            var invalid = hint.dataset.hintInvalid || "";
            if (normal || invalid) {
                hint.textContent = ok || !length ? normal : invalid || normal;
            }
        }

        // Təsdiq düyməsi gizlədilmir — disabled stilində qalır (handoff §4).
        var overlay = box.closest(".ems-overlay") || document;
        var submits = overlay.querySelectorAll("[data-ems-reason-submit]");
        for (var j = 0; j < submits.length; j += 1) {
            submits[j].disabled = !ok;
            submits[j].setAttribute("aria-disabled", ok ? "false" : "true");
        }
    }

    /* ---- Qeydiyyat ------------------------------------------------------- */

    window.EMSDelegate.on("click", "[data-ems-overlay-open]", function (event, btn) {
        event.preventDefault();
        open(btn.getAttribute("data-ems-overlay-open"));
    });

    window.EMSDelegate.on("click", "[data-ems-overlay-close]", function (event, btn) {
        event.preventDefault();
        close(btn);
    });

    /* Scrim-ə klik bağlayır; dialoqun İÇİNƏ klik bağlamır.
     *
     * ⚠️ Bağlamaq üçün mousedown VƏ mouseup — HƏR İKİSİ scrim-in ÖZÜNDƏ olmalıdır.
     * Tək `mousedown` yoxlaması iki halda dialoqu YANLIŞ bağlayırdı:
     *   • native `<select>` popup-ı dialoqun sərhədindən kənara daşanda variantın
     *     üzərinə edilən klik popup bağlandıqdan sonra scrim-ə düşürdü — sahib
     *     şikayəti 2026-09-07: «rəhbər seçimini açan kimi bağlanır»;
     *   • dialoq içində mətn seçib siçanı scrim üzərində buraxanda.
     * Bu naxış (down+up eyni hədəfdə) modal komponentlərində standartdır. */
    var scrimDown = null;

    window.EMSDelegate.on("mousedown", ".ems-overlay", function (event, overlay) {
        scrimDown = event.target === overlay ? overlay : null;
    });

    window.EMSDelegate.on("mouseup", ".ems-overlay", function (event, overlay) {
        var startedOnScrim = scrimDown === overlay;
        scrimDown = null;
        if (startedOnScrim && event.target === overlay && overlay.dataset.emsStatic !== "true") {
            close(overlay);
        }
    });

    window.EMSDelegate.on("input", ".ems-reason .ems-textarea, .ems-reason .ems-input", function (event, field) {
        var box = field.closest(".ems-reason");
        if (box) {
            syncOneReason(box);
        }
    });

    window.EMSReady.once("ems-ui-overlay-scrim", function () {
        // Siçan overlay-dən KƏNARDA buraxılırsa yaddaş təmizlənir — əks halda
        // növbəti mouseup köhnə `scrimDown` ilə yanlış bağlaya bilərdi.
        document.addEventListener("mouseup", function (event) {
            if (!event.target || !event.target.closest || !event.target.closest(".ems-overlay")) {
                scrimDown = null;
            }
        });
    });

    window.EMSReady.once("ems-ui-overlay-keys", function () {
        document.addEventListener("keydown", function (event) {
            var overlay = topOverlay();
            if (!overlay) {
                return;
            }
            if (event.key === "Escape") {
                // Açıq AXTARIŞLI SEÇİCİ (rəhbər/müəllim menyusu) varsa Escape
                // ONU bağlayır, dialoqu yox — əks halda istifadəçi menyunu
                // yığmaq istəyəndə bütün forma itirdi. Seçicinin öz qatı hadisəni
                // `preventDefault` edir; dinləyici sırasından asılı qalmamaq üçün
                // burada həm o bayraq, həm də DOM vəziyyəti yoxlanır.
                if (event.defaultPrevented || overlay.querySelector(".ems-ss.is-open")) {
                    return;
                }
                event.stopPropagation();
                close(overlay);
                return;
            }
            if (event.key !== "Tab") {
                return;
            }
            // Fokus tələsi.
            var items = visibleFocusable(overlay);
            if (!items.length) {
                event.preventDefault();
                return;
            }
            var first = items[0];
            var last = items[items.length - 1];
            if (event.shiftKey && (document.activeElement === first || !overlay.contains(document.activeElement))) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });
    });

    // Panel swap-dan sonra açıq qalmış overlay olmasın + səbəb sayğacları yenilənsin.
    window.EMSReady(function () {
        syncReason(document);
        unlockScroll();
    });

    window.EMSOverlay = {
        open: open,
        close: close,
        syncReason: syncReason,
        MIN_REASON: MIN_REASON,
    };
})(window, document);
