/* =========================================================================
   Tədris şöbəsi bölmələri — ekran 01/03/04 davranışı (dizayn handoff Mərhələ 1).

   NƏ EDİR
   -------
   * ağac qovşağı seçiləndə paneli `?st_unit=<id>` ilə YENİDƏN YÜKLƏYİR
     (detal server-render-lidir — kliyentdə ikinci data modeli saxlanılmır);
   * dialoqları (bölmə yaratma/adını dəyişmə/rəhbər təyini/arxivləmə,
     ixtisas və fənn formu) sətirdən gələn `data-*` dəyərləri ilə DOLDURUR;
   * formu JSON endpoint-inə göndərir və uğurda paneli yeniləyir.

   NƏ ETMİR
   --------
   Ağacın klaviatura naviqasiyası, fokus tələsi, səbəb sayğacı və filtr
   panelinin draft↔applied məntiqi ORTAQ qatdadır (`static/js/ems_ui/*.js`) —
   burada TƏKRARLANMIR.

   AJAX-SAFE: yalnız `EMSDelegate` (sənəd səviyyəli) + `EMSReady` — panel
   swap-da handler stack-lənmir, `[data-tof-root]` yoxdursa heç nə etmir.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSTeachingOffice) {
        return;
    }

    function root() {
        return document.querySelector("[data-tof-root]");
    }

    function reload(section, url) {
        if (window.EMSProfileLoadSection) {
            window.EMSProfileLoadSection(section, url);
        } else {
            window.location.assign(url);
        }
    }

    function sectionUrl(section, params) {
        var url = new URL(window.location.pathname, window.location.origin);
        var search = new URLSearchParams(window.location.search);
        search.set("section", section);
        Object.keys(params || {}).forEach(function (key) {
            if (params[key] === "" || params[key] === null || params[key] === undefined) {
                search.delete(key);
            } else {
                search.set(key, params[key]);
            }
        });
        url.search = search.toString();
        return url.toString();
    }

    function toast(message, kind) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    /** CSRF tokeni — ƏVVƏLCƏ formanın öz gizli sahəsindən.
     *
     * ⚠️ Niyə kukidən DEYİL? `EMSCore.getCsrfToken()` sabit `csrftoken` kuki
     * adını oxuyur, halbuki bəzi mühitlərdə (staging_inspect: CSRF_COOKIE_NAME
     * = "emsarena_staging_csrftoken") ad fərqlidir — həmin halda eyni hostdakı
     * BAŞQA serverin köhnə kukisi götürülür və server 403 qaytarır. Formanın
     * `{% csrf_token %}` sahəsi HƏMİŞƏ cari sessiyanın tokenidir.
     */
    function csrfToken(form) {
        var field = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
        if (field && field.value) {
            return field.value;
        }
        // Forma verilməyibsə (dialoqsuz `data-tof-submit`) səhifədəki İSTƏNİLƏN
        // `{% csrf_token %}` sahəsi götürülür — o da cari sessiyanın tokenidir.
        field = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (field && field.value) {
            return field.value;
        }
        return (window.EMSCore && window.EMSCore.getCsrfToken && window.EMSCore.getCsrfToken()) || "";
    }

    /** Formu `application/x-www-form-urlencoded` kimi göndərir (server `request.POST` oxuyur).
     *
     * Massiv dəyər ÇOXLU sahə kimi yazılır (`programs=a&programs=b`) — server
     * onu `request.POST.getlist()` ilə oxuyur (məs. semestr açılışında ixtisas
     * seçimi). Massiv olmayan dəyər əvvəlki kimi tək sahədir.
     */
    function post(url, payload, form) {
        var body = new URLSearchParams();
        Object.keys(payload).forEach(function (key) {
            var value = payload[key];
            if (value === null || value === undefined) {
                return;
            }
            if (Array.isArray(value)) {
                value.forEach(function (item) {
                    body.append(key, item);
                });
                return;
            }
            body.append(key, value);
        });
        return window.EMSCore.fetchJSON(url, {
            method: "POST",
            body: body.toString(),
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRFToken": csrfToken(form),
            },
        });
    }

    function fieldsOf(form) {
        var payload = {};
        var nodes = form.querySelectorAll("[name]");
        for (var i = 0; i < nodes.length; i += 1) {
            var el = nodes[i];
            if (el.name === "csrfmiddlewaretoken") {
                continue;
            }
            if (el.type === "checkbox") {
                payload[el.name] = el.checked ? "1" : "";
            } else if (el.tagName === "SELECT" && el.multiple) {
                // Çoxlu seçim → massiv (server `getlist` oxuyur).
                payload[el.name] = Array.prototype.filter
                    .call(el.options, function (option) {
                        return option.selected;
                    })
                    .map(function (option) {
                        return option.value;
                    });
            } else if (Object.prototype.hasOwnProperty.call(payload, el.name)) {
                // Eyni adlı bir neçə sahə (məs. toplu əməlin gizli `ids`
                // sahələri) → massiv; `post()` onu təkrarlanan sahə kimi yazır.
                payload[el.name] = [].concat(payload[el.name], el.value);
            } else {
                payload[el.name] = el.value;
            }
        }
        return payload;
    }

    function showFormError(form, message, field) {
        var box = form.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
        var nodes = form.querySelectorAll("[name]");
        for (var i = 0; i < nodes.length; i += 1) {
            nodes[i].setAttribute("aria-invalid", nodes[i].name === field ? "true" : "false");
        }
    }

    /* ---- Ağac seçimi (ekran 01) ------------------------------------------ */

    document.addEventListener("ems:tree-select", function (event) {
        var host = root();
        if (!host || !event.detail || !event.detail.node) {
            return;
        }
        var section = host.getAttribute("data-tof-section");
        if (section !== "org-structure-tree") {
            return;
        }
        reload(section, sectionUrl(section, { st_unit: event.detail.node }));
    });

    /* ---- Dialoq açılışı: sətir/qovşaq dəyərlərini formaya köçür ---------- */

    window.EMSDelegate.on("click", "[data-tof-open]", function (event, btn) {
        event.preventDefault();
        var dialogId = btn.getAttribute("data-tof-open");
        var dialog = document.getElementById(dialogId);
        if (!dialog) {
            return;
        }
        var form = dialog.querySelector("form");
        if (form) {
            showFormError(form, "");
            var prefill = btn.getAttribute("data-tof-prefill");
            var values = {};
            if (prefill) {
                try {
                    values = JSON.parse(prefill);
                } catch (err) {
                    values = {};
                }
            }
            var nodes = form.querySelectorAll("[name]");
            for (var i = 0; i < nodes.length; i += 1) {
                var el = nodes[i];
                if (el.name === "csrfmiddlewaretoken") {
                    continue;
                }
                var value = Object.prototype.hasOwnProperty.call(values, el.name) ? values[el.name] : "";
                if (el.type === "checkbox") {
                    el.checked = value === "1" || value === true;
                } else if (el.dataset.tofKeep === "1" && value === "") {
                    // `data-tof-keep` sahələr (məs. gizli `action`) sıfırlanmır.
                    continue;
                } else {
                    el.value = value;
                }
                if (window.EMSBootstrapSelect && el.tagName === "SELECT") {
                    window.EMSBootstrapSelect.sync(el);
                }
            }
            var title = dialog.querySelector(".ems-dialog__title");
            var titleOverride = btn.getAttribute("data-tof-title");
            if (title && titleOverride) {
                title.textContent = titleOverride;
            }
        }
        if (window.EMSOverlay) {
            window.EMSOverlay.open(dialog);
            window.EMSOverlay.syncReason(dialog);
        }
    });

    /* ---- Göndərmə -------------------------------------------------------- */

    window.EMSDelegate.on("submit", "form[data-tof-form]", function (event, form) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var url = form.getAttribute("data-tof-url") || host.getAttribute("data-tof-action-url");
        var section = host.getAttribute("data-tof-section");
        var submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
        }
        post(url, fieldsOf(form), form)
            .then(function () {
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(form.closest(".ems-overlay"));
                }
                toast(form.getAttribute("data-tof-success") || "", "success");
                reload(section, sectionUrl(section, {}));
            })
            .catch(function (err) {
                var payload = err && err.payload;
                var message = (payload && payload.message) || form.getAttribute("data-tof-error-text") || "";
                showFormError(form, message, payload && payload.field);
            })
            .then(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    });

    /* ---- Birbaşa əməl düyməsi (dialoqsuz) ------------------------------- */

    /* `data-tof-submit='{"action": …}'` — dialoq açmadan JSON POST edir.
     * `data-tof-confirm` verilibsə ƏVVƏLCƏ təsdiq soruşulur (məs. «cari dövr»
     * açarı bütün universitetin konteksini dəyişir, ona görə təsadüfi klik
     * olmamalıdır). Səbəb tələb edən əməllər BU YOLLA GETMİR — onlar
     * `_reason_dialog.html`-dən keçir. */
    window.EMSDelegate.on("click", "[data-tof-submit]", function (event, btn) {
        event.preventDefault();
        if (btn.disabled) {
            return;
        }
        var host = root();
        if (!host) {
            return;
        }
        var payload;
        try {
            payload = JSON.parse(btn.getAttribute("data-tof-submit"));
        } catch (err) {
            return;
        }
        var confirmText = btn.getAttribute("data-tof-confirm");
        if (confirmText && !window.confirm(confirmText)) {
            return;
        }
        var section = host.getAttribute("data-tof-section");
        var url = host.getAttribute("data-tof-action-url");
        btn.disabled = true;
        post(url, payload, null)
            .then(function () {
                reload(section, sectionUrl(section, {}));
            })
            .catch(function (err) {
                var message = (err && err.payload && err.payload.message) || "";
                if (message) {
                    toast(message, "error");
                }
                btn.disabled = false;
            });
    });

    window.EMSTeachingOffice = { post: post, sectionUrl: sectionUrl, root: root, reload: reload };
})(window, document);
