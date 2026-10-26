/* «Parol sıfırlama» bölməsi (account.password_reset, 2026-09-30).
 *
 * AJAX-SAFE: bütün hadisələr `EMSDelegate.on` ilə `document`-ə bir dəfə bağlanır
 * (panel swap olunsa da işləyir, yığılmır); fayl təkrar yüklənsə də bayraqla bir
 * dəfə qeydiyyat olur. Endpoint URL-ləri `data-*`, mətnlər `json_script`-dən
 * (#pwr-strings) oxunur — faylda sərt yazılmış istifadəçi mətni yoxdur.
 *
 * TƏHLÜKƏSİZLİK: müvəqqəti parol YALNIZ `[data-pwr-secret]` elementinin mətnində
 * yaşayır — heç bir dəyişəndə, storage-da və ya console-da saxlanılmır; «gizlət»
 * düyməsi, dialoqun bağlanması, 10 dəqiqəlik taymer və səhifədən çıxış onu DOM-dan
 * silir. Bütün dinamik məzmun `textContent` ilə yazılır (HTML inyeksiyası yoxdur).
 *
 * 2026-10-26 (sahib): sıfırlama ƏVVƏLCƏ səbəb dialoqundan keçir (`_reason_dialog.html`,
 * `EMSOverlay`), parol isə ayrıca dialoqda (`#pwr-result-dialog`) BİR DƏFƏ göstərilir.
 */
(function (window, document) {
    "use strict";

    if (window.__emsPasswordResetAdminLoaded) {
        return;
    }
    window.__emsPasswordResetAdminLoaded = true;

    var EMPTY = "\u2014"; // tipoqrafik boşluq işarəsi (tərcümə tələb etmir)
    var STATUS_BADGE = {
        active: "ems-badge ems-badge--success",
        blocked: "ems-badge ems-badge--danger",
        deleted: "ems-badge ems-badge--muted",
        login_closed: "ems-badge ems-badge--archived"
    };
    var people = Object.create(null);

    /* Birdəfəlik parol dialoqu ayrı fayldadır (`account_password_reset_dialogs.js`) — yüklənməyibsə səssiz. */
    function clearSecret() {
        if (window.EMSPwrDialogs && typeof window.EMSPwrDialogs.clearSecret === "function") {
            window.EMSPwrDialogs.clearSecret();
        }
    }

    function root() {
        return document.querySelector("[data-pwr-root]");
    }

    function strings() {
        var node = document.getElementById("pwr-strings");
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent || "{}") || {};
        } catch (error) {
            return {};
        }
    }

    function format(template, values) {
        return String(template || "").replace(/\{(\w+)\}/g, function (match, key) {
            return Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match;
        });
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function errorMessage(error, fallback) {
        var payload = error && error.payload;
        if (payload && typeof payload === "object" && payload.message) {
            return payload.message;
        }
        if (payload && typeof payload === "object" && payload.detail) {
            return payload.detail;
        }
        return fallback;
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = String(text);
        }
        return node;
    }

    function setStatus(scope, message, tone) {
        var status = scope.querySelector("[data-pwr-status]");
        if (!status) {
            return;
        }
        status.textContent = message || "";
        status.hidden = !message;
        status.classList.toggle("is-error", tone === "error");
        status.classList.toggle("is-warning", tone === "warning");
    }

    /* ── Nəticə kartı ─────────────────────────────────────────────────── */
    function fact(list, label, value, fallback) {
        var row = el("div");
        row.appendChild(el("dt", "", label));
        row.appendChild(el("dd", "", value || fallback));
        list.appendChild(row);
    }

    function actionButton(className, iconClass, attribute, id, label) {
        var button = el("button", className);
        button.type = "button";
        button.setAttribute(attribute, String(id));
        var icon = el("i", iconClass);
        icon.setAttribute("aria-hidden", "true");
        button.appendChild(icon);
        button.appendChild(document.createTextNode(" " + (label || "")));
        return button;
    }

    function renderPerson(person, t) {
        var item = el("li", "pwr-person" + (person.can_reset || person.can_rename ? "" : " is-disabled"));
        item.setAttribute("data-user-id", String(person.id));

        var main = el("div", "pwr-person__main");
        main.appendChild(el("p", "pwr-person__name", person.full_name));

        var meta = el("p", "pwr-person__meta");
        var username = el("span", "ems-mono", person.username);
        username.title = t.username || "";
        meta.appendChild(username);
        meta.appendChild(el("span", STATUS_BADGE[person.status] || "ems-badge ems-badge--neutral", person.status_label));
        if (person.password_change_required) {
            meta.appendChild(el("span", "ems-badge ems-badge--warning", t.pendingChange));
        }
        main.appendChild(meta);

        var facts = el("dl", "pwr-person__facts");
        fact(facts, t.roles, (person.roles || []).join(", "), EMPTY);
        fact(facts, t.units, (person.units || []).join(", "), EMPTY);
        fact(facts, t.lastLogin, person.last_login, EMPTY);
        main.appendChild(facts);

        if (!person.can_reset && person.reason) {
            main.appendChild(el("p", "pwr-person__reason", person.reason));
        }
        item.appendChild(main);

        var actions = el("div", "pwr-person__actions");
        if (person.can_reset) {
            actions.appendChild(actionButton("ems-btn ems-btn--danger", "fas fa-key", "data-pwr-reset", person.id, t.reset));
        }
        // Sahib 2026-10-26: «İstifadəçi adını dəyiş» — parolu bilmədən (`account_username_change.js`).
        if (person.can_rename) {
            actions.appendChild(actionButton("ems-btn", "fas fa-user-pen", "data-pwr-rename", person.id, t.rename));
        }
        if (actions.childNodes.length) {
            item.appendChild(actions);
        }
        return item;
    }

    function renderResults(scope, payload) {
        var t = strings();
        var list = scope.querySelector("[data-pwr-results]");
        if (!list) {
            return;
        }
        list.textContent = "";
        people = Object.create(null);
        var results = (payload && payload.results) || [];
        results.forEach(function (person) {
            people[String(person.id)] = person;
            list.appendChild(renderPerson(person, t));
        });
        list.hidden = results.length === 0;

        if (!results.length) {
            setStatus(scope, (payload && payload.notice) || t.noResults, payload && payload.notice ? "error" : "warning");
            return;
        }
        var message = payload.has_more ? t.hasMore : t.found;
        setStatus(scope, message, payload.has_more ? "warning" : "");
    }

    /* Dialoq faylının istifadə etdiyi ortaq köməkçilər (AJAX-safe: obyekt bir dəfə qurulur). */
    window.EMSPwr = {
        root: root,
        strings: strings,
        format: format,
        toast: toast,
        errorMessage: errorMessage,
        renderPerson: renderPerson,
        getPerson: function (id) {
            return people[String(id)] || null;
        },
        setPerson: function (person) {
            people[String(person.id)] = person;
        }
    };

    /* ── Axtarış ──────────────────────────────────────────────────────── */
    window.EMSDelegate.on("submit", "[data-pwr-search-form]", function (event, form) {
        event.preventDefault();
        var scope = form.closest("[data-pwr-root]");
        var input = form.querySelector("[data-pwr-query]");
        if (!scope || !input) {
            return;
        }
        var query = (input.value || "").trim();
        var t = strings();
        closeSuggest(scope);
        clearSecret();
        if (query.length < 2) {
            setStatus(scope, input.validationMessage || t.noResults, "warning");
            input.focus();
            return;
        }
        var button = form.querySelector("[data-pwr-search-btn]");
        if (button) {
            button.disabled = true;
        }
        setStatus(scope, t.searching, "");
        window.EMSCore.fetchJSON(scope.getAttribute("data-lookup-url"), { method: "POST", data: { q: query } })
            .then(function (payload) {
                renderResults(scope, payload);
            })
            .catch(function (error) {
                var list = scope.querySelector("[data-pwr-results]");
                if (list) {
                    list.textContent = "";
                    list.hidden = true;
                }
                setStatus(scope, errorMessage(error, t.genericError), "error");
            })
            .then(function () {
                if (button) {
                    button.disabled = false;
                }
            });
    });

    /* ── Yazdıqca təklif (sahib 2026-09-30) ──────────────────────────────
     * Yüngül siyahı (ən çoxu 8 nəfər) — yazı dayananda (vahid EMSSearchInput, 1500 ms;
     * Enter burada siyahıdan SEÇİMDİR, ona görə `enter: false`) BİR sorğu; köhnə
     * sorğu AbortController ilə ləğv olunur, gecikmiş cavab (seq) atılır. Seçim
     * istifadəçi adını xanaya yazıb adi axtarışı (tam kart + «sıfırla») işə salır. */
    var suggestController = null;
    var suggestSeq = 0;

    function suggestParts(scope) {
        return {
            input: scope.querySelector("[data-pwr-query]"),
            list: scope.querySelector("[data-pwr-suggest]"),
            hint: scope.querySelector("[data-pwr-suggest-hint]")
        };
    }

    function closeSuggest(scope) {
        var pending = scope && scope.querySelector("[data-pwr-query]");
        if (pending) {
            window.EMSSearchInput.cancel(pending); // Esc / seçim — gözləyən sorğu da düşür
        }
        if (suggestController) {
            suggestController.abort();
            suggestController = null;
        }
        suggestSeq += 1;
        if (!scope) {
            return;
        }
        var parts = suggestParts(scope);
        if (parts.list) {
            parts.list.hidden = true;
            parts.list.textContent = "";
        }
        if (parts.hint) {
            parts.hint.hidden = true;
        }
        if (parts.input) {
            parts.input.setAttribute("aria-expanded", "false");
            parts.input.removeAttribute("aria-activedescendant");
        }
    }

    function initials(name) {
        return String(name || "")
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map(function (word) {
                return word.charAt(0).toUpperCase();
            })
            .join("");
    }

    function renderSuggest(scope, results) {
        var t = strings();
        var parts = suggestParts(scope);
        if (!parts.list || !parts.input) {
            return;
        }
        parts.list.textContent = "";
        if (!results.length) {
            parts.list.appendChild(el("li", "pwr-suggest__empty", t.suggestEmpty));
        }
        results.forEach(function (person, index) {
            var item = el("li", "pwr-suggest__item");
            item.id = "pwr-opt-" + index;
            item.setAttribute("role", "option");
            item.setAttribute("aria-selected", "false");
            item.setAttribute("data-pwr-pick", person.username);
            item.appendChild(el("span", "pwr-suggest__avatar", initials(person.full_name)));
            var text = el("span", "pwr-suggest__text");
            text.appendChild(el("span", "pwr-suggest__name", person.full_name));
            text.appendChild(el("span", "pwr-suggest__meta", person.hint ? person.username + " \u00b7 " + person.hint : person.username));
            item.appendChild(text);
            parts.list.appendChild(item);
        });
        parts.list.hidden = false;
        parts.input.setAttribute("aria-expanded", "true");
        parts.input.removeAttribute("aria-activedescendant");
        if (parts.hint) {
            parts.hint.textContent = results.length ? t.suggestHint : "";
            parts.hint.hidden = !results.length;
        }
    }

    function requestSuggest(scope, query) {
        if (suggestController) {
            suggestController.abort();
        }
        suggestController = typeof window.AbortController === "function" ? new window.AbortController() : null;
        suggestSeq += 1;
        var mySeq = suggestSeq;
        window.EMSCore.fetchJSON(scope.getAttribute("data-suggest-url"), {
            method: "POST",
            data: { q: query },
            signal: suggestController ? suggestController.signal : undefined
        })
            .then(function (payload) {
                if (mySeq === suggestSeq) {
                    renderSuggest(scope, (payload && payload.results) || []);
                }
            })
            .catch(function () {
                // Ləğv edilmiş / uğursuz təklif sorğusu səssizdir — adi «Axtar» işləməkdə davam edir.
            });
    }

    function pick(scope, username) {
        var input = scope.querySelector("[data-pwr-query]");
        var form = scope.querySelector("[data-pwr-search-form]");
        closeSuggest(scope);
        if (!input || !form) {
            return;
        }
        input.value = username;
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
        }
    }

    function moveActive(scope, step) {
        var parts = suggestParts(scope);
        if (!parts.list || parts.list.hidden) {
            return false;
        }
        var items = Array.prototype.slice.call(parts.list.querySelectorAll("[data-pwr-pick]"));
        if (!items.length) {
            return false;
        }
        var current = items.findIndex(function (item) {
            return item.classList.contains("is-active");
        });
        var next = current + step;
        if (next < 0) {
            next = items.length - 1;
        } else if (next >= items.length) {
            next = 0;
        }
        items.forEach(function (item, index) {
            var active = index === next;
            item.classList.toggle("is-active", active);
            item.setAttribute("aria-selected", active ? "true" : "false");
        });
        parts.input.setAttribute("aria-activedescendant", items[next].id);
        if (typeof items[next].scrollIntoView === "function") {
            items[next].scrollIntoView({ block: "nearest" });
        }
        return true;
    }

    window.EMSDelegate.on("input", "[data-pwr-query]", function (event, input) {
        var scope = input.closest("[data-pwr-root]");
        if (!scope || !scope.getAttribute("data-suggest-url")) {
            return;
        }
        if ((input.value || "").trim().length < 2) {
            closeSuggest(scope); // köhnə təkliflər yarımçıq sorğuya aid deyil
        }
    });

    window.EMSSearchInput.delegate("[data-pwr-query]", {
        enter: false,
        onSearch: function (value, meta) {
            var scope = meta.input.closest("[data-pwr-root]");
            if (scope && scope.getAttribute("data-suggest-url") && value.length >= 2) {
                requestSuggest(scope, value);
            } else if (scope) {
                closeSuggest(scope);
            }
        },
    });

    window.EMSDelegate.on("keydown", "[data-pwr-query]", function (event, input) {
        var scope = input.closest("[data-pwr-root]");
        if (!scope) {
            return;
        }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            if (moveActive(scope, event.key === "ArrowDown" ? 1 : -1)) {
                event.preventDefault();
            }
        } else if (event.key === "Enter") {
            var active = scope.querySelector("[data-pwr-suggest] .is-active[data-pwr-pick]");
            if (active) {
                event.preventDefault();
                pick(scope, active.getAttribute("data-pwr-pick"));
            }
        } else if (event.key === "Escape") {
            closeSuggest(scope);
        }
    });

    // Klik xananın fokusunu itirməsin (mobil klaviatura da bağlanmasın).
    window.EMSDelegate.on("mousedown", "[data-pwr-pick]", function (event) {
        event.preventDefault();
    });

    window.EMSDelegate.on("click", "[data-pwr-pick]", function (event, item) {
        event.preventDefault();
        var scope = item.closest("[data-pwr-root]");
        if (scope) {
            pick(scope, item.getAttribute("data-pwr-pick"));
        }
    });

    window.EMSReady.once("pwr-suggest-outside", function () {
        document.addEventListener("click", function (event) {
            var scope = root();
            if (scope && !(event.target && event.target.closest && event.target.closest("[data-pwr-combo]"))) {
                closeSuggest(scope);
            }
        });
    });

    window.EMSReady(function () {
        // Panel (yenidən) göründü — əvvəlki paneldən qalmış parol taymeri varsa sıfırla.
        var scope = root();
        if (!scope) {
            clearSecret();
            return;
        }
        // Şəxs səhifəsindən «Parolu sıfırla» (`?pwr_q=<istifadəçi adı>`) — sahə doldurulub axtarılır, BİR dəfə.
        var initial = scope.getAttribute("data-initial-query") || "";
        var form = scope.querySelector("[data-pwr-search-form]");
        var input = scope.querySelector("[data-pwr-query]");
        if (initial && form && input && !scope.hasAttribute("data-pwr-initial-done")) {
            scope.setAttribute("data-pwr-initial-done", "1");
            input.value = initial;
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
            }
        }
    });
})(window, document);
