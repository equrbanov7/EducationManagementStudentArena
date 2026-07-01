/* Create-exam modal loading, binding, and submit handling. */
(function (ns) {
    "use strict";

    ns.register(function installCreateExamModal(ctx) {
        function createExamModalLoadingMarkup() {
            return '<div class="create-exam-modal-loading">Form yüklənir...</div>';
        }

        function buildCreateExamModalUrl(createExamUrl) {
            try {
                var url = new URL(createExamUrl, window.location.origin);
                url.searchParams.set("modal", "1");
                return url.pathname + url.search;
            } catch (error) {
                return createExamUrl + (createExamUrl.indexOf("?") === -1 ? "?modal=1" : "&modal=1");
            }
        }

        function initCreateExamAccessToggle(form) {
            if (!form) {
                return;
            }

            var isPublicCheckbox = form.querySelector('input[name="is_public"]');
            var accessBlock = form.querySelector("#createExamAccessRestrictions");
            if (!isPublicCheckbox || !accessBlock) {
                return;
            }

            function syncAccessBlock() {
                accessBlock.classList.toggle("is-hidden", isPublicCheckbox.checked);
            }

            syncAccessBlock();
            isPublicCheckbox.addEventListener("change", syncAccessBlock);
        }

        function initCreateExamTypePicker(form) {
            if (!form) {
                return;
            }

            var nativeSelect = form.querySelector('select[name="exam_type"]');
            var picker = form.querySelector("[data-create-exam-type-picker]");
            if (!nativeSelect || !picker) {
                return;
            }

            var typeOptions = picker.querySelectorAll(".js-create-exam-type-option");
            var paintCheckbox = form.querySelector('input[name="enable_paint"]');
            var paintLabel = paintCheckbox ? paintCheckbox.closest(".modal-check-label--paint") : null;
            var randomQuestionGroup = form.querySelector("[data-random-question-group], [data-test-random-question-group]");
            var randomQuestionInput = form.querySelector('input[name="random_question_count"]');

            function syncPaintAvailability(examType) {
                if (randomQuestionGroup) {
                    randomQuestionGroup.hidden = false;
                }
                if (randomQuestionInput) {
                    randomQuestionInput.disabled = false;
                }
                if (!paintCheckbox) {
                    return;
                }

                var isWritten = examType === "written";
                if (!isWritten) {
                    paintCheckbox.checked = false;
                }
                paintCheckbox.disabled = !isWritten;

                if (paintLabel) {
                    paintLabel.classList.toggle("is-disabled", !isWritten);
                }
            }

            function syncPickerFromSelect() {
                var selectedType = nativeSelect.value || "test";
                typeOptions.forEach(function (option) {
                    option.checked = option.value === selectedType;
                });
                syncPaintAvailability(selectedType);
            }

            typeOptions.forEach(function (option) {
                option.addEventListener("change", function () {
                    if (!option.checked) {
                        return;
                    }

                    nativeSelect.value = option.value;
                    syncPaintAvailability(option.value);
                    nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
                });
            });

            nativeSelect.addEventListener("change", syncPickerFromSelect);
            syncPickerFromSelect();
        }

        function showCreateExamTemplateInfo(form, templateSelect) {
            var infoPanel = form.querySelector("#modalSupervisionTemplateInfo");
            var infoTitle = form.querySelector("#modalSupervisionTemplateInfoTitle");
            var infoDesc = form.querySelector("#modalSupervisionTemplateInfoDesc");
            var infoFeatures = form.querySelector("#modalSupervisionTemplateInfoFeatures");
            if (!infoPanel || !templateSelect) {
                return;
            }

            var val = templateSelect.value;
            var templates =
                typeof window.MODAL_SUPERVISION_TPL_INFO === "object"
                    ? window.MODAL_SUPERVISION_TPL_INFO
                    : {};
            var borderColors = {
                custom: "#6c757d",
                light: "#28a745",
                medium: "#ffc107",
                strict: "#dc3545"
            };
            var tpl = templates[val];
            if (!tpl || val === "custom") {
                infoPanel.style.display = "none";
                return;
            }
            infoTitle.textContent = tpl.title || "";
            infoDesc.textContent = tpl.desc || "";
            infoFeatures.innerHTML = "";
            (tpl.features || []).forEach(function (f) {
                var li = document.createElement("li");
                li.textContent = f;
                infoFeatures.appendChild(li);
            });
            infoPanel.style.borderLeftColor = borderColors[val] || "#007bff";
            infoPanel.style.display = "block";
        }

        function initCreateExamSupervisionToggle(form) {
            if (!form) {
                return;
            }

            var enabledCheckbox = form.querySelector('input[name="supervision_enabled"]');
            var settingsBlock = form.querySelector("#modalSupervisionSettings");
            var templateSelect = form.querySelector('select[name="supervision_template"]');
            var customBlock = form.querySelector("#modalSupervisionCustomSettings");

            if (!enabledCheckbox || !settingsBlock) {
                return;
            }

            function syncSupervisionSettings() {
                if (enabledCheckbox.checked) {
                    settingsBlock.style.display = "block";
                    settingsBlock.removeAttribute("hidden");
                } else {
                    settingsBlock.style.display = "none";
                }
            }

            function syncSupervisionCustom() {
                if (!templateSelect || !customBlock) {
                    return;
                }
                customBlock.style.display = templateSelect.value === "custom" ? "block" : "none";
            }

            syncSupervisionSettings();
            enabledCheckbox.addEventListener("change", syncSupervisionSettings);
            enabledCheckbox.addEventListener("click", function () {
                setTimeout(syncSupervisionSettings, 0);
            });

            if (templateSelect) {
                syncSupervisionCustom();
                templateSelect.addEventListener("change", syncSupervisionCustom);
                templateSelect.addEventListener("change", function () {
                    showCreateExamTemplateInfo(form, templateSelect);
                });
                showCreateExamTemplateInfo(form, templateSelect);
            }

            if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.init === "function") {
                window.EMSBootstrapSelect.init(settingsBlock);
            }
        }

        function bindCreateExamModalForm() {
            if (!ctx.createExamModalBody) {
                return;
            }

            var closeInlineBtn = ctx.createExamModalBody.querySelector(".js-close-create-exam");
            if (closeInlineBtn) {
                closeInlineBtn.addEventListener("click", function () {
                    closeCreateExamModal(true);
                });
            }

            var form = ctx.createExamModalBody.querySelector("#createExamModalForm");
            if (!form) {
                return;
            }

            initCreateExamTypePicker(form);
            initCreateExamAccessToggle(form);
            initCreateExamSupervisionToggle(form);
            var groupSelector = ctx.initCreateExamSearchableSelect(form, {
                selectName: "allowed_groups",
                listSelector: "#createExamGroupsList",
                searchSelector: "#createExamGroupsSearch",
                counterSelector: "#createExamGroupsCount"
            });
            var userSelector = ctx.initCreateExamSearchableSelect(form, {
                selectName: "allowed_users",
                listSelector: "#createExamUsersList",
                searchSelector: "#createExamUsersSearch",
                counterSelector: "#createExamUsersCount"
            });
            ctx.initCreateExamGroupUserSelectionSync(form, groupSelector, userSelector);

            form.addEventListener("submit", async function (event) {
                event.preventDefault();
                if (ctx.createExamSubmitInFlight) {
                    return;
                }

                ctx.createExamSubmitInFlight = true;
                var submitBtn = form.querySelector('button[type="submit"]');
                var originalSubmitText = submitBtn ? submitBtn.innerHTML : "";
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.textContent = "Yaradılır...";
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
                    var redirectTarget = response.url || "";
                    if (response.ok && contentType.indexOf("application/json") !== -1) {
                        var data = await response.json();
                        if (data.success) {
                            closeCreateExamModal(true);
                            var nextUrl = new URL(ctx.profileBaseUrl, window.location.origin);
                            nextUrl.searchParams.set("section", "my-exams");
                            window.setTimeout(function () {
                                window.location.href = nextUrl.pathname + nextUrl.search;
                            }, 60);
                            return;
                        }
                    }

                    if (response.ok && response.redirected && redirectTarget) {
                        closeCreateExamModal(true);
                        var redirectedUrl = new URL(ctx.profileBaseUrl, window.location.origin);
                        redirectedUrl.searchParams.set("section", "my-exams");
                        window.setTimeout(function () {
                            window.location.href = redirectedUrl.pathname + redirectedUrl.search;
                        }, 60);
                        return;
                    }

                    if (contentType.indexOf("application/json") !== -1) {
                        var jsonError = await response.json();
                        if (jsonError.html) {
                            ctx.createExamModalBody.innerHTML = jsonError.html;
                            bindCreateExamModalForm();
                            return;
                        }
                    }

                    var html = await response.text();
                    ctx.createExamModalBody.innerHTML = html || '<div class="create-exam-modal-error">Form yenilənmədi. Yenidən cəhd edin.</div>';
                    bindCreateExamModalForm();
                } catch (error) {
                    if (ctx.createExamModalBody) {
                        ctx.createExamModalBody.innerHTML = '<div class="create-exam-modal-error">Xəta baş verdi. Yenidən cəhd edin.</div>';
                    }
                } finally {
                    ctx.createExamSubmitInFlight = false;
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalSubmitText;
                    }
                }
            });
        }

        async function openCreateExamModal(createExamUrl) {
            if (!createExamUrl || !ctx.createExamModal || !ctx.createExamModalBody) {
                return;
            }
            if (
                ctx.createExamModal.dataset.createExamLoading === "1" &&
                ctx.createExamModal.classList.contains("active")
            ) {
                return;
            }

            ctx.ensureModalRoot(ctx.createExamModal);
            ctx.createExamModal.classList.add("active");
            document.body.style.overflow = "hidden";
            ctx.createExamModalBody.innerHTML = createExamModalLoadingMarkup();

            var modalUrl = buildCreateExamModalUrl(createExamUrl);
            ctx.createExamModal.dataset.createExamUrl = modalUrl;
            var loadToken = String((Number(ctx.createExamModal.dataset.createExamToken) || 0) + 1);
            ctx.createExamModal.dataset.createExamToken = loadToken;
            ctx.createExamModal.dataset.createExamLoading = "1";

            try {
                var response = await fetch(modalUrl, {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });
                var html = await response.text();
                if (!response.ok) {
                    throw new Error("create exam modal load failed");
                }
                if (
                    ctx.createExamModal.dataset.createExamToken !== loadToken ||
                    !ctx.createExamModal.classList.contains("active")
                ) {
                    return;
                }
                ctx.createExamModalBody.innerHTML = html;
                bindCreateExamModalForm();
            } catch (error) {
                if (
                    ctx.createExamModal.dataset.createExamToken !== loadToken ||
                    !ctx.createExamModal.classList.contains("active")
                ) {
                    return;
                }
                ctx.createExamModalBody.innerHTML = '<div class="create-exam-modal-error">Form yüklənmədi. Yenidən cəhd edin.</div>';
            } finally {
                if (ctx.createExamModal.dataset.createExamToken === loadToken) {
                    ctx.createExamModal.dataset.createExamLoading = "0";
                }
            }
        }

        function closeCreateExamModal(resetContent) {
            if (!ctx.createExamModal) {
                return;
            }
            ctx.createExamModal.classList.remove("active");
            document.body.style.overflow = "";
            ctx.createExamModal.dataset.createExamToken =
                String((Number(ctx.createExamModal.dataset.createExamToken) || 0) + 1);
            ctx.createExamModal.dataset.createExamLoading = "0";
            if (resetContent && ctx.createExamModalBody) {
                ctx.createExamModalBody.innerHTML = createExamModalLoadingMarkup();
            }
        }

        ctx.openCreateExamModal = openCreateExamModal;
        ctx.closeCreateExamModal = closeCreateExamModal;

        if (ctx.createExamModal) {
            ctx.ensureModalRoot(ctx.createExamModal);
        }

        if (ctx.closeCreateExamModalBtn) {
            ctx.closeCreateExamModalBtn.addEventListener("click", function () {
                closeCreateExamModal(true);
            });
        }

        if (ctx.createExamModal) {
            ctx.createExamModal.addEventListener("click", function (event) {
                if (event.target === ctx.createExamModal) {
                    closeCreateExamModal(true);
                }
            });
        }

        window.openCreateExamModal = openCreateExamModal;
    });
})(window.EMSProfile = window.EMSProfile || {});
