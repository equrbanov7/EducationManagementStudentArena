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

        form.addEventListener("submit", async function (event) {
            event.preventDefault();

            if (ctx.submitInFlight) {
                return;
            }

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
