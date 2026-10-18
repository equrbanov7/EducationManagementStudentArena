/* «Tələbə reyestri» → «Arayış ver» (sahib 2026-10-19): «Təhsil aldığı yer haqqında arayış» dialoqu.
 *
 * Düymə sətir əməllərində (`data-sr-arayis="<record_id>"`) və tələbə kartında (`data-sr-arayis-card`,
 * record_id `sr:card` hadisəsi ilə gəlir). Dialoq «Təqdim ediləcəyi yer»i alır və
 * `registrar:student_enrollment_certificate_pdf`-ə POST edir; cavab PDF-dirsə `blob` kimi endirilir, deyilsə
 * serverin mətni (409 — tələbə aktiv deyil, 403 — view-as) dialoqda göstərilir.
 *
 * AJAX-safe: dinləyicilər BİR DƏFƏ qoşulur (sənəd səviyyəsində delegasiya), DOM hər dəfə yenidən axtarılır.
 */
(function (window, document) {
    "use strict";

    if (window.EMSRegistryDocuments) {
        return;
    }
    window.EMSRegistryDocuments = true;

    var ZERO_ID = "00000000-0000-0000-0000-000000000000";
    var current = { recordId: "", name: "" };

    function dialog() {
        return document.querySelector("[data-sr-arayis-dialog]");
    }

    function showError(box, text) {
        var node = box && box.querySelector("[data-sr-arayis-error]");
        if (!node) {
            return;
        }
        node.textContent = text || "";
        node.hidden = !text;
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function open(recordId, name) {
        var box = dialog();
        if (!box || !recordId) {
            return;
        }
        current = { recordId: recordId, name: name || "" };
        var target = box.querySelector("[data-sr-arayis-target]");
        if (target) {
            target.textContent = current.name;
        }
        var place = box.querySelector("input[name=place]");
        if (place) {
            place.value = "";
        }
        showError(box, "");
        if (window.EMSOverlay && typeof window.EMSOverlay.open === "function") {
            window.EMSOverlay.open(box);
        } else {
            box.hidden = false;
        }
    }

    function close(box) {
        if (window.EMSOverlay && typeof window.EMSOverlay.close === "function") {
            window.EMSOverlay.close(box);
        } else if (box) {
            box.hidden = true;
        }
    }

    function filenameFrom(response) {
        var header = response.headers.get("Content-Disposition") || "";
        var utf = /filename\*=UTF-8''([^;]+)/i.exec(header);
        if (utf) {
            try {
                return decodeURIComponent(utf[1]);
            } catch (error) {
                /* ASCII adına düşür */
            }
        }
        var ascii = /filename="([^"]+)"/i.exec(header);
        return ascii ? ascii[1] : "arayis.pdf";
    }

    function save(blob, filename) {
        var url = window.URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(function () {
            window.URL.revokeObjectURL(url);
        }, 1000);
    }

    function readError(response, fallback) {
        return response
            .json()
            .then(function (data) {
                return (data && (data.message || data.detail)) || fallback;
            })
            .catch(function () {
                return fallback;
            });
    }

    function submit(form) {
        var box = form.closest("[data-sr-arayis-dialog]");
        var base = box ? box.getAttribute("data-sr-arayis-url") : "";
        if (!base || !current.recordId) {
            return;
        }
        var fallback = box.getAttribute("data-msg-error") || "";
        var button = form.querySelector("[data-sr-arayis-submit]");
        var body = new FormData();
        var place = form.querySelector("input[name=place]");
        body.append("place", place ? place.value.trim() : "");
        var token = window.EMSCore && window.EMSCore.getCsrfToken ? window.EMSCore.getCsrfToken() : "";
        if (button) {
            button.disabled = true;
        }
        showError(box, "");
        window
            .fetch(base.replace(ZERO_ID, current.recordId), {
                method: "POST",
                body: body,
                credentials: "same-origin",
                headers: { "X-CSRFToken": token || "", Accept: "application/pdf, application/json" },
            })
            .then(function (response) {
                var type = response.headers.get("Content-Type") || "";
                if (response.ok && type.indexOf("application/pdf") === 0) {
                    return response.blob().then(function (blob) {
                        save(blob, filenameFrom(response));
                        close(box);
                        toast(box.getAttribute("data-msg-done"), "success");
                    });
                }
                return readError(response, fallback).then(function (text) {
                    showError(box, text);
                });
            })
            .catch(function () {
                showError(box, fallback);
            })
            .then(function () {
                if (button) {
                    button.disabled = false;
                }
            });
    }

    /* Kart açılanda kartdakı düyməyə qeyd id-si yazılır (düymə yalnız səlahiyyətli aktorda render olunur). */
    document.addEventListener("sr:card", function (event) {
        var payload = (event && event.detail) || {};
        var button = document.querySelector("[data-sr-arayis-card]");
        if (!button) {
            return;
        }
        button.setAttribute("data-sr-arayis", payload.record_id || "");
        button.setAttribute("data-sr-name", payload.name || "");
        button.hidden = !payload.record_id;
    });

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest ? event.target.closest("[data-sr-arayis]") : null;
        if (!trigger) {
            return;
        }
        event.preventDefault();
        open(trigger.getAttribute("data-sr-arayis"), trigger.getAttribute("data-sr-name"));
    });

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.matches || !form.matches("[data-sr-arayis-form]")) {
            return;
        }
        event.preventDefault();
        submit(form);
    });
})(window, document);
