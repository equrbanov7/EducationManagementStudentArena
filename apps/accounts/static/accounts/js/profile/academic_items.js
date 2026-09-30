/* «Akademik fəaliyyət» idarəetməsi (profil redaktəsi bölməsi).
 *
 * AJAX-safe: bütün kliklər EMSDelegate ilə document üzərindədir, ona görə
 * bölmə swap olunsa da düymələr «ölmür». Server cavabı yenilənmiş siyahı
 * fraqmentidir (#academicItemsManagerList swap edilir) — i18n server tərəfdə.
 * Endpoint: #academicItemsManager[data-api-url] (accounts:academic_items_api).
 */
(function () {
    "use strict";

    // Tolerant axtarış (EMSSearch: az↔en hərfləri, «234king» → «234 K ing»).
    // «İ».toLowerCase() = «i» + U+0307 (birləşən nöqtə) — mətndən atılır.
    function searchMatcher(query) {
        var q = String(query || "").trim();
        var m = window.EMSSearch ? window.EMSSearch.matcher(q) : null;
        var low = q.toLowerCase();
        return function (text) {
            var t = String(text || "").replace(/\u0307/g, "");
            return m ? m(t) : !low || t.toLowerCase().indexOf(low) !== -1;
        };
    }

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

    /* `fields` — obyekt (urlencoded) və ya hazır FormData (multipart: fayl qoşması). */
    function postAction(fields) {
        var manager = getManager();
        if (!manager || !manager.dataset.apiUrl || !window.EMSCore) {
            return Promise.reject(new Error("academic items manager not ready"));
        }
        var body = fields;
        if (!(fields instanceof window.FormData)) {
            body = new URLSearchParams();
            Object.keys(fields).forEach(function (key) {
                body.append(key, fields[key] === null || fields[key] === undefined ? "" : String(fields[key]));
            });
        }
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

    function itemMatches(item, match) {
        return match(item.textContent);
    }

    function refreshListView() {
        var host = getListHost();
        if (!host) {
            return;
        }
        var searchInput = document.getElementById("academicItemsSearch");
        var query = searchInput ? searchInput.value.trim() : "";
        var match = searchMatcher(query);
        var limit = parseInt(host.dataset.collapseLimit || "5", 10);
        // Axtarış zamanı «Boş bölmələr» çipləri gizlənir (CSS: .is-searching).
        host.classList.toggle("is-searching", Boolean(query));

        host.querySelectorAll(".academic-items-group").forEach(function (group) {
            var items = Array.prototype.slice.call(group.querySelectorAll(".academic-item"));
            var matched = items.filter(function (item) {
                var isMatch = itemMatches(item, match);
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
                // Ekran oxuyucusu üçün açıq/bağlı vəziyyət — düymə qeydlərin
                // qalanını göstərib gizlədir, yalnız mətn dəyişməsi azdır.
                toggle.setAttribute("aria-expanded", group.dataset.expanded === "1" ? "true" : "false");
                toggle.innerHTML = "";
                var icon = document.createElement("i");
                icon.className = group.dataset.expanded === "1" ? "fas fa-chevron-up" : "fas fa-chevron-down";
                icon.setAttribute("aria-hidden", "true");
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

    /* ── Fayl qoşması (2026-10-01): bir qeydə bir PDF/şəkil ─────────────── */

    function attachNodes() {
        var field = document.getElementById("academicItemAttachmentField");
        if (!field) {
            return null;
        }
        return {
            field: field,
            current: field.querySelector("[data-attach-current]"),
            link: field.querySelector("[data-attach-current-link]"),
            thumb: field.querySelector("[data-attach-current-thumb]"),
            icon: field.querySelector("[data-attach-current-icon]"),
            name: field.querySelector("[data-attach-current-name]"),
            removed: field.querySelector("[data-attach-removed]"),
            input: field.querySelector("[data-attach-input]"),
            hint: field.querySelector("[data-attach-hint]"),
            pickLabel: field.querySelector("[data-attach-pick-label]"),
            removeFlag: field.querySelector("input[name=remove_attachment]"),
        };
    }

    function modalLabel(key) {
        var modalElement = document.getElementById("academicItemModal");
        return (modalElement && modalElement.dataset[key]) || "";
    }

    function resetAttachment(values) {
        var nodes = attachNodes();
        if (!nodes) {
            return;
        }
        var allowed = values.allowsAttachment === "1";
        var hasCurrent = allowed && Boolean(values.attachmentUrl);
        nodes.field.hidden = !allowed;
        if (nodes.input) {
            nodes.input.value = "";
            nodes.input.disabled = !allowed;
        }
        if (nodes.removeFlag) {
            nodes.removeFlag.value = "";
        }
        if (nodes.hint) {
            nodes.hint.textContent = nodes.hint.dataset.labelEmpty || "";
            nodes.hint.classList.remove("is-selected");
        }
        if (nodes.removed) {
            nodes.removed.hidden = true;
        }
        if (nodes.current) {
            nodes.current.hidden = !hasCurrent;
        }
        if (hasCurrent) {
            nodes.link.href = values.attachmentUrl;
            nodes.name.textContent = values.attachmentName || "";
            var isImage = values.attachmentPdf !== "1";
            if (nodes.thumb) {
                if (isImage && values.attachmentThumb) {
                    nodes.thumb.src = values.attachmentThumb;
                    nodes.thumb.hidden = false;
                } else {
                    nodes.thumb.removeAttribute("src");
                    nodes.thumb.hidden = true;
                }
            }
            if (nodes.icon) {
                nodes.icon.hidden = isImage && Boolean(values.attachmentThumb);
                nodes.icon.className = isImage
                    ? "fas fa-image academic-file__icon"
                    : "fas fa-file-pdf academic-file__icon academic-file__icon--pdf";
            }
        }
        if (nodes.pickLabel) {
            nodes.pickLabel.textContent = hasCurrent ? modalLabel("labelChange") : modalLabel("labelPick");
        }
    }

    function formatSize(bytes) {
        if (bytes >= 1048576) {
            return (bytes / 1048576).toFixed(1) + " MB";
        }
        return Math.max(1, Math.round(bytes / 1024)) + " KB";
    }

    function attachmentProblem(file) {
        var maxBytes = parseInt(modalLabel("maxBytes") || "0", 10);
        if (!/\.(pdf|jpe?g|png|webp)$/i.test(file.name || "")) {
            return modalLabel("labelBadType");
        }
        if (maxBytes && file.size > maxBytes) {
            return modalLabel("labelTooBig");
        }
        return "";
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
        // Növə görə placeholder-lər (məs. «Nəşriyyat, ISBN…» kitab üçün).
        form.elements.title.placeholder = values.titleHint || modalLabel("labelTitleHint");
        form.elements.detail.placeholder = values.detailHint || modalLabel("labelDetailHint");
        resetAttachment(values);
        showError("academicItemFormError", "");
    }

    function valuesFrom(button, extra) {
        var data = button.dataset;
        var values = {
            kind: data.kind,
            titleHint: data.titleHint,
            detailHint: data.detailHint,
            allowsAttachment: data.allowsAttachment,
            attachmentUrl: data.attachmentUrl,
            attachmentName: data.attachmentName,
            attachmentThumb: data.attachmentThumb,
            attachmentPdf: data.attachmentPdf,
        };
        Object.keys(extra).forEach(function (key) {
            values[key] = extra[key];
        });
        return values;
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
            fillItemForm(valuesFrom(button, { action: "create", attachmentUrl: "" }));
            setItemModalTitle("create", button.dataset.kindLabel || "");
            modal.api.show();
        });

        window.EMSDelegate.on("click", ".js-academic-item-edit", function (event, button) {
            event.preventDefault();
            var modal = getModal("academicItemModal");
            if (!modal) {
                return;
            }
            fillItemForm(
                valuesFrom(button, {
                    action: "update",
                    itemId: button.dataset.itemId,
                    title: button.dataset.title,
                    detail: button.dataset.detail,
                    year: button.dataset.year,
                    link: button.dataset.link,
                })
            );
            setItemModalTitle("update", button.dataset.kindLabel || "");
            modal.api.show();
        });

        window.EMSDelegate.on("change", "#academicItemAttachmentField [data-attach-input]", function (event, input) {
            var nodes = attachNodes();
            var file = input.files && input.files.length ? input.files[0] : null;
            if (!nodes || !nodes.hint) {
                return;
            }
            var problem = file ? attachmentProblem(file) : "";
            showError("academicItemFormError", problem);
            if (!file || problem) {
                input.value = "";
                nodes.hint.textContent = nodes.hint.dataset.labelEmpty || "";
                nodes.hint.classList.remove("is-selected");
                return;
            }
            nodes.hint.textContent = file.name + " · " + formatSize(file.size);
            nodes.hint.classList.add("is-selected");
            if (nodes.pickLabel) {
                nodes.pickLabel.textContent = modalLabel("labelChange");
            }
        });

        window.EMSDelegate.on("click", "#academicItemAttachmentField [data-attach-remove]", function (event) {
            event.preventDefault();
            var nodes = attachNodes();
            if (!nodes) {
                return;
            }
            nodes.removeFlag.value = "1";
            nodes.current.hidden = true;
            nodes.removed.hidden = false;
            if (nodes.pickLabel) {
                nodes.pickLabel.textContent = modalLabel("labelPick");
            }
        });

        window.EMSDelegate.on("click", "#academicItemAttachmentField [data-attach-undo]", function (event) {
            event.preventDefault();
            var nodes = attachNodes();
            if (!nodes) {
                return;
            }
            nodes.removeFlag.value = "";
            nodes.current.hidden = false;
            nodes.removed.hidden = true;
            if (nodes.pickLabel) {
                nodes.pickLabel.textContent = modalLabel("labelChange");
            }
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
            // multipart: FormData formanın bütün sahələrini (fayl + remove_attachment) daşıyır.
            var body = new window.FormData(form);
            var nodes = attachNodes();
            var file = nodes && nodes.input && nodes.input.files && nodes.input.files[0];
            if (!file || (nodes && nodes.field.hidden)) {
                body.delete("attachment");
            } else if (attachmentProblem(file)) {
                showError("academicItemFormError", attachmentProblem(file));
                return;
            }
            setBusy(submitButton, true);
            postAction(body)
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
