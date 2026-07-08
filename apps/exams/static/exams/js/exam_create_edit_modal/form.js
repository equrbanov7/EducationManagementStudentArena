/* Modal form binding and AJAX load/submit orchestration. */
(function (ns, window) {
    "use strict";

    function bindModalForm(ctx) {
        var closeInlineBtn = ctx.modalBody.querySelector(".js-close-create-exam");
        if (closeInlineBtn) {
            closeInlineBtn.addEventListener("click", function () {
                ctx.bsModal.hide();
            });
        }

        var form = ctx.modalBody.querySelector("#createExamModalForm");
        if (!form) {
            return;
        }

        ns.toggles.initExamTypePicker(form);
        ns.toggles.initAccessToggle(form);
        ns.toggles.initSupervisionToggle(form);
        ns.toggles.initCategoryVisibility(form);

        if (ns.subjectSelect && typeof ns.subjectSelect.init === "function") {
            ns.subjectSelect.init(form);
        }

        // Initialize Bootstrap selects for dynamically loaded form content
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.init === "function") {
            window.EMSBootstrapSelect.init(form);
        }

        var groupSelector = ns.searchableSelect.initSearchableSelect(form, {
            selectName: "allowed_groups",
            listSelector: "#createExamGroupsList",
            searchSelector: "#createExamGroupsSearch",
            counterSelector: "#createExamGroupsCount"
        });

        var userSelector = ns.searchableSelect.initSearchableSelect(form, {
            selectName: "allowed_users",
            listSelector: "#createExamUsersList",
            searchSelector: "#createExamUsersSearch",
            counterSelector: "#createExamUsersCount"
        });

        if (groupSelector && userSelector) {
            ns.searchableSelect.initGroupUserSync(form, groupSelector, userSelector);
        }

        // 4-addımlı sehrbaz: naviqasiya + addım validasiyası + (server 400-dan
        // sonra) aydın xəta xülasəsi və ilk xətalı addıma keçid.
        if (window.EMSExamWizard && typeof window.EMSExamWizard.init === "function") {
            window.EMSExamWizard.init(form);
        }

        // ── Yaratma təsdiqi modalı ("İmtahan yarat"a basanda) ──
        // Seçilmiş qrupların adları + ümumi tələbə sayı göstərilir; Təsdiqlə →
        // imtahan yaradılır, Geri → redaktəyə qayıdır. Yalnız yaratma rejimində.
        var createConfirmed = false;

        function confirmFieldText(selector) {
            var el = form.querySelector(selector);
            if (!el) {
                return "";
            }
            if (el.tagName === "SELECT") {
                var opt = el.options[el.selectedIndex];
                return opt ? (opt.textContent || "").trim() : "";
            }
            return (el.value || "").trim();
        }

        function buildConfirmRows(totalText) {
            var dash = "—";
            var rows = [];
            rows.push([gettext("İmtahan adı"), confirmFieldText('[name="title"]') || dash]);

            var typeOption = form.querySelector(".js-create-exam-type-option:checked");
            var typeLabel = typeOption ? form.querySelector('label[for="' + typeOption.id + '"] .ew-tc-name') : null;
            rows.push([gettext("Tip"), (typeLabel ? typeLabel.textContent.trim() : "") || dash]);
            rows.push([gettext("Kateqoriya"), confirmFieldText('[name="exam_type_extended"]') || dash]);

            var subjectSel = form.querySelector("[data-exam-subject-native]");
            var subjectOpt = subjectSel ? subjectSel.querySelector("option[value]") : null;
            rows.push([gettext("Fənn"), (subjectOpt ? (subjectOpt.textContent || "").trim() : "") || dash]);

            rows.push([gettext("Başlama"), confirmFieldText('[name="start_datetime"]') || dash]);
            rows.push([gettext("Bitmə"), confirmFieldText('[name="end_datetime"]') || dash]);
            rows.push([gettext("Müddət (dəq)"), confirmFieldText('[name="total_duration_minutes"]') || dash]);
            rows.push([gettext("Sual sayı"), confirmFieldText('[name="random_question_count"]') || dash]);

            var supervision = form.querySelector('[name="supervision_enabled"]');
            rows.push([gettext("Nəzarət"), (supervision && supervision.checked) ? gettext("Aktiv") : gettext("Deaktiv")]);

            var isPublic = form.querySelector('[name="is_public"]');
            if (isPublic && isPublic.checked) {
                rows.push([gettext("Alıcılar"), gettext("Hamıya açıq")]);
                return rows;
            }
            var groupItems = groupSelector ? groupSelector.getSelectedItems() : [];
            var userCount = userSelector ? userSelector.getSelectedValues().length : 0;
            if (groupItems.length) {
                rows.push([gettext("Qruplar"), groupItems.map(function (i) { return i.text; }).join(", ")]);
            }
            if (userCount) {
                rows.push([gettext("Fərdi tələbələr"), String(userCount)]);
            }
            if (!groupItems.length && !userCount) {
                rows.push([gettext("Alıcılar"), gettext("Seçilməyib")]);
            }
            rows.push([gettext("Tələbə sayı (ümumi)"), totalText]);
            return rows;
        }

        function renderConfirmSummary(overlay, totalText) {
            var summary = overlay.querySelector("[data-cc-summary]");
            if (!summary) {
                return;
            }
            summary.innerHTML = "";
            buildConfirmRows(totalText).forEach(function (row) {
                var dt = document.createElement("dt");
                dt.textContent = row[0];
                var dd = document.createElement("dd");
                dd.textContent = row[1];
                summary.appendChild(dt);
                summary.appendChild(dd);
            });
        }

        function fetchConfirmTotal(overlay) {
            var isPublic = form.querySelector('[name="is_public"]');
            if (isPublic && isPublic.checked) {
                return;
            }
            var url = form.getAttribute("data-assigned-count-url");
            var groups = groupSelector ? groupSelector.getSelectedValues() : [];
            var users = userSelector ? userSelector.getSelectedValues() : [];
            if (!url || (!groups.length && !users.length)) {
                renderConfirmSummary(overlay, "0");
                return;
            }
            var q = url + (url.indexOf("?") === -1 ? "?" : "&") +
                "groups=" + encodeURIComponent(groups.join(",")) +
                "&users=" + encodeURIComponent(users.join(","));
            fetch(q, { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (r) { return r.ok ? r.json() : { total: 0 }; })
                .then(function (d) { renderConfirmSummary(overlay, String((d && d.total) || 0)); })
                .catch(function () { renderConfirmSummary(overlay, "—"); });
        }

        function showCreateConfirmOverlay() {
            var content = ctx.modalElement.querySelector(".modal-content");
            if (!content) {
                createConfirmed = true;
                if (form.requestSubmit) form.requestSubmit();
                return;
            }
            var existing = content.querySelector("[data-ew-create-confirm]");
            if (existing) {
                existing.parentNode.removeChild(existing);
            }
            var overlay = document.createElement("div");
            overlay.className = "ew-confirm";
            overlay.setAttribute("data-ew-create-confirm", "");
            overlay.innerHTML =
                '<div class="ew-confirm-box ew-confirm-box--review" role="alertdialog" aria-modal="true">' +
                '<span class="ew-confirm-ic ew-confirm-ic--ok"><i class="fas fa-clipboard-check" aria-hidden="true"></i></span>' +
                '<h4>' + gettext("İmtahanı təsdiqlə") + "</h4>" +
                "<p>" + gettext("İmtahan aşağıdakı məlumatlarla yaradılıb təyin olunacaq.") + "</p>" +
                '<dl class="ew-confirm-summary" data-cc-summary></dl>' +
                '<div class="ew-confirm-actions">' +
                '<button type="button" class="ew-btn ew-btn--ghost" data-cc-back>' + gettext("Geri") + "</button>" +
                '<button type="button" class="ew-btn ew-btn--primary" data-cc-ok>' + gettext("Təsdiqlə və yarat") + "</button>" +
                "</div></div>";
            content.appendChild(overlay);

            renderConfirmSummary(overlay, gettext("hesablanır…"));
            fetchConfirmTotal(overlay);

            function close() {
                if (overlay.parentNode) {
                    overlay.parentNode.removeChild(overlay);
                }
            }
            var backBtn = overlay.querySelector("[data-cc-back]");
            var okBtn = overlay.querySelector("[data-cc-ok]");
            if (backBtn) {
                backBtn.addEventListener("click", close);
            }
            if (okBtn) {
                okBtn.addEventListener("click", function () {
                    close();
                    createConfirmed = true;
                    if (form.requestSubmit) {
                        form.requestSubmit();
                    } else {
                        var sb = form.querySelector('button[type="submit"]');
                        if (sb) sb.click();
                    }
                });
            }
        }

        form.addEventListener("submit", async function (event) {
            event.preventDefault();

            if (ctx.submitInFlight) {
                return;
            }

            // Yaratma rejimində əvvəlcə təsdiq modalını göstər (redaktədə birbaşa saxla).
            if (form.getAttribute("data-editing") !== "1" && !createConfirmed) {
                showCreateConfirmOverlay();
                return;
            }
            createConfirmed = false;

            ctx.submitInFlight = true;
            var submitToken = ctx.modalLoadToken;
            var succeeded = false;

            var submitBtn = form.querySelector('button[type="submit"]');
            var submitOriginalHtml = submitBtn ? submitBtn.innerHTML : "";
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = ns.markup.getSavingMarkup(ctx);
            }

            try {
                var response = await fetch(form.getAttribute("action"), {
                    method: "POST",
                    body: new FormData(form),
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });

                var contentType = response.headers.get("content-type") || "";

                if (response.ok && contentType.indexOf("application/json") !== -1) {
                    var payload = await response.json();
                    if (payload.success) {
                        succeeded = true;
                        form.dataset.ewDirty = ""; // saxlanıldı — çıxışda soruşma
                        if (submitBtn) {
                            submitBtn.innerHTML = ns.markup.getSavedMarkup(ctx);
                        }
                        setTimeout(function () {
                            ctx.bsModal.hide();
                            window.location.reload();
                        }, 550);
                        return;
                    }
                }

                if (submitToken !== ctx.modalLoadToken) {
                    return;
                }

                if (contentType.indexOf("application/json") !== -1) {
                    var jsonPayload = await response.json();
                    if (jsonPayload.html) {
                        ctx.modalBody.innerHTML = jsonPayload.html;
                        bindModalForm(ctx);
                        var reform = ctx.modalBody.querySelector("#createExamModalForm");
                        if (reform) {
                            reform.dataset.ewDirty = "1"; // istifadəçi dəyişikliyi var
                        }
                        return;
                    }
                }

                var html = await response.text();
                if (submitToken !== ctx.modalLoadToken) {
                    return;
                }
                ctx.modalBody.innerHTML = html || ns.markup.getErrorMarkup(ctx);
                bindModalForm(ctx);
            } catch (error) {
                if (submitToken !== ctx.modalLoadToken) {
                    return;
                }
                ctx.modalBody.innerHTML = ns.markup.getErrorMarkup(ctx);
            } finally {
                ctx.submitInFlight = false;
                if (submitBtn && !succeeded) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = submitOriginalHtml;
                }
            }
        });

        // Dirty tracking — çıxışda yadda saxlanmamış dəyişiklik xəbərdarlığı.
        // Sintetik init hadisələri artıq keçib (bu listener ən sonda bağlanır).
        var markDirty = function () {
            form.dataset.ewDirty = "1";
        };
        form.addEventListener("input", markDirty);
        form.addEventListener("change", markDirty);
    }

    async function openExamModal(ctx, rawUrl, mode) {
        if (!rawUrl) {
            return;
        }

        ns.markup.applyModalMode(ctx, mode);
        ctx.modalBody.innerHTML = ns.markup.getLoadingMarkup(ctx);
        ctx.modalLoadToken += 1;
        var loadToken = ctx.modalLoadToken;
        ctx.modalElement.dataset.examModalLoading = "1";
        ctx.bsModal.show();

        var modalUrl = ns.markup.buildModalUrl(rawUrl);

        try {
            var response = await fetch(modalUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            });

            if (!response.ok) {
                throw new Error("request_failed");
            }

            var html = await response.text();
            if (loadToken !== ctx.modalLoadToken) {
                return;
            }
            ctx.modalBody.innerHTML = html;
            bindModalForm(ctx);
        } catch (error) {
            if (loadToken !== ctx.modalLoadToken) {
                return;
            }
            ctx.modalBody.innerHTML = ns.markup.getErrorMarkup(ctx);
        } finally {
            if (loadToken === ctx.modalLoadToken) {
                ctx.modalElement.dataset.examModalLoading = "0";
            }
        }
    }

    ns.form = {
        bindModalForm: bindModalForm,
        openExamModal: openExamModal
    };
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, window);
