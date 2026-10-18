/* «İmtahan şansı ver» — filtr formunun avto-submit-i.
 *
 * Select dəyişən kimi forma göndərilir (fakültə dəyişəndə kafedra sıfırlanır —
 * server onsuz da yad kafedranı rədd edir, URL təmiz qalsın); axtarış
 * inputları (imtahan + tələbə) vahid EMSSearchInput qaydası ilə (2026-10-14:
 * yazı dayananda 1500 ms, ≥ 2 simvol, Enter dərhal, IME) — göndəriş «quiet»
 * bölmə yükləməsidir: input əvəzlənmir, fokus və yazılan hərflər qalır.
 *
 * QEYD: profil SPA-sı bölmə swap-ında paneldəki <script> taqlarını yenidən
 * icra edir — dinləyicilər document səviyyəsində DELEGATED qoşulur və qlobal
 * bayraqla ikiqat qoşulma önlənir (CSP: inline handler yoxdur).
 */
(function () {
    "use strict";

    if (window.__exchInit) {
        return;
    }
    window.__exchInit = true;

    function submitForm(form, input) {
        window.EMSSearchInput.submitForm(form, { input: input || null });
    }

    document.addEventListener("change", function (event) {
        var select = event.target;
        if (!select || select.tagName !== "SELECT") {
            return;
        }
        var form = select.closest("form.js-exch-filter");
        if (!form) {
            return;
        }
        if (select.classList.contains("js-exch-faculty")) {
            var kafedra = form.querySelector('select[name="chance_kafedra"]');
            if (kafedra) {
                kafedra.value = "";
            }
        }
        submitForm(form);
    });

    /* 2026-10-18 (sahib): rəsmi şans — «25% müraciəti» səbəbində imtahan siyahısı seçilmiş tələbələrin
     * 25% fənlərinə görə süzülür; altda «kimə, nə, niyə» xülasəsi. Server qaydanı yenidən yoxlayır. */
    function syncGrant(form) {
        var reason = form.getAttribute("data-exch-reason");
        var checked = Array.prototype.slice.call(form.querySelectorAll('input[name="student_ids"]:checked'));
        var select = form.querySelector("[data-exch-exam]");
        if (select && reason === "retake_25") {
            var allowed = {};
            checked.forEach(function (box) {
                (box.getAttribute("data-exch-subjects") || "").split(",").forEach(function (id) {
                    if (id) { allowed[id] = true; }
                });
            });
            var any = Object.keys(allowed).length > 0;
            Array.prototype.forEach.call(select.options, function (option) {
                if (!option.value) { return; }
                var ok = !any || allowed[option.getAttribute("data-subject")] === true;
                option.hidden = !ok;
                option.disabled = !ok;
                if (!ok && option.selected) { select.value = ""; }
            });
            if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
                window.EMSBootstrapSelect.refresh(select);
            }
        }
        var summary = form.querySelector("[data-exch-summary]");
        if (summary) {
            var names = checked.map(function (box) {
                var label = box.closest("label");
                var name = label ? label.querySelector(".exch-stu__name") : null;
                return name ? name.textContent.trim() : "";
            }).filter(Boolean);
            var exam = select && select.selectedIndex > 0 ? select.options[select.selectedIndex].textContent.trim() : "";
            summary.textContent = names.length && exam ? names.join(", ") + " → " + exam : "";
        }
    }

    document.addEventListener("change", function (event) {
        var form = event.target && event.target.closest ? event.target.closest("form[data-exch-grant]") : null;
        if (form) {
            syncGrant(form);
        }
    });

    window.EMSSearchInput.delegate("form.js-exch-filter input[data-exch-debounce]", {
        onSearch: function (value, meta) {
            submitForm(meta.input.closest("form.js-exch-filter"), meta.input);
        },
    });
})();
