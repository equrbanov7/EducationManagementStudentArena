/**
 * Final imtahan giriş səhifəsi — qaydalar/məlumat modalı üçün kənar-klik.
 * Modalın kənarına (backdrop) klik "Geri" formasını göndərir (login-ə qayıdır).
 * İstifadəçi adı serverdə saxlanır, ona görə kənar-klik dağıdıcı deyil.
 */
(function () {
    "use strict";
    var backdrop = document.querySelector(".fexc-modal-backdrop");
    if (!backdrop) return;
    backdrop.addEventListener("click", function (evt) {
        if (evt.target !== backdrop) return; // yalnız kənara klik, panelə yox
        var backBtn = backdrop.querySelector('button[name="action"][value="back"]');
        if (backBtn) backBtn.click();
    });
})();
