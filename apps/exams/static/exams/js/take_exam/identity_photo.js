/**
 * İmtahan səhifəsi — tələbə şəkli yüklənməsə baş hərflərə qayıt (2026-10-13 gecə, examphoto).
 *
 * Niyə: avatar faylı storage-dən silinibsə (və ya sessiya bitib 302/404 qayıdırsa) brauzer
 * «sınıq şəkil» ikonunu baş hərflərin ÜSTÜNDƏ göstərirdi — nəzarətçi üçün daha pis idi.
 * Inline `onerror` CSP səbəbindən YOXDUR: sənəd səviyyəsində tutulan `error` hadisəsi (capture,
 * çünki `error` bubble etmir) + skript gec yüklənəndə artıq sınmış şəkillər üçün bir dəfəlik yoxlama.
 * İdempotentdir (iki dəfə yüklənsə də bir dinləyici qalır).
 */
(function () {
    "use strict";

    if (window.EMSExamIdentityPhoto) return;

    var HOLDER_CLASSES = ["proctor-id__ava--photo", "has-photo"];

    function fallback(img) {
        var holder = img.closest("[data-id-photo-holder]");
        if (holder) {
            HOLDER_CLASSES.forEach(function (cls) { holder.classList.remove(cls); });
            var card = holder.closest("[data-exam-id-card]");
            var note = card && card.querySelector("[data-id-nophoto]");
            if (note) note.hidden = false;
        }
        img.remove();
    }

    document.addEventListener("error", function (evt) {
        var img = evt.target;
        if (img && img.tagName === "IMG" && img.hasAttribute("data-id-photo")) fallback(img);
    }, true);

    function sweep() {
        document.querySelectorAll("img[data-id-photo]").forEach(function (img) {
            if (img.complete && img.naturalWidth === 0) fallback(img);
        });
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(sweep);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", sweep, { once: true });
    } else {
        sweep();
    }

    window.EMSExamIdentityPhoto = { sweep: sweep };
})();
