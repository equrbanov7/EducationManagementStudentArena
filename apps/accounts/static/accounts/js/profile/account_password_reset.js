/* «Parol sıfırlama» bölməsi (account.password_reset, 2026-09-30).
 *
 * AJAX-SAFE: bütün hadisələr `EMSDelegate.on` ilə `document`-ə bir dəfə bağlanır
 * (panel swap olunsa da işləyir, yığılmır); fayl təkrar yüklənsə də bayraqla bir
 * dəfə qeydiyyat olur. Endpoint URL-ləri `data-*`, mətnlər `json_script`-dən
 * (#pwr-strings) oxunur — faylda sərt yazılmış istifadəçi mətni yoxdur.
 *
 * TƏHLÜKƏSİZLİK: müvəqqəti parol YALNIZ `[data-pwr-secret]` elementinin mətnində
 * yaşayır — heç bir dəyişəndə, storage-da və ya console-da saxlanılmır; «gizlət»
 * düyməsi, 10 dəqiqəlik taymer və səhifədən çıxış onu DOM-dan silir. Bütün
 * dinamik məzmun `textContent` ilə yazılır (HTML inyeksiyası yoxdur).
 */
(function (window, document) {
    "use strict";

    if (window.__emsPasswordResetAdminLoaded) {
        return;
    }
    window.__emsPasswordResetAdminLoaded = true;

    var SECRET_TTL_MS = 10 * 60 * 1000;
    var EMPTY = "\u2014"; // tipoqrafik boşluq işarəsi (tərcümə tələb etmir)
    var STATUS_BADGE = {
        active: "ems-badge ems-badge--success",
        blocked: "ems-badge ems-badge--danger",
        deleted: "ems-badge ems-badge--muted",
        login_closed: "ems-badge ems-badge--archived"
    };
    var people = Object.create(null);
    var secretTimer = null;

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

    /* ── Birdəfəlik parol ─────────────────────────────────────────────── */
    function clearSecret() {
        if (secretTimer) {
            window.clearTimeout(secretTimer);
            secretTimer = null;
        }
        var scope = root();
        if (!scope) {
            return;
        }
        var secret = scope.querySelector("[data-pwr-secret]");
        if (secret) {
            secret.textContent = "";
        }
        var who = scope.querySelector("[data-pwr-result-who]");
        if (who) {
            who.textContent = "";
        }
        var card = scope.querySelector("[data-pwr-result]");
        if (card) {
            card.hidden = true;
        }
    }

    function showSecret(scope, person, password) {
        var t = strings();
        var card = scope.querySelector("[data-pwr-result]");
        var secret = scope.querySelector("[data-pwr-secret]");
        var who = scope.querySelector("[data-pwr-result-who]");
        if (!card || !secret) {
            return;
        }
        secret.textContent = password;
        if (who) {
            who.textContent = format(t.resultFor, { name: person.full_name, username: person.username });
        }
        card.hidden = false;
        if (typeof card.scrollIntoView === "function") {
            card.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        if (secretTimer) {
            window.clearTimeout(secretTimer);
        }
        secretTimer = window.setTimeout(clearSecret, SECRET_TTL_MS);
    }

    /* ── Nəticə kartı ─────────────────────────────────────────────────── */
    function fact(list, label, value, fallback) {
        var row = el("div");
        row.appendChild(el("dt", "", label));
        row.appendChild(el("dd", "", value || fallback));
        list.appendChild(row);
    }

    function renderPerson(person, t) {
        var item = el("li", "pwr-person" + (person.can_reset ? "" : " is-disabled"));
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

        if (person.can_reset) {
            var actions = el("div", "pwr-person__actions");
            var button = el("button", "ems-btn ems-btn--danger");
            button.type = "button";
            button.setAttribute("data-pwr-reset", String(person.id));
            var icon = el("i", "fas fa-key");
            icon.setAttribute("aria-hidden", "true");
            button.appendChild(icon);
            button.appendChild(document.createTextNode(" " + (t.reset || "")));
            actions.appendChild(button);
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

    /* ── Sıfırlama ────────────────────────────────────────────────────── */
    function performReset(scope, button, person) {
        var t = strings();
        var label = button.lastChild;
        button.disabled = true;
        if (label && label.nodeType === 3) {
            label.textContent = " " + t.resetting;
        }
        window.EMSCore.fetchJSON(scope.getAttribute("data-reset-url"), { method: "POST", data: { user_id: person.id } })
            .then(function (payload) {
                var updated = (payload && payload.user) || person;
                people[String(updated.id)] = updated;
                var item = button.closest(".pwr-person");
                if (item && item.parentNode) {
                    item.parentNode.replaceChild(renderPerson(updated, t), item);
                }
                showSecret(scope, updated, payload.password);
                toast(payload.message, "success");
            })
            .catch(function (error) {
                toast(errorMessage(error, t.genericError), "error");
                button.disabled = false;
                if (label && label.nodeType === 3) {
                    label.textContent = " " + t.reset;
                }
            });
    }

    window.EMSDelegate.on("click", "[data-pwr-reset]", function (event, button) {
        event.preventDefault();
        var scope = button.closest("[data-pwr-root]");
        var person = people[button.getAttribute("data-pwr-reset")];
        if (!scope || !person || button.disabled) {
            return;
        }
        var t = strings();
        var body = format(t.confirmBody, { name: person.full_name, username: person.username });
        var confirmed = window.EMSConfirm
            ? window.EMSConfirm.open({ title: t.confirmTitle, body: body, confirmLabel: t.confirmOk, danger: true })
            : Promise.resolve(false);
        confirmed.then(function (ok) {
            if (ok) {
                performReset(scope, button, person);
            }
        });
    });

    /* ── Kopyala / gizlət ─────────────────────────────────────────────── */
    function selectSecret(secret) {
        if (!window.getSelection || !document.createRange) {
            return;
        }
        var range = document.createRange();
        range.selectNodeContents(secret);
        var selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
    }

    window.EMSDelegate.on("click", "[data-pwr-copy]", function (event, button) {
        event.preventDefault();
        var scope = button.closest("[data-pwr-root]");
        var secret = scope && scope.querySelector("[data-pwr-secret]");
        var t = strings();
        if (!secret || !secret.textContent) {
            return;
        }
        if (window.navigator.clipboard && typeof window.navigator.clipboard.writeText === "function") {
            window.navigator.clipboard.writeText(secret.textContent).then(
                function () {
                    toast(t.copied, "success");
                },
                function () {
                    selectSecret(secret);
                    toast(t.copyFailed, "warning");
                }
            );
            return;
        }
        selectSecret(secret);
        toast(t.copyFailed, "warning");
    });

    window.EMSDelegate.on("click", "[data-pwr-done]", function (event, button) {
        event.preventDefault();
        clearSecret();
        var scope = button.closest("[data-pwr-root]");
        var input = scope && scope.querySelector("[data-pwr-query]");
        if (input) {
            input.value = "";
            input.focus();
        }
    });

    window.EMSReady.once("pwr-pagehide", function () {
        window.addEventListener("pagehide", clearSecret);
    });

    window.EMSReady(function () {
        // Panel (yenidən) göründü — əvvəlki paneldən qalmış parol taymeri varsa sıfırla.
        if (!root()) {
            clearSecret();
        }
    });
})(window, document);
