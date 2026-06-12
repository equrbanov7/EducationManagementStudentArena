/**
 * "View as" seçim paneli — istifadəçi axtarışı və keçid.
 *
 * AJAX-safe pattern: bütün hadisələr EMSDelegate ilə document səviyyəsində
 * bağlanır (profil bölmələri fragment swap olunsa belə "ölü düymə" yaranmır).
 * Performans: axtarış 300ms debounce + AbortController ilə; nəticələr
 * səhifələnmiş gəlir (has_more → "Daha çox").
 */
(function () {
    "use strict";

    var DEBOUNCE_MS = 300;
    var state = {
        page: 1,
        hasMore: false,
        controller: null,
        debounceTimer: null,
        appending: false
    };

    function root() {
        return document.getElementById("viewAsLauncher");
    }

    function el(id) {
        return document.getElementById(id);
    }

    function escapeHtml(value) {
        var div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }

    function statusHtml(text) {
        return '<div class="view-as-dropdown__status">' + escapeHtml(text) + "</div>";
    }

    function selectedOrg() {
        var orgSelect = el("viewAsOrgSelect");
        return orgSelect ? orgSelect.value : "";
    }

    function isSuperadmin(launcher) {
        return launcher.getAttribute("data-is-superadmin") === "1";
    }

    function renderResults(launcher, items, append) {
        var box = el("viewAsResults");
        if (!box) return;

        var html = "";
        items.forEach(function (item) {
            var roles = (item.roles || [])
                .map(function (role) {
                    return '<span class="view-as-result__role">' + escapeHtml(role) + "</span>";
                })
                .join("");
            html +=
                '<button type="button" class="view-as-result" role="option" data-user-id="' +
                escapeHtml(item.id) +
                '">' +
                '<img class="view-as-result__avatar" src="' + escapeHtml(item.avatar_url) + '" alt="" loading="lazy">' +
                '<span class="view-as-result__body">' +
                '<span class="view-as-result__name">' + escapeHtml(item.name) + "</span>" +
                '<span class="view-as-result__meta">@' + escapeHtml(item.username) +
                (item.email ? " · " + escapeHtml(item.email) : "") + "</span>" +
                "</span>" +
                '<span class="view-as-result__roles">' + roles + "</span>" +
                '<i class="fas fa-chevron-right view-as-result__go" aria-hidden="true"></i>' +
                "</button>";
        });

        if (append) {
            var oldMore = box.querySelector(".view-as-dropdown__more");
            if (oldMore) oldMore.remove();
            box.insertAdjacentHTML("beforeend", html);
        } else {
            box.innerHTML = items.length ? html : statusHtml(launcher.getAttribute("data-text-no-results"));
        }

        if (state.hasMore) {
            box.insertAdjacentHTML(
                "beforeend",
                '<button type="button" class="view-as-dropdown__more" id="viewAsLoadMore">' +
                    escapeHtml(launcher.getAttribute("data-text-load-more")) +
                    "</button>"
            );
        }
    }

    function fetchUsers(launcher, options) {
        options = options || {};
        var box = el("viewAsResults");
        var searchInput = el("viewAsUserSearch");
        var roleSelect = el("viewAsRoleFilter");
        if (!box) return;

        if (isSuperadmin(launcher) && !selectedOrg()) {
            box.innerHTML = "";
            return;
        }

        if (state.controller) state.controller.abort();
        state.controller = new AbortController();
        state.page = options.append ? state.page + 1 : 1;
        state.appending = Boolean(options.append);

        if (!options.append) {
            box.innerHTML = statusHtml(launcher.getAttribute("data-text-loading"));
        }
        box.setAttribute("aria-busy", "true");

        var params = new URLSearchParams({
            type: "users",
            q: searchInput ? searchInput.value.trim() : "",
            role: roleSelect ? roleSelect.value : "",
            page: String(state.page)
        });
        if (isSuperadmin(launcher)) params.set("org", selectedOrg());

        fetch(launcher.getAttribute("data-search-url") + "?" + params.toString(), {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            signal: state.controller.signal,
            credentials: "same-origin"
        })
            .then(function (response) {
                if (!response.ok) throw new Error("HTTP " + response.status);
                return response.json();
            })
            .then(function (data) {
                state.hasMore = Boolean(data.has_more);
                renderResults(launcher, data.results || [], state.appending);
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") return;
                box.innerHTML = statusHtml(launcher.getAttribute("data-text-error"));
            })
            .finally(function () {
                box.setAttribute("aria-busy", "false");
            });
    }

    function loadOrganizations(launcher) {
        var orgSelect = el("viewAsOrgSelect");
        if (!orgSelect || orgSelect.dataset.loaded === "1") return;

        fetch(launcher.getAttribute("data-search-url") + "?type=orgs", {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin"
        })
            .then(function (response) {
                if (!response.ok) throw new Error("HTTP " + response.status);
                return response.json();
            })
            .then(function (data) {
                (data.results || []).forEach(function (org) {
                    var option = document.createElement("option");
                    option.value = org.id;
                    option.textContent = org.name;
                    orgSelect.appendChild(option);
                });
                orgSelect.dataset.loaded = "1";
            })
            .catch(function () {
                /* orq siyahısı yüklənməsə select boş qalır — kritik deyil */
            });
    }

    function toggleDropdown(open) {
        var launcher = root();
        if (!launcher) return;
        var dropdown = el("viewAsDropdown");
        var toggle = el("viewAsToggle");
        if (!dropdown || !toggle) return;

        var willOpen = typeof open === "boolean" ? open : dropdown.hidden;
        dropdown.hidden = !willOpen;
        toggle.setAttribute("aria-expanded", willOpen ? "true" : "false");

        if (willOpen) {
            if (isSuperadmin(launcher)) {
                loadOrganizations(launcher);
            } else {
                fetchUsers(launcher);
            }
            var searchInput = el("viewAsUserSearch");
            if (searchInput) searchInput.focus();
        }
    }

    window.EMSDelegate.on("click", "#viewAsToggle", function () {
        toggleDropdown();
    });

    // Kənara klik → bağla.
    document.addEventListener("click", function (event) {
        var launcher = root();
        var dropdown = el("viewAsDropdown");
        if (!launcher || !dropdown || dropdown.hidden) return;
        if (!launcher.contains(event.target)) toggleDropdown(false);
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") toggleDropdown(false);
    });

    window.EMSDelegate.on("input", "#viewAsUserSearch", function () {
        var launcher = root();
        if (!launcher) return;
        clearTimeout(state.debounceTimer);
        state.debounceTimer = setTimeout(function () {
            fetchUsers(launcher);
        }, DEBOUNCE_MS);
    });

    window.EMSDelegate.on("change", "#viewAsRoleFilter", function () {
        var launcher = root();
        if (launcher) fetchUsers(launcher);
    });

    window.EMSDelegate.on("change", "#viewAsOrgSelect", function () {
        var launcher = root();
        if (launcher) fetchUsers(launcher);
    });

    window.EMSDelegate.on("click", "#viewAsLoadMore", function () {
        var launcher = root();
        if (launcher) fetchUsers(launcher, { append: true });
    });

    // Nəticəyə klik → gizli formu doldur və POST et (CSRF formdadır).
    window.EMSDelegate.on("click", ".view-as-result", function (event, button) {
        var launcher = root();
        var form = el("viewAsStartForm");
        var userField = el("viewAsStartUserId");
        var orgField = el("viewAsStartOrgId");
        if (!launcher || !form || !userField) return;

        userField.value = button.getAttribute("data-user-id") || "";
        if (orgField) orgField.value = isSuperadmin(launcher) ? selectedOrg() : "";
        if (userField.value) form.submit();
    });
})();
