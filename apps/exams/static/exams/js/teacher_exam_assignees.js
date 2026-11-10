/* =========================================================================
   «Tapşırıq təyin olunmuşlar» — qrup / tələbə əlavə et, çıxar, istisna et (sahib 2026-10-27).

   Bütün dəyərlər `[data-eas-root]` data-atributlarından oxunur (CSP: inline JS yoxdur).
   Əməl POST → `data-update-url` (sehrbazın saxlama qapıları). Server cavabları:
     * 200 {success, message, warnings}      → YALNIZ canlı hissələr yenilənir (mesaj toast kimi);
     * 400 {unit_coverage_required: [...]}  → fənnin jurnalında olmayan qrup: səbəb dialoqu → forced_units;
     * 409 {subject_change_required: {...}} → nəticəli midterm: təsdiq + səbəb → subject_change_*;
     * başqa xəta                            → toast.

   Canlı yeniləmə (sahib 2026-11-10: «səhifə çox yavaş açılır, search edərkən zəif hərəkət edir»):
   süzgəc, axtarış, qrup çipi, sıralama, səhifələmə və hər təyinat əməli artıq TAM SƏHİFƏNİ yenidən
   yükləmir — eyni URL `X-EAS-Partial: 1` başlığı ilə çağırılır, server yalnız `data-eas-live` hissələrini
   (xülasə + çiplər, cədvəl) qaytarır və onlar yerində əvəz olunur. Köhnə (yavaş) cavab yenisinin üstünə
   yazılmır (AbortController + sıra nömrəsi); xəta olarsa adi keçidə düşür. URL `history` ilə saxlanılır.
   AJAX-safe: EMSReady (idempotent init) + EMSDelegate (document-səviyyəli, yığılmır).
   ========================================================================= */
(function (window, document) {
    "use strict";

    var REASON_MIN = 10;
    var PARTIAL_HEADER = "X-EAS-Partial";
    var FILTER_FIELDS = ["group", "source", "status"];
    var pending = null; // səbəb gözləyən əməl: {action, fields, kind, groups}
    var liveSeq = 0;
    var liveController = null;
    var sending = false;

    function root() {
        return document.querySelector("[data-eas-root]");
    }

    function msg(key) {
        var el = root();
        return (el && el.dataset[key]) || "";
    }

    function toast(text, level) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(text, level || "danger");
        }
    }

    function confirmAction(body) {
        if (window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            return window.EMSConfirm.open({ body: body, danger: true, confirmLabel: msg("msgConfirm") });
        }
        return Promise.resolve(true);
    }

    function picker(selector) {
        var el = document.querySelector(selector);
        return el && el._emsSearchable ? el._emsSearchable : null;
    }

    /* ---- canlı yeniləmə: yalnız dəyişən hissələr ------------------------- */
    function samePage(url) {
        return url.origin === window.location.origin && url.pathname === window.location.pathname;
    }

    function region(name, scope) {
        return (scope || root() || document).querySelector('[data-eas-live="' + name + '"]');
    }

    function setBusy(on) {
        ["table", "summary"].forEach(function (name) {
            var el = region(name);
            if (el) {
                el.classList.toggle("eas-live--busy", !!on);
                el.setAttribute("aria-busy", on ? "true" : "false");
            }
        });
    }

    /** Ehtiyat yol: adi (tam) keçid — eyni ünvandırsa yenidən yükləmə. */
    function hardNavigate(url) {
        if (url.toString() === window.location.href) {
            window.location.reload();
        } else {
            window.location.assign(url.toString());
        }
    }

    function moveChildren(from, to) {
        to.textContent = "";
        while (from.firstChild) {
            to.appendChild(document.adoptNode(from.firstChild));
        }
    }

    function swapRegion(doc, name) {
        var target = region(name);
        var fresh = region(name, doc);
        if (!target || !fresh) {
            return false;
        }
        moveChildren(fresh, target);
        return true;
    }

    function optionSignature(select) {
        return Array.prototype.map
            .call(select.options, function (option) {
                return option.value + "=" + option.textContent;
            })
            .join("|");
    }

    function setSelectValue(select, value) {
        select.value = value;
        if (select.value !== value) {
            select.value = "";
        }
    }

    /** Qrup süzgəcinin variantları (say ilə) — forma yerində qalır, yalnız siyahı dəyişibsə yenilənir. */
    function syncGroupOptions(doc) {
        var select = document.getElementById("easGroupSelect");
        var fresh = doc.getElementById("easGroupSelect");
        if (!select || !fresh || optionSignature(select) === optionSignature(fresh)) {
            return;
        }
        var value = select.value;
        moveChildren(fresh, select);
        setSelectValue(select, value);
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    /** Süzgəc formasını URL-ə uyğunlaşdır (çip / sıralama / «geri» düyməsi formanı dəyişmir). */
    function syncForm(url) {
        var el = root();
        var form = el && el.querySelector(".js-eas-filter-form");
        if (!form) {
            return;
        }
        var params = url.searchParams;
        var apply = function (name, value) {
            var select = form.querySelector('select[name="' + name + '"]');
            if (!select) {
                return;
            }
            setSelectValue(select, value);
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(select);
            }
        };
        FILTER_FIELDS.forEach(function (name) {
            apply(name, params.get(name) || "");
        });
        var order = params.get("order") || "";
        if (!order && params.get("sort_by") && params.get("sort_dir")) {
            order = params.get("sort_by") + "_" + params.get("sort_dir");
        }
        apply("order", order === "name_asc" ? "" : order);
        var search = form.querySelector('input[name="q"]');
        var value = params.get("q") || "";
        if (search && document.activeElement !== search && search.value !== value) {
            search.value = value;
            if (window.EMSSearchInput && typeof window.EMSSearchInput.sync === "function") {
                window.EMSSearchInput.sync(search, value);
            }
        }
    }

    function formUrl(form) {
        var url = new URL(window.location.pathname, window.location.href);
        new window.FormData(form).forEach(function (value, key) {
            if (typeof value === "string" && value !== "") {
                url.searchParams.append(key, value);
            }
        });
        return url;
    }

    /**
     * Canlı hissələri `target` ünvanından yenilə.
     *   opts.push    — tarixçəyə yeni qeyd (əks halda cari qeyd əvəzlənir);
     *   opts.keepUrl — ünvan dəyişmir (təyinat əməlindən sonra cari görünüş, «geri» düyməsi);
     *   opts.scroll  — cədvəlin başı görünmürsə ora sürüş (səhifələmə).
     */
    function refresh(target, opts) {
        opts = opts || {};
        var url = new URL(String(target), window.location.href);
        if (!root() || typeof window.fetch !== "function" || typeof window.DOMParser !== "function") {
            hardNavigate(url);
            return;
        }
        if (liveController) {
            liveController.abort(); // köhnə sorğu artıq lazım deyil
        }
        liveController = typeof window.AbortController === "function" ? new window.AbortController() : null;
        var mine = ++liveSeq;
        var headers = { Accept: "text/html", "X-Requested-With": "XMLHttpRequest" };
        headers[PARTIAL_HEADER] = "1";
        setBusy(true);
        window
            .fetch(url.toString(), {
                credentials: "same-origin",
                headers: headers,
                signal: liveController ? liveController.signal : undefined,
            })
            .then(function (response) {
                if (!response.ok || response.redirected) {
                    throw new Error("http_" + response.status);
                }
                return response.text();
            })
            .then(function (html) {
                if (mine !== liveSeq) {
                    return; // daha yeni sorğu var — köhnə cavab atılır
                }
                var doc = new window.DOMParser().parseFromString(html, "text/html");
                if (!swapRegion(doc, "table")) {
                    throw new Error("no_region");
                }
                swapRegion(doc, "summary");
                syncGroupOptions(doc);
                setBusy(false);
                if (!opts.keepUrl) {
                    try {
                        window.history[opts.push ? "pushState" : "replaceState"]({ eas: true }, "", url.toString());
                    } catch (err) {
                        /* ignore */
                    }
                }
                syncForm(url);
                var table = region("table");
                if (opts.scroll && table && table.getBoundingClientRect().top < 0) {
                    table.scrollIntoView({ block: "start" });
                }
            })
            .catch(function (err) {
                if (err && err.name === "AbortError") {
                    return;
                }
                if (mine === liveSeq) {
                    hardNavigate(url);
                }
            });
    }

    function clearPickers() {
        [".js-eas-unit-picker", ".js-eas-user-picker"].forEach(function (selector) {
            var pick = picker(selector);
            if (pick && typeof pick.reset === "function" && pick.ids().length) {
                pick.reset();
            }
        });
    }

    function send(action, fields, extra) {
        var el = root();
        if (!el || !window.EMSCore || sending) {
            return;
        }
        var body = new FormData();
        body.append("action", action);
        Object.keys(fields).forEach(function (name) {
            [].concat(fields[name]).forEach(function (value) {
                body.append(name, value);
            });
        });
        Object.keys(extra || {}).forEach(function (name) {
            body.append(name, extra[name]);
        });
        var headers = {};
        headers[PARTIAL_HEADER] = "1";
        sending = true; // cüt klik eyni əməli iki dəfə göndərməsin
        el.classList.add("eas-page--sending");
        var done = function () {
            sending = false;
            el.classList.remove("eas-page--sending");
        };
        // then(uğur, rədd): uğur qolundakı xəta «əməliyyat alınmadı» kimi GÖSTƏRİLMİR (əməl artıq saxlanıb).
        window.EMSCore.fetchJSON(el.dataset.updateUrl, { method: "POST", body: body, headers: headers }).then(
            function (payload) {
                done();
                payload = payload || {};
                if (payload.message) {
                    toast(payload.message, "success");
                }
                (payload.warnings || []).forEach(function (warning) {
                    toast(warning, "warning");
                });
                clearPickers();
                refresh(window.location.href, { keepUrl: true });
            },
            function (err) {
                done();
                var payload = (err && err.payload) || {};
                if (payload.unit_coverage_required) {
                    openReason({ action: action, fields: fields, kind: "units", groups: payload.unit_coverage_required }, payload.error);
                    return;
                }
                if (payload.subject_change_required) {
                    openReason({ action: action, fields: fields, kind: "subject", groups: [] }, payload.error);
                    return;
                }
                toast(payload.error || msg("msgError"));
            }
        );
    }

    function groupLine(group) {
        var text = msg("msgUncovered").replace("{n}", group.uncovered).replace("{total}", group.total);
        var names = (group.names || []).join(", ");
        if (group.more) {
            names += (names ? ", " : "") + msg("msgMore").replace("{n}", group.more);
        }
        return group.name + " — " + text + (names ? " (" + names + ")" : "");
    }

    function openReason(state, message) {
        var dialog = document.getElementById("easReasonDialog");
        if (!dialog || !window.EMSOverlay) {
            toast(message || msg("msgError"));
            return;
        }
        pending = state;
        dialog.querySelector("[data-eas-reason-message]").textContent = message || "";
        var list = dialog.querySelector("[data-eas-reason-list]");
        list.textContent = "";
        state.groups.forEach(function (group) {
            var item = document.createElement("li");
            item.textContent = groupLine(group);
            list.appendChild(item);
        });
        dialog.querySelector("[data-eas-reason-confirm-wrap]").hidden = state.kind !== "subject";
        dialog.querySelector("[data-eas-reason-confirm]").checked = false;
        window.EMSOverlay.open("easReasonDialog");
    }

    function submitReason(event) {
        event.preventDefault();
        var dialog = document.getElementById("easReasonDialog");
        if (!dialog || !pending) {
            return;
        }
        var reason = (dialog.querySelector("[data-eas-reason-text]").value || "").trim();
        if (reason.length < REASON_MIN) {
            dialog.querySelector("[data-eas-reason-text]").focus();
            return;
        }
        var extra = {};
        if (pending.kind === "subject") {
            if (!dialog.querySelector("[data-eas-reason-confirm]").checked) {
                dialog.querySelector("[data-eas-reason-confirm]").focus();
                return;
            }
            extra.subject_change_confirm = "1";
            extra.subject_change_reason = reason;
        } else {
            var forced = {};
            pending.groups.forEach(function (group) {
                forced[group.id] = reason;
            });
            extra.forced_units = JSON.stringify(forced);
        }
        var state = pending;
        pending = null;
        window.EMSOverlay.close(dialog);
        send(state.action, state.fields, extra);
    }

    window.EMSReady(function () {
        var el = root();
        if (!el || !el.dataset.canEdit || !window.EMSSearchableSelect) {
            return;
        }
        window.EMSSearchableSelect.create(el.querySelector(".js-eas-unit-picker"), {
            url: el.dataset.groupSearchUrl,
            multi: true,
        });
        window.EMSSearchableSelect.create(el.querySelector(".js-eas-user-picker"), {
            url: el.dataset.userSearchUrl,
            multi: true,
        });
    });

    window.EMSDelegate.on("click", ".js-eas-add-units", function () {
        var pick = picker(".js-eas-unit-picker");
        var ids = pick ? pick.ids() : [];
        if (!ids.length) {
            toast(msg("msgPickGroups"), "warning");
            return;
        }
        send("add_units", { allowed_units: ids });
    });

    window.EMSDelegate.on("click", ".js-eas-add-users", function () {
        var pick = picker(".js-eas-user-picker");
        var ids = pick ? pick.ids() : [];
        if (!ids.length) {
            toast(msg("msgPickUsers"), "warning");
            return;
        }
        send("add_users", { users: ids });
    });

    window.EMSDelegate.on("click", ".js-eas-remove-unit", function (event, button) {
        confirmAction(button.dataset.label + "\n\n" + msg("msgRemoveUnit")).then(function (ok) {
            if (ok) {
                send("remove_unit", { unit: button.dataset.unit });
            }
        });
    });

    var USER_MESSAGES = {
        remove_user: "msgRemoveUser",
        exclude_user: "msgExcludeUser",
        include_user: "msgIncludeUser",
    };

    window.EMSDelegate.on("click", ".js-eas-user-action", function (event, button) {
        var action = button.dataset.action;
        if (!USER_MESSAGES[action]) {
            return;
        }
        confirmAction(button.dataset.name + "\n\n" + msg(USER_MESSAGES[action])).then(function (ok) {
            if (ok) {
                send(action, { user: button.dataset.user });
            }
        });
    });

    window.EMSDelegate.on("submit", ".js-eas-reason-form", submitReason);

    // Süzgəc forması (seçim dəyişəndə / axtarışda `results_filter_ui.js` formanı göndərir) → canlı yeniləmə.
    window.EMSDelegate.on("submit", ".js-eas-filter-form", function (event, form) {
        event.preventDefault();
        try {
            // EMSSearchInput.submitForm tam yenidən yükləmə üçün fokus izi qoyur — burada səhifə yüklənmir.
            window.sessionStorage.removeItem("ems.search.focus");
        } catch (err) {
            /* private rejim */
        }
        refresh(formUrl(form), { push: true });
    });

    // Qrup çipləri, sütun sıralaması, səhifələmə — eyni səhifənin keçidləri yerində yenilənir.
    window.EMSDelegate.on("click", "[data-eas-live] a[href]", function (event, link) {
        if (event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }
        if (link.target && link.target !== "_self") {
            return;
        }
        var url = new URL(link.getAttribute("href"), window.location.href);
        if (!samePage(url)) {
            return;
        }
        event.preventDefault();
        refresh(url, { push: true, scroll: !!link.closest('[data-eas-live="table"]') });
    });

    window.EMSReady.once("eas-popstate", function () {
        window.addEventListener("popstate", function () {
            if (root()) {
                refresh(window.location.href, { keepUrl: true });
            }
        });
    });
})(window, document);
