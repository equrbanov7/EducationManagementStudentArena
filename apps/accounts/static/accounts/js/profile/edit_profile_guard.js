/* Profil redaktəsi — yadda saxlanmamış dəyişiklik qoruyucusu.
 *
 * Forma ilk vəziyyətlə müqayisə olunur (dirty-check). Dəyişiklik varkən:
 *  - sticky paneldə status nişanı görünür;
 *  - səhifədaxili keçidlər (sidebar, bölmə linkləri) capture fazasında tutulub
 *    #editProfileLeaveModal təsdiqi göstərilir (Yadda saxla / Saxlamadan çıx /
 *    Ləğv et);
 *  - tab bağlama/yeniləmə üçün native beforeunload xəbərdarlığı işləyir.
 * AJAX-safe: EMSReady + sənəd səviyyəli listener-lər EMSReady.once ilə bir dəfə.
 */
(function () {
    "use strict";

    var state = {
        snapshot: null,
        formNode: null,
        pendingHref: "",
        bypass: false,
    };

    function getForm() {
        return document.getElementById("editProfileForm");
    }

    function serializeForm(form) {
        var parts = [];
        Array.prototype.forEach.call(form.elements, function (element) {
            if (!element.name || element.name === "csrfmiddlewaretoken" || element.disabled) {
                return;
            }
            if (element.type === "file") {
                parts.push(element.name + "=" + (element.files && element.files.length ? "1" : ""));
                return;
            }
            if ((element.type === "checkbox" || element.type === "radio") && !element.checked) {
                return;
            }
            parts.push(element.name + "=" + element.value);
        });
        return parts.join("&");
    }

    function isDirty() {
        var form = getForm();
        return Boolean(form && state.snapshot !== null && serializeForm(form) !== state.snapshot);
    }

    function syncStatus() {
        var status = document.getElementById("editProfileDirtyStatus");
        if (status) {
            status.hidden = !isDirty();
        }
    }

    function takeSnapshot() {
        var form = getForm();
        state.snapshot = form ? serializeForm(form) : null;
        syncStatus();
    }

    function getLeaveModal() {
        var element = document.getElementById("editProfileLeaveModal");
        if (!element || !window.bootstrap || !window.bootstrap.Modal) {
            return null;
        }
        return { element: element, api: window.bootstrap.Modal.getOrCreateInstance(element) };
    }

    function shouldInterceptLink(anchor) {
        if (!anchor || !anchor.href || state.bypass) {
            return false;
        }
        if (anchor.target === "_blank" || anchor.hasAttribute("download")) {
            return false;
        }
        var href = anchor.getAttribute("href") || "";
        if (!href || href.charAt(0) === "#" || href.indexOf("javascript:") === 0) {
            return false;
        }
        // Modal daxili linklər / bağlama düymələri müdaxiləsiz qalır.
        if (anchor.closest(".modal")) {
            return false;
        }
        return isDirty();
    }

    window.EMSReady(function () {
        var form = getForm();
        if (!form) {
            return; // bölmə DOM-da deyil
        }
        // Snapshot yalnız YENİ forma node-u üçün: başqa bölmənin AJAX swap-ı
        // eyni formanı yenidən baseline-ə salıb dirty bayrağını silməsin.
        if (state.formNode !== form) {
            state.formNode = form;
            takeSnapshot();
        }
    });

    window.EMSReady.once("accounts/profile/edit_profile_guard", function () {
        // Dəyişiklik izləmə (delegated — swap-a davamlı).
        ["input", "change"].forEach(function (eventType) {
            document.addEventListener(eventType, function (event) {
                var form = getForm();
                if (form && event.target && form.contains(event.target)) {
                    syncStatus();
                }
            });
        });

        // Yadda saxla göndərişi qoruyucunu söndürür (yönləndirmə gözlənilir).
        document.addEventListener("submit", function (event) {
            var form = getForm();
            if (form && event.target === form) {
                state.bypass = true;
            }
        });

        // Keçidləri SPA loader-dən ƏVVƏL tutmaq üçün capture fazası.
        document.addEventListener(
            "click",
            function (event) {
                // Modifier-li kliklər (yeni tab/pəncərə) və artıq emal olunmuş
                // hadisələr müdaxiləsiz qalır — səhifə tərk edilmir.
                if (
                    event.defaultPrevented ||
                    event.metaKey ||
                    event.ctrlKey ||
                    event.shiftKey ||
                    event.altKey ||
                    event.button !== 0
                ) {
                    return;
                }
                var origin = event.target;
                if (!origin || typeof origin.closest !== "function") {
                    return;
                }
                var anchor = origin.closest("a[href]");
                if (!shouldInterceptLink(anchor)) {
                    return;
                }
                var modal = getLeaveModal();
                if (!modal) {
                    return; // modal yoxdursa müdaxilə etmə (native beforeunload qalır)
                }
                event.preventDefault();
                event.stopPropagation();
                state.pendingHref = anchor.href;
                modal.api.show();
            },
            true
        );

        window.EMSDelegate.on("click", "#editProfileLeaveWithoutSaving", function (event) {
            event.preventDefault();
            state.bypass = true;
            var target = state.pendingHref;
            state.pendingHref = "";
            if (target) {
                window.location.href = target;
            }
        });

        window.EMSDelegate.on("click", "#editProfileSaveAndLeave", function (event) {
            event.preventDefault();
            var form = getForm();
            var modal = getLeaveModal();
            if (modal) {
                modal.api.hide();
            }
            if (form) {
                // bypass burada QOYULMUR: constraint-validasiya uğursuz olsa
                // submit hadisəsi atəşlənmir və qoruyucu silahsızlanmamalıdır —
                // bypass yalnız real "submit" listener-ində qoyulur.
                form.requestSubmit ? form.requestSubmit() : form.submit();
            }
        });

        window.addEventListener("beforeunload", function (event) {
            if (state.bypass || !isDirty()) {
                return;
            }
            event.preventDefault();
            event.returnValue = "";
        });
    });
})();
