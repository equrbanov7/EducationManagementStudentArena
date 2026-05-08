(function () {
    "use strict";

    var i18n = window.AI_QUESTION_BANK_I18N || {};

    function t(key, fallback) {
        return i18n[key] || fallback;
    }

    function getCsrfToken() {
        var tokenInput = document.querySelector("[name=csrfmiddlewaretoken]");
        if (tokenInput && tokenInput.value) return tokenInput.value;

        var cookieMatch = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return cookieMatch ? decodeURIComponent(cookieMatch[1]) : "";
    }

    function setStatus(panel, message, state) {
        if (!panel || typeof panel.querySelector !== "function") return;
        var status = panel.querySelector("[data-ai-question-status]");
        if (!status) return;
        status.textContent = message || "";
        status.classList.remove("is-error", "is-success", "is-loading");
        if (state) status.classList.add("is-" + state);
    }

    function setBusy(panel, busy) {
        var button = panel.querySelector("[data-ai-question-submit]");
        if (!button) return;

        if (!button.dataset.defaultLabel) {
            button.dataset.defaultLabel = button.innerHTML;
        }

        button.disabled = busy;
        button.innerHTML = busy
            ? '<i class="fas fa-circle-notch fa-spin"></i> ' + t("generating", "Yaradılır...")
            : button.dataset.defaultLabel;
    }

    function appendField(formData, field) {
        if (!field.name || field.disabled) return;

        var type = (field.type || "").toLowerCase();
        if (type === "file") {
            if (field.files && field.files[0]) {
                formData.append(field.name, field.files[0]);
            }
            return;
        }

        if ((type === "checkbox" || type === "radio") && !field.checked) {
            return;
        }

        formData.append(field.name, field.value || "");
    }

    function buildFormData(panel) {
        var formData = new FormData();
        panel.querySelectorAll("input, textarea, select").forEach(function (field) {
            appendField(formData, field);
        });

        var block = panel.closest(".block-item");
        if (block && !formData.has("block_name")) {
            var blockNameInput = block.querySelector(".block-name-input");
            if (blockNameInput) {
                formData.append("block_name", blockNameInput.value || "");
            }
        }

        if (!formData.has("insert_mode")) {
            var checkedMode = panel.querySelector("[data-ai-insert-mode]:checked");
            if (checkedMode) {
                formData.append("insert_mode", checkedMode.value || "append");
            }
        }

        if (!formData.has("csrfmiddlewaretoken")) {
            formData.append("csrfmiddlewaretoken", getCsrfToken());
        }

        return formData;
    }

    function findTarget(panel) {
        var targetSelector = panel.getAttribute("data-ai-target");
        if (targetSelector) {
            return document.querySelector(targetSelector);
        }

        var block = panel.closest(".block-item");
        if (block) {
            return block.querySelector("[data-written-question-textarea], textarea[name^='block_content_']");
        }

        return null;
    }

    function insertGeneratedText(panel, generatedText, insertMode) {
        var target = findTarget(panel);
        if (!target) {
            setStatus(panel, t("targetMissing", "Mətn sahəsi tapılmadı."), "error");
            return;
        }

        var text = (generatedText || "").trim();
        if (!text) {
            setStatus(panel, t("emptyResponse", "AI boş cavab qaytardı."), "error");
            return;
        }

        var current = target.value.trim();
        if (insertMode === "replace" || !current) {
            target.value = text;
        } else {
            target.value = current + "\n\n" + text;
        }

        target.dispatchEvent(new Event("input", { bubbles: true }));
        target.focus({ preventScroll: true });

        var staleResults = document.querySelector(".results-container");
        if (panel.getAttribute("data-ai-context") === "test" && staleResults) {
            staleResults.remove();
        }
    }

    function handleGenerate(panel) {
        var url = panel.getAttribute("data-ai-url");
        if (!url) {
            setStatus(panel, t("endpointMissing", "AI endpoint tapılmadı."), "error");
            return;
        }

        var formData = buildFormData(panel);
        var prompt = String(formData.get("prompt") || "").trim();
        var hasSourceFile = Boolean(formData.get("source_file"));
        var sourceText = String(formData.get("source_text") || "").trim();

        if (!prompt && !hasSourceFile && !sourceText) {
            setStatus(panel, t("emptyInput", "Prompt yazın və ya fayl yükləyin."), "error");
            return;
        }

        setBusy(panel, true);
        setStatus(panel, t("loading", "Gemini 2.5 Pro sualları hazırlayır..."), "loading");

        fetch(url, {
            method: "POST",
            body: formData,
            headers: {
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest"
            }
        })
            .then(function (response) {
                return response.text().then(function (body) {
                    var json = {};
                    try {
                        json = body ? JSON.parse(body) : {};
                    } catch (error) {
                        throw new Error(t("generateFailed", "AI sual yaratma alınmadı."));
                    }
                    if (!response.ok || !json.ok) {
                        throw new Error(json.error || t("generateFailed", "AI sual yaratma alınmadı."));
                    }
                    return json;
                });
            })
            .then(function (json) {
                insertGeneratedText(panel, json.text || "", String(formData.get("insert_mode") || "append"));
                var count = json.question_count || 0;
                var quota = "";
                if (json.remaining !== undefined && json.limit !== undefined) {
                    quota = " " + t("remainingRequests", "Qalan sorğu") + ": " + json.remaining + "/" + json.limit + ".";
                }
                setStatus(
                    panel,
                    t("readyTemplate", "{count} sual hazırdır. Önizləmə ilə yoxlayın.")
                        .replace("{count}", String(count)) + quota,
                    "success"
                );
            })
            .catch(function (error) {
                setStatus(panel, error.message || t("generateFailed", "AI sual yaratma alınmadı."), "error");
            })
            .finally(function () {
                setBusy(panel, false);
            });
    }

    function initPanel(panel) {
        if (!panel || panel.dataset.aiQuestionPanelReady === "true") return;
        var button = panel.querySelector("[data-ai-question-submit]");
        if (!button) return;
        panel.dataset.aiQuestionPanelReady = "true";

        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.init(panel);
        }

        panel.querySelectorAll("[data-ai-file-input]").forEach(function (input) {
            var fileNameEl = panel.querySelector('[data-ai-file-name-for="' + input.id + '"]');
            input.addEventListener("change", function () {
                var fileName = input.files && input.files[0] ? input.files[0].name : "";
                if (!fileNameEl) return;
                fileNameEl.textContent = fileName || t("noFileSelected", "Fayl seçilməyib");
                fileNameEl.classList.toggle("has-file", Boolean(fileName));
                fileNameEl.title = fileName || "";
            });
        });

        button.addEventListener("click", function (event) {
            event.preventDefault();
            handleGenerate(panel);
        });

        panel.addEventListener("keydown", function (event) {
            var tagName = event.target && event.target.tagName ? event.target.tagName.toUpperCase() : "";
            if (event.key === "Enter" && tagName !== "TEXTAREA") {
                event.preventDefault();
                handleGenerate(panel);
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-ai-question-form]").forEach(initPanel);
    });

    window.initAiQuestionBankPanel = initPanel;
})();
