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

    /* Ağac qovşağı seçiləndə bölmə YENİDƏN yüklənir; swap-dan sonra brauzer
       panelin başına qayıdır və istifadəçi «başqa sətir seçildi» zənn edirdi
       (QA 2026-09-06 şikayəti). Yükləndikdən sonra seçilmiş sətri öz
       sürüşmə konteynerində görünürə gətiririk — səhifə tullanmır. */
    document.addEventListener("profile:section:loaded", function (event) {
        var detail = event.detail || {};
        if (detail.section !== "org-structure-tree") {
            return;
        }
        var panel = detail.panel || document;
        var selected = panel.querySelector('.ems-tree__row[aria-selected="true"]');
        if (!selected) {
            return;
        }
        try {
            selected.scrollIntoView({ block: "center", inline: "nearest" });
        } catch (e) {
            selected.scrollIntoView(false);
        }
    });

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

    /* Qovşaq seçiləndə YALNIZ detal paneli yenilənir (2026-09-08, sahib şikayəti
     * «klik edirəm açılır, sonra bağlanır»): fraqment endpoint-indən eyni bölmə
     * HTML-i alınır, ondan `[data-tof-detail]` çıxarılıb yerində əvəzlənir. Ağac
     * DOM-u toxunulmaz qalır → açıq/bağlı vəziyyət itmir. URL `replaceState` ilə
     * `st_unit`-i daşıyır ki, yeniləmə/paylaşma seçimi saxlasın. Fraqment
     * alınmasa köhnə yol (bütöv panel) işə düşür. */
    var treeDetailRequest = 0;

    function loadTreeDetail(host, unitId) {
        var pane = host.querySelector("[data-tof-detail]");
        var fragmentBase = host.getAttribute("data-tof-tree-detail-url");
        var section = host.getAttribute("data-tof-section");
        var pageUrl = sectionUrl(section, { st_unit: unitId });
        if (!pane || !fragmentBase || typeof window.fetch !== "function") {
            reload(section, pageUrl);
            return;
        }
        var request = ++treeDetailRequest;
        var url = new URL(fragmentBase, window.location.origin);
        var params = new URLSearchParams(window.location.search);
        params.delete("section");
        params.set("st_unit", unitId);
        url.search = params.toString();
        pane.setAttribute("aria-busy", "true");
        window
            .fetch(url.toString(), {
                credentials: "same-origin",
                headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
            })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("http_" + response.status);
                }
                return response.json();
            })
            .then(function (payload) {
                if (request !== treeDetailRequest) {
                    return;
                }
                var html = payload && payload.html;
                if (!html) {
                    throw new Error("bad_payload");
                }
                var doc = new window.DOMParser().parseFromString(html, "text/html");
                var next = doc.querySelector("[data-tof-detail]");
                if (!next) {
                    throw new Error("detail_missing");
                }
                pane.innerHTML = next.innerHTML;
                pane.removeAttribute("aria-busy");
                if (window.EMSBootstrapSelect) {
                    window.EMSBootstrapSelect.init(pane);
                }
                if (window.history && window.history.replaceState) {
                    window.history.replaceState({ section: section, ajax: true }, "", pageUrl);
                }
                pane.dispatchEvent(new CustomEvent("tof:detail-loaded", { bubbles: true, detail: { unit: unitId } }));
            })
            .catch(function () {
                if (request !== treeDetailRequest) {
                    return;
                }
                pane.removeAttribute("aria-busy");
                toast(host.getAttribute("data-tof-tree-error") || "", "error");
                reload(section, pageUrl);
            });
    }

    document.addEventListener("ems:tree-select", function (event) {
        var host = root();
        if (!host || !event.detail || !event.detail.node) {
            return;
        }
        var section = host.getAttribute("data-tof-section");
        if (section !== "org-structure-tree") {
            return;
        }
        loadTreeDetail(host, event.detail.node);
    });

    /* Yol (breadcrumb) düyməsi: ağacda həmin qovşağı seç (+ onu görünürə gətir). */
    window.EMSDelegate.on("click", "[data-tof-tree-jump]", function (event, btn) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var row = host.querySelector('.ems-tree__row[data-ems-tree-node="' + btn.getAttribute("data-tof-tree-jump") + '"]');
        if (!row) {
            return;
        }
        // Valideyn qrupları aç ki, sətir görünsün.
        var group = row.closest(".ems-tree__group");
        while (group) {
            group.hidden = false;
            var parentRow = group.parentElement ? group.parentElement.querySelector(".ems-tree__row") : null;
            if (parentRow) {
                parentRow.setAttribute("aria-expanded", "true");
            }
            group = group.parentElement ? group.parentElement.closest(".ems-tree__group") : null;
        }
        if (window.EMSNav && typeof window.EMSNav.selectTreeRow === "function") {
            window.EMSNav.selectTreeRow(row);
        }
        try {
            row.scrollIntoView({ block: "nearest" });
        } catch (e) {
            row.scrollIntoView(false);
        }
    });

    /* ---- Rəhbər seçicisi (axtarışlı, server-backed) ---------------------- */

    /* Native `<select>` əvəzlənib: siyahı `structure_head_candidates` lookup-undan
     * debounce-lu axtarışla, səhifə-səhifə gəlir. Seçici BİR dəfə qurulur —
     * dialoq DOM-da qalır, hər açılışda yalnız dəyəri sinxronlaşdırılır. */
    var headPicker = null;
    //: Dialoq açılana qədər saxlanılan prefill dəyərləri (bax aşağıdakı handler).
    var pendingHeadValues = null;

    function headPickerFor(dialog) {
        var host = dialog.querySelector("[data-tof-head-picker]");
        var field = dialog.querySelector("#tof-head-user");
        // `data-url` boşdursa (məs. server yenidən başladılmayıb və kontekst
        // açarı hələ yoxdur) YARIMÇIQ seçici qurma: boş URL cari səhifəyə fetch
        // edib HTML alır, menyu isə heç vaxt dolmur. Sahə adi mətn kimi qalır,
        // gizli `head` dəyəri prefill-dən gəlir — forma yenə göndərilir.
        if (!host || !field || !window.EMSSearchableSelect || !host.dataset.url) {
            return null;
        }
        if (!headPicker || !document.contains(headPicker.el)) {
            headPicker = window.EMSSearchableSelect.create(host, {
                url: host.dataset.url || "",
                multi: false,
                skeleton: true,
                emptyText: host.dataset.empty || "",
                // Seçim BİRBAŞA gizli sahəyə yazılır — forma dəyişmədən göndərilir.
                onChange: function () {
                    field.value = headPicker ? headPicker.value() : "";
                },
            });
        }
        return headPicker;
    }

    /* Dialoq açılanda: cari rəhbər çip kimi görünsün, boşdursa seçici təmiz olsun. */
    function syncHeadPicker(dialog, values) {
        var picker = headPickerFor(dialog);
        if (!picker) {
            return;
        }
        var id = values && values.head ? String(values.head) : "";
        var label = (values && values.head_label) || "";
        picker.reset();
        if (id && label) {
            picker.setValue(id, label);
        }
        var field = dialog.querySelector("#tof-head-user");
        if (field) {
            field.value = id;
        }
    }

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
            pendingHeadValues = dialog.querySelector("[data-tof-head-picker]") ? values : null;
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
        // Seçici GÖRÜNƏN dialoqda qurulur — menyunun yerləşdirilməsi ölçü tələb edir.
        if (pendingHeadValues) {
            syncHeadPicker(dialog, pendingHeadValues);
            pendingHeadValues = null;
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
            .then(function (payload) {
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(form.closest(".ems-overlay"));
                }
                // Şablon mətni yoxdursa serverin öz mesajı göstərilir (məs.
                // «X «Y» fakültəsinə dekan təyin edildi») — səssiz uğur olmasın.
                toast(form.getAttribute("data-tof-success") || (payload && payload.message) || "", "success");
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
