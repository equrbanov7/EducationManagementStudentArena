/* =========================================================================
   Dərs yükü zənciri — YALNIZ Excel idxalının MULTIPART yüklənməsi (ekran 12).

   NİYƏ AYRI FAYL?
   ---------------
   Ortaq `teaching_office.js` formanı `application/x-www-form-urlencoded` kimi
   göndərir — fayl ondan KEÇMİR. Burada yalnız `[data-wl-upload]` forması
   `FormData` ilə göndərilir; uğurda panel yenilənir (server addım 2-ni
   render edir). Dialoq doldurma, səbəb sayğacı, fokus tələsi və digər JSON
   POST-lar ORTAQ qatda qalır və TƏKRARLANMIR.

   AJAX-SAFE: yalnız `EMSDelegate` (sənəd səviyyəli); `[data-wl-upload]`
   yoxdursa heç nə etmir.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSWorkloadChain) {
        return;
    }

    function csrfToken(form) {
        var field = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
        if (field && field.value) {
            return field.value;
        }
        field = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return (field && field.value) || "";
    }

    function showError(form, message) {
        var box = form.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
    }

    function reload(section) {
        if (!window.EMSTeachingOffice) {
            window.location.reload();
            return;
        }
        window.EMSTeachingOffice.reload(section, window.EMSTeachingOffice.sectionUrl(section, {}));
    }

    window.EMSDelegate.on("submit", "form[data-wl-upload]", function (event, form) {
        event.preventDefault();
        var section = form.getAttribute("data-wl-section") || "workload-center";
        var submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
        }
        showError(form, "");

        // ⚠️ `FormData` ilə `Content-Type` BAŞLIĞI ƏLLƏ QOYULMUR — brauzer
        // multipart sərhədini özü yazır (əl ilə qoyulsa server faylı görmür).
        window.EMSCore.fetchJSON(form.getAttribute("action"), {
            method: "POST",
            body: new FormData(form),
            headers: { "X-CSRFToken": csrfToken(form) },
        })
            .then(function () {
                reload(section);
            })
            .catch(function (err) {
                var payload = err && err.payload;
                showError(form, (payload && payload.message) || "");
                if (submit) {
                    submit.disabled = false;
                }
            });
    });

    window.EMSWorkloadChain = { version: 1 };
})(window, document);
