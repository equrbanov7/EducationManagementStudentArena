/**
 * Zibil qutusu — birdəfəlik silmə təsdiqi.
 *
 * Əvvəllər təsdiq `onsubmit="return confirm(...)"` inline atributu ilə idi.
 * Layihənin CSP-si `script-src` üçün `unsafe-inline`/`unsafe-hashes` vermir
 * (bax config/settings/components/csp.py) — yəni brauzer həmin atributu icra
 * ETMİR və silmə HEÇ BİR təsdiq olmadan gedirdi. Burada eyni rol bootstrap
 * modalı ilə, xarici fayldan icra olunur.
 */
window.EMSReady(function () {
    var modalElement = document.getElementById("deletedExamsPurgeModal");
    var form = document.getElementById("deletedExamsPurgeForm");
    if (!modalElement || !form || typeof bootstrap === "undefined") {
        return; // Səhifə swap olunmayıb və ya bootstrap yüklənməyib — null-safe.
    }

    var targetElement = document.getElementById("deletedExamsPurgeTarget");
    var modal = bootstrap.Modal.getOrCreateInstance(modalElement);

    window.EMSDelegate.on("click", ".js-purge-exam", function (event, trigger) {
        event.preventDefault();
        form.setAttribute("action", trigger.getAttribute("data-purge-action") || "");
        if (targetElement) {
            targetElement.textContent = trigger.getAttribute("data-purge-target") || "";
        }
        modal.show();
    });
});
