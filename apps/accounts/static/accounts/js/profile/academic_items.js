/* «Akademik fəaliyyət» idarəetməsi (profil redaktəsi bölməsi).
 *
 * AJAX-safe: bütün kliklər EMSDelegate ilə document üzərindədir, ona görə
 * bölmə swap olunsa da düymələr «ölmür». Server cavabı yenilənmiş siyahı
 * fraqmentidir (#academicItemsManagerList swap edilir) — i18n server tərəfdə.
 * Endpoint: #academicItemsManager[data-api-url] (accounts:academic_items_api).
 */
(function () {
    "use strict";

    function getManager() {
        return document.getElementById("academicItemsManager");
    }

    function getModal(id) {
        var element = document.getElementById(id);
        if (!element || !window.bootstrap || !window.bootstrap.Modal) {
            return null;
        }
        return { element: element, api: window.bootstrap.Modal.getOrCreateInstance(element) };
    }

    function setBusy(button, busy) {
        if (!button) {
            return;
        }
        button.disabled = busy;
        var spinner = button.querySelector(".spinner-border");
        if (spinner) {
            spinner.classList.toggle("d-none", !busy);
        }
    }

    function showError(regionId, message) {
        var region = document.getElementById(regionId);
        if (!region) {
            return;
        }
        if (message) {
            region.textContent = message;
            region.classList.remove("d-none");
        } else {
            region.textContent = "";
            region.classList.add("d-none");
        }
    }

    function errorMessageFrom(error, fallback) {
        if (error && error.payload && typeof error.payload === "object" && error.payload.error) {
            return String(error.payload.error);
        }
        return fallback;
    }

    function postAction(fields) {
        var manager = getManager();
        if (!manager || !manager.dataset.apiUrl || !window.EMSCore) {
            return Promise.reject(new Error("academic items manager not ready"));
        }
        var body = new URLSearchParams();
        Object.keys(fields).forEach(function (key) {
            body.append(key, fields[key] === null || fields[key] === undefined ? "" : String(fields[key]));
        });
        return window.EMSCore.fetchJSON(manager.dataset.apiUrl, { method: "POST", body: body });
    }

    function swapList(html) {
        var list = document.getElementById("academicItemsManagerList");
        if (list && typeof html === "string") {
            list.innerHTML = html;
            refreshListView();
        }
    }

    /* ── Axtarış + «Daha çox göstər» (çox qeyddə siyahı dağılmasın) ──────── */

    function getListHost() {
        return document.getElementById("academicItemsManagerList");
    }

    function itemMatches(item, query) {
        return !query || item.textContent.toLowerCase().indexOf(query) !== -1;
    }

    function refreshListView() {
        var host = getListHost();
        if (!host) {
            return;
        }
        var searchInput = document.getElementById("academicItemsSearch");
        var query = searchInput ? searchInput.value.trim().toLowerCase() : "";
        var limit = parseInt(host.dataset.collapseLimit || "5", 10);

        host.querySelectorAll(".academic-items-group").forEach(function (group) {
            var items = Array.prototype.slice.call(group.querySelectorAll(".academic-item"));
            var matched = items.filter(function (item) {
                var isMatch = itemMatches(item, query);
                item.hidden = !isMatch;
                return isMatch;
            });

            // Axtarış aktivkən collapse SÖNÜR — bütün uyğun nəticələr görünsün.
            var expanded = Boolean(query) || group.dataset.expanded === "1";
            var hiddenCount = 0;
            if (!expanded) {
                matched.forEach(function (item, index) {
                    if (index >= limit) {
                        item.hidden = true;
                        hiddenCount += 1;
                    }
                });
            }

            var noMatchNote = group.querySelector(".academic-items-nomatch");
            if (query && !matched.length && items.length) {
                if (!noMatchNote) {
                    noMatchNote = document.createElement("p");
                    noMatchNote.className = "academic-items-empty academic-items-nomatch";
                    noMatchNote.textContent = host.dataset.labelNoMatch || "";
                    group.appendChild(noMatchNote);
                }
                noMatchNote.hidden = false;
            } else if (noMatchNote) {
                noMatchNote.hidden = true;
            }

            var toggle = group.querySelector(".js-academic-items-toggle");
            var needsToggle = !query && (hiddenCount > 0 || (group.dataset.expanded === "1" && matched.length > limit));
            if (needsToggle) {
                if (!toggle) {
                    toggle = document.createElement("button");
                    toggle.type = "button";
                    toggle.className = "academic-items-toggle js-academic-items-toggle";
                    group.appendChild(toggle);
                }
                toggle.hidden = false;
                toggle.innerHTML = "";
                var icon = document.createElement("i");
                icon.className = group.dataset.expanded === "1" ? "fas fa-chevron-up" : "fas fa-chevron-down";
                toggle.appendChild(icon);
                toggle.appendChild(
                    document.createTextNode(
                        " " +
                            (group.dataset.expanded === "1"
                                ? host.dataset.labelShowLess || ""
                                : (host.dataset.labelShowMore || "") + " (" + hiddenCount + ")")
                    )
                );
            } else if (toggle) {
                toggle.hidden = true;
            }
        });
    }

    function fillItemForm(values) {
        var form = document.getElementById("academicItemForm");
        if (!form) {
            return;
        }
        form.elements.action.value = values.action;
        form.elements.item_id.value = values.itemId || "";
        form.elements.kind.value = values.kind || "";
        form.elements.title.value = values.title || "";
        form.elements.detail.value = values.detail || "";
        form.elements.year.value = values.year || "";
        form.elements.link.value = values.link || "";
        showError("academicItemFormError", "");
    }

    function setItemModalTitle(mode, kindLabel) {
        var modalElement = document.getElementById("academicItemModal");
        var heading = document.getElementById("academicItemModalTitle");
        if (!modalElement || !heading) {
            return;
        }
        var base = mode === "update" ? modalElement.dataset.labelEdit : modalElement.dataset.labelCreate;
        heading.textContent = kindLabel ? base + " — " + kindLabel : base;
    }

    window.EMSReady(function () {
        if (getListHost()) {
            refreshListView();
        }
    });

    window.EMSReady.once("accounts/profile/academic_items", function () {
        document.addEventListener("input", function (event) {
            if (event.target && event.target.id === "academicItemsSearch") {
                refreshListView();
            }
        });

        window.EMSDelegate.on("click", ".js-academic-items-toggle", function (event, button) {
            event.preventDefault();
            var group = button.closest(".academic-items-group");
            if (group) {
                group.dataset.expanded = group.dataset.expanded === "1" ? "" : "1";
                refreshListView();
            }
        });

        window.EMSDelegate.on("click", ".js-academic-item-add", function (event, button) {
            event.preventDefault();
            var modal = getModal("academicItemModal");
            if (!modal) {
                return;
            }
            fillItemForm({ action: "create", kind: button.dataset.kind });
            setItemModalTitle("create", button.dataset.kindLabel || "");
            modal.api.show();
        });

        window.EMSDelegate.on("click", ".js-academic-item-edit", function (event, button) {
            event.preventDefault();
            var modal = getModal("academicItemModal");
            if (!modal) {
                return;
            }
            fillItemForm({
                action: "update",
                itemId: button.dataset.itemId,
                kind: button.dataset.kind,
                title: button.dataset.title,
                detail: button.dataset.detail,
                year: button.dataset.year,
                link: button.dataset.link,
            });
            setItemModalTitle("update", button.dataset.kindLabel || "");
            modal.api.show();
        });

        window.EMSDelegate.on("click", ".js-academic-item-delete", function (event, button) {
            event.preventDefault();
            var modal = getModal("academicItemDeleteModal");
            if (!modal) {
                return;
            }
            var confirmButton = document.getElementById("academicItemDeleteConfirmBtn");
            var titleNode = document.getElementById("academicItemDeleteTitle");
            if (confirmButton) {
                confirmButton.dataset.itemId = button.dataset.itemId || "";
            }
            if (titleNode) {
                titleNode.textContent = button.dataset.title || "";
            }
            showError("academicItemDeleteError", "");
            modal.api.show();
        });

        window.EMSDelegate.on("submit", "#academicItemForm", function (event, form) {
            event.preventDefault();
            var modalElement = document.getElementById("academicItemModal");
            var submitButton = document.getElementById("academicItemSubmitBtn");
            var fallbackError = modalElement ? modalElement.dataset.labelError : "Error";
            showError("academicItemFormError", "");
            setBusy(submitButton, true);
            postAction({
                action: form.elements.action.value,
                item_id: form.elements.item_id.value,
                kind: form.elements.kind.value,
                title: form.elements.title.value,
                detail: form.elements.detail.value,
                year: form.elements.year.value,
                link: form.elements.link.value,
            })
                .then(function (payload) {
                    swapList(payload && payload.html);
                    var modal = getModal("academicItemModal");
                    if (modal) {
                        modal.api.hide();
                    }
                })
                .catch(function (error) {
                    showError("academicItemFormError", errorMessageFrom(error, fallbackError));
                })
                .finally(function () {
                    setBusy(submitButton, false);
                });
        });

        window.EMSDelegate.on("click", "#academicItemDeleteConfirmBtn", function (event, button) {
            event.preventDefault();
            var modalElement = document.getElementById("academicItemDeleteModal");
            var fallbackError = modalElement ? modalElement.dataset.labelError : "Error";
            showError("academicItemDeleteError", "");
            setBusy(button, true);
            postAction({ action: "delete", item_id: button.dataset.itemId })
                .then(function (payload) {
                    swapList(payload && payload.html);
                    var modal = getModal("academicItemDeleteModal");
                    if (modal) {
                        modal.api.hide();
                    }
                })
                .catch(function (error) {
                    showError("academicItemDeleteError", errorMessageFrom(error, fallbackError));
                })
                .finally(function () {
                    setBusy(button, false);
                });
        });
    });
})();
