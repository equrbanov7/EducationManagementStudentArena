/* Profil redaktəsi — avatar seçicisi.
 *
 * Sahib (2026-09-10): «görünüş stabillik … dizaynını təkmilləşdir». Çılpaq
 * `<input type="file">` brauzerdən-brauzerə tam başqa cür görünür və seçilən
 * faylın adı sistem dilində qalırdı. İndi: cari şəkil önizləməsi + layihənin
 * öz düymə üslubu; fayl seçiləndə önizləmə DƏRHAL yenilənir, ad göstərilir.
 *
 * `URL.createObjectURL` ilə yaradılan keçid azad edilir — bölmə AJAX ilə
 * dəyişəndə sızma qalmasın.
 *
 * AJAX-safe: `EMSDelegate.on("change", …)` — swap-dan sonra da işləyir.
 */
(function (window, document) {
    "use strict";

    function picker(input) {
        return input && input.closest ? input.closest("[data-avatar-picker]") : null;
    }

    function release(host) {
        if (host.dataset.objectUrl) {
            window.URL.revokeObjectURL(host.dataset.objectUrl);
            delete host.dataset.objectUrl;
        }
    }

    function apply(input) {
        var host = picker(input);
        if (!host) {
            return;
        }
        var hint = host.querySelector("[data-avatar-name]");
        var preview = host.querySelector("[data-avatar-preview]");
        var placeholder = host.querySelector("[data-avatar-placeholder]");
        var file = input.files && input.files.length ? input.files[0] : null;

        release(host);

        if (!file) {
            if (hint) {
                hint.textContent = input.dataset.labelEmpty || "";
            }
            return;
        }
        if (hint) {
            hint.textContent = file.name;
        }
        if (preview && window.URL && window.URL.createObjectURL) {
            var url = window.URL.createObjectURL(file);
            host.dataset.objectUrl = url;
            preview.src = url;
            preview.hidden = false;
            if (placeholder) {
                placeholder.hidden = true;
            }
        }
    }

    window.EMSReady.once("accounts/profile/edit_profile_avatar", function () {
        window.EMSDelegate.on("change", "[data-avatar-input]", function (event, input) {
            apply(input);
        });
    });
})(window, document);
