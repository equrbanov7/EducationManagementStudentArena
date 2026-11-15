/* Redaktorun kilid banneri — «Yeni versiya yarat» (sahib 2026-11-15).
 *
 * Banner təsdiqlənmiş / rədd edilmiş / arxiv versiyada «yeni versiya yaradın» deyirdi, düyməsi yox idi.
 * Başqasının / ortaq dosyesində isə «Öz sillabusunu yarat» (siyahının `create` əməli) — eyni axın.
 * Düymə siyahının «Yeni versiya» əməlini (`syllabus_action` → `new_version`, «kiçik dəyişiklik») çağırır və
 * redaktoru yeni QARALAMADA açır — təsdiqlənmiş versiya toxunulmur. Düyməni server yalnız redaktə hüququ
 * olana render edir; son sözü yenə servis deyir.
 *
 * AJAX-safe: klik `EMSDelegate.on` ilə delegasiya olunur (bölmə swap-ından sonra da işləyir); URL-lər
 * redaktor kökünün `data-*` atributlarındadır (xarici JS şablondan keçmir). `syllabus_editor.js`-ə toxunmur.
 */
(function () {
    "use strict";

    if (!window.EMSDelegate || window.__emsSyllabusNewVersionBound) {
        return;
    }
    window.__emsSyllabusNewVersionBound = true;

    var SECTION = "syllabus-editor";

    function openVersion(root, versionId) {
        var url = new URL(root.getAttribute("data-profile-url") || window.location.pathname, window.location.origin);
        url.searchParams.set("section", SECTION);
        url.searchParams.set("version", versionId);
        if (typeof window.EMSProfileLoadSection === "function") {
            window.EMSProfileLoadSection(SECTION, url.pathname + url.search);
        } else {
            window.location.assign(url.pathname + url.search);
        }
    }

    function fail(button, error) {
        button.disabled = false;
        var message = (error && error.payload && error.payload.error) || button.getAttribute("data-t-error") || "";
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, "error");
        } else if (message) {
            window.alert(message);
        }
    }

    function run(button, payload) {
        var root = button.closest("[data-syllabus-editor]");
        var http = window.EMSCore && window.EMSCore.fetchJSON;
        if (!root || !http || button.disabled) {
            return;
        }
        button.disabled = true;
        http(root.getAttribute("data-action-url"), { method: "POST", data: payload })
            .then(function (data) {
                if (data && data.ok && data.version) {
                    openVersion(root, data.version);
                } else {
                    fail(button, null);
                }
            })
            .catch(function (error) {
                fail(button, error);
            });
    }

    window.EMSDelegate.on("click", "[data-syllabus-editor] [data-syl-new-version]", function (event, button) {
        event.preventDefault();
        run(button, { action: "new_version", syllabus: button.getAttribute("data-syllabus"), kind: "minor" });
    });

    /* Başqasının / ortaq dosye (sahib 2026-11-15): müəllimin sillabussuz jurnalı üçün öz qaralaması. */
    window.EMSDelegate.on("click", "[data-syllabus-editor] [data-syl-create-own]", function (event, button) {
        event.preventDefault();
        run(button, { action: "create", offering: button.getAttribute("data-offering") });
    });
})();
