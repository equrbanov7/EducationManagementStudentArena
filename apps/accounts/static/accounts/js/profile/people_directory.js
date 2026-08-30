/* «Müəllimlər» / «Tələbələr» kataloqu — BACKEND MÜQAVİLƏSİNİN İŞLƏK İSKELETİ.
 *
 * Bu fayl UI-ın son forması DEYİL — növbəti (UI) agent onu bəzəyəcək. Məqsədi:
 * backend müqaviləsinin (list / options / detail / action endpoint-ləri, sətir
 * açarları, icazə bayraqları) uçdan-uca işlədiyini göstərmək və UI agentinə
 * dəyişməz istinad nöqtəsi vermək.
 *
 * AJAX-safe: `EMSReady` + idempotent boot (panel SPA swap-ından sonra təkrar
 * qoşulmur). Bütün şəbəkə çağırışları `EMSCore.fetchJSON` üzərindəndir (CSRF).
 * Heç bir inline stil/script yoxdur — CSP `unsafe-inline` vermir (CLAUDE.md).
 */
(function () {
    "use strict";

    var DEBOUNCE_MS = 250;

    function textCell(row, value) {
        var cell = document.createElement("td");
        cell.textContent = value || "—";
        row.appendChild(cell);
        return cell;
    }

    function personCell(row, person) {
        var cell = document.createElement("td");
        cell.className = "people__cell-person";

        var avatar = document.createElement("span");
        avatar.className = "people__avatar";
        if (person.avatar_url) {
            var img = document.createElement("img");
            img.src = person.avatar_url;
            img.alt = "";
            img.loading = "lazy";
            avatar.appendChild(img);
        } else {
            // Şəkil FAYLLARI köhnə sistemdən köçmür — baş hərflər fallback-dir.
            avatar.classList.add("people__avatar--initials");
            avatar.textContent = person.initials || "?";
        }

        var name = document.createElement("button");
        name.type = "button";
        name.className = "people__name";
        name.dataset.peopleOpen = person.id;
        name.textContent = [person.full_name, person.patronymic].filter(Boolean).join(" ");

        var username = document.createElement("span");
        username.className = "people__username";
        username.textContent = person.username;

        cell.appendChild(avatar);
        var stack = document.createElement("span");
        stack.className = "people__name-stack";
        stack.appendChild(name);
        stack.appendChild(username);
        cell.appendChild(stack);
        row.appendChild(cell);
    }

    function actionsCell(row, person, flags) {
        var cell = document.createElement("td");
        cell.className = "people__cell-actions";
        var buttons = [];
        if (flags.canManageStatus && person.status === "active") {
            buttons.push(["block", "Dayandır"]);
        }
        if (flags.canManageStatus && person.status === "blocked") {
            buttons.push(["unblock", "Bərpa et"]);
        }
        if (flags.canManageTeacherRole && person.kind === "teacher") {
            buttons.push(["revoke_teacher", "Müəllim statusunu çıxar"]);
        }
        buttons.forEach(function (pair) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "people__action";
            button.dataset.peopleAction = pair[0];
            button.dataset.peopleTarget = person.id;
            button.textContent = pair[1];
            cell.appendChild(button);
        });
        row.appendChild(cell);
    }

    function boot() {
        var roots = document.querySelectorAll("[data-people-root]");
        Array.prototype.forEach.call(roots, function (root) {
            if (root.dataset.peopleInit === "1") {
                return;
            }
            root.dataset.peopleInit = "1";
            setup(root);
        });
    }

    function setup(root) {
        var kind = root.dataset.kind;
        var urls = {
            list: root.dataset.listUrl,
            options: root.dataset.optionsUrl,
            action: root.dataset.actionUrl,
            detail: root.dataset.detailUrlTemplate,
        };
        var flags = {
            canViewContacts: root.dataset.canViewContacts === "1",
            canViewDemographics: root.dataset.canViewDemographics === "1",
            canManageStatus: root.dataset.canManageStatus === "1",
            canManageTeacherRole: root.dataset.canManageTeacherRole === "1"
        };
        var form = root.querySelector("[data-people-filters]");
        var tbody = root.querySelector("[data-people-rows]");
        var empty = root.querySelector("[data-people-empty]");
        var pageInfo = root.querySelector("[data-people-page-info]");
        var coverage = root.querySelector("[data-people-coverage]");
        var state = { page: 1, total: 0, numPages: 1 };
        var timer = null;

        function params() {
            var data = new URLSearchParams();
            if (form) {
                Array.prototype.forEach.call(form.elements, function (el) {
                    if (!el.name) {
                        return;
                    }
                    if (el.type === "checkbox") {
                        if (el.checked) {
                            data.set(el.name, el.value);
                        }
                        return;
                    }
                    if (el.value) {
                        data.set(el.name, el.value);
                    }
                });
            }
            data.set("page", String(state.page));
            return data;
        }

        /* Analitika ilə EYNİ filtr dəsti — `page` XARİC (qrafiklər səhifədən
         * asılı deyil). Sətri `dataset`-ə yazırıq ki, analitika modulu skript
         * sırasından ASILI OLMADAN son vəziyyəti oxuya bilsin, sonra hadisə
         * göndəririk (o, artıq qoşulubsa dərhal yenilənir). */
        function publishFilters() {
            var data = params();
            data.delete("page");
            var query = data.toString();
            if (root.dataset.peopleFilterQuery === query) {
                return;
            }
            root.dataset.peopleFilterQuery = query;
            root.dispatchEvent(new CustomEvent("people:filters", { detail: { query: query } }));
        }

        function fillSelect(select, options) {
            if (!select) {
                return;
            }
            var current = select.value;
            while (select.options.length > 1) {
                select.remove(1);
            }
            (options || []).forEach(function (option) {
                var node = document.createElement("option");
                node.value = option.id;
                node.textContent = option.text;
                select.appendChild(node);
            });
            select.value = current;
        }

        function loadOptions() {
            window.EMSCore.fetchJSON(urls.options + "?" + params().toString())
                .then(function (payload) {
                    if (!payload || !payload.has_access) {
                        return;
                    }
                    Array.prototype.forEach.call(
                        root.querySelectorAll("[data-people-option]"),
                        function (select) {
                            fillSelect(select, payload[select.dataset.peopleOption]);
                        }
                    );
                    if (coverage && payload.demographics_coverage) {
                        var cov = payload.demographics_coverage;
                        coverage.textContent = cov.total
                            ? "Demoqrafiya: cins " +
                              cov.gender_known +
                              "/" +
                              cov.total +
                              ", doğum tarixi " +
                              cov.birth_date_known +
                              "/" +
                              cov.total
                            : "";
                    }
                })
                .catch(function () {
                    /* açılışlar boş qalır — cədvəl yenə işləyir */
                });
        }

        function render(payload) {
            tbody.textContent = "";
            (payload.results || []).forEach(function (person) {
                var row = document.createElement("tr");
                row.dataset.peopleRow = person.id;
                personCell(row, person);
                if (kind === "teachers") {
                    textCell(row, person.title || person.role_label);
                    textCell(row, person.kafedra_name || person.unit_name);
                } else {
                    textCell(row, person.group_name);
                    textCell(row, person.program_label || person.program_name);
                }
                textCell(row, person.faculty_name);
                if (flags.canViewContacts) {
                    textCell(row, [person.phone, person.email].filter(Boolean).join(" · "));
                }
                if (flags.canViewDemographics) {
                    var demo = [];
                    if (person.gender && person.gender !== "unspecified") {
                        demo.push(person.gender === "male" ? "Kişi" : "Qadın");
                    }
                    if (person.age !== null && person.age !== undefined) {
                        demo.push(person.age + " yaş");
                    }
                    textCell(row, demo.join(", "));
                }
                textCell(row, person.status);
                if (flags.canManageStatus || flags.canManageTeacherRole) {
                    actionsCell(row, person, flags);
                }
                tbody.appendChild(row);
            });
            state.total = payload.total || 0;
            state.numPages = payload.num_pages || 1;
            state.page = payload.page || 1;
            if (empty) {
                empty.hidden = state.total > 0;
            }
            if (pageInfo) {
                pageInfo.textContent = state.page + " / " + state.numPages + " (" + state.total + ")";
            }
        }

        function load() {
            publishFilters();
            window.EMSCore.fetchJSON(urls.list + "?" + params().toString())
                .then(function (payload) {
                    if (!payload || !payload.has_access) {
                        tbody.textContent = "";
                        if (empty) {
                            empty.hidden = false;
                        }
                        return;
                    }
                    render(payload);
                })
                .catch(function () {
                    tbody.textContent = "";
                });
        }

        function reload(resetPage) {
            if (resetPage) {
                state.page = 1;
            }
            window.clearTimeout(timer);
            timer = window.setTimeout(load, DEBOUNCE_MS);
        }

        if (form) {
            form.addEventListener("input", function () {
                reload(true);
            });
            form.addEventListener("change", function (event) {
                if (event.target && event.target.name === "faculty") {
                    loadOptions();
                }
                reload(true);
            });
            form.addEventListener("submit", function (event) {
                event.preventDefault();
                reload(true);
            });
            form.addEventListener("reset", function () {
                window.setTimeout(function () {
                    reload(true);
                }, 0);
            });
        }

        var prev = root.querySelector("[data-people-prev]");
        var next = root.querySelector("[data-people-next]");
        if (prev) {
            prev.addEventListener("click", function () {
                if (state.page > 1) {
                    state.page -= 1;
                    load();
                }
            });
        }
        if (next) {
            next.addEventListener("click", function () {
                if (state.page < state.numPages) {
                    state.page += 1;
                    load();
                }
            });
        }

        root.addEventListener("click", function (event) {
            var opener = event.target.closest("[data-people-open]");
            if (opener) {
                openDetail(root, urls, opener.dataset.peopleOpen);
                return;
            }
            var action = event.target.closest("[data-people-action]");
            if (action) {
                runAction(root, urls, action.dataset.peopleAction, action.dataset.peopleTarget, load);
            }
        });

        loadOptions();
        load();
    }

    function openDetail(root, urls, userId) {
        var modal = root.querySelector("[data-people-detail-modal]");
        var body = root.querySelector("[data-people-detail-body]");
        if (!modal || !body) {
            return;
        }
        window.EMSCore.fetchJSON(urls.detail.replace(/0\/$/, userId + "/"))
            .then(function (payload) {
                if (!payload || !payload.has_access) {
                    return;
                }
                var person = payload.person;
                body.textContent = "";
                var title = document.createElement("h3");
                title.textContent = [person.full_name, person.patronymic].filter(Boolean).join(" ");
                body.appendChild(title);
                var link = document.createElement("a");
                link.href = person.profile_url;
                link.textContent = "Profil səhifəsi";
                body.appendChild(link);
                modal.hidden = false;
                body.focus();
            })
            .catch(function () {
                /* səssiz — sətir cədvəldə qalır */
            });
        var close = root.querySelector("[data-people-detail-close]");
        if (close && !close.dataset.bound) {
            close.dataset.bound = "1";
            close.addEventListener("click", function () {
                modal.hidden = true;
            });
        }
    }

    function runAction(root, urls, action, userId, onDone) {
        var minLength = parseInt(root.dataset.minReasonLength || "3", 10);
        var destructive = action === "block" || action === "revoke_teacher";
        var reason = "";
        if (destructive) {
            reason = window.prompt("Səbəb (ən azı " + minLength + " simvol):") || "";
            if (reason.trim().length < minLength) {
                return;
            }
        }
        window.EMSCore.fetchJSON(urls.action, {
            method: "POST",
            data: { action: action, user_id: userId, reason: reason },
        })
            .then(function () {
                onDone();
            })
            .catch(function (error) {
                var message = (error && error.payload && error.payload.message) || "Əməliyyat alınmadı.";
                window.alert(message);
            });
    }

    if (window.EMSReady) {
        window.EMSReady(boot);
    } else {
        document.addEventListener("DOMContentLoaded", boot);
    }
})();
