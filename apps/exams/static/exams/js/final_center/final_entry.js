/**
 * Final/midterm imtahan giriş səhifəsi — qaydalar/məlumat modalı.
 *
 * - Modalın kənarına (backdrop) klik və ya Esc "Geri" formasını göndərir (login-ə qayıdır).
 *   İstifadəçi adı serverdə saxlanır, ona görə bu dağıdıcı deyil (PIN yenidən yazılır).
 * - Redizayn 2026-10-21: modal açılanda fokus modalın başlığına keçir (arxa plan `inert`-dir —
 *   templates: final_entry.html), ekran oxuyucu dialoqun adını dərhal oxuyur.
 *
 * Səhifə AJAX ilə dəyişdirilmir; yenə də EMSReady + idempotent bağlama (data-fexc-bound).
 */
(function () {
    "use strict";

    function init() {
        var backdrop = document.querySelector("[data-fexc-gate-backdrop]");
        if (!backdrop || backdrop.dataset.fexcBound === "1") return;
        backdrop.dataset.fexcBound = "1";

        function goBack() {
            var backBtn = backdrop.querySelector('button[name="action"][value="back"]');
            if (backBtn) backBtn.click();
        }

        backdrop.addEventListener("click", function (evt) {
            if (evt.target !== backdrop) return; // yalnız kənara klik, panelə yox
            goBack();
        });

        document.addEventListener("keydown", function (evt) {
            if (evt.key !== "Escape" || !document.body.contains(backdrop)) return;
            evt.preventDefault();
            goBack();
        });

        var title = backdrop.querySelector("#fexc-modal-title");
        if (title && typeof title.focus === "function") {
            try {
                title.focus({ preventScroll: true });
            } catch (err) {
                title.focus();
            }
        }
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
