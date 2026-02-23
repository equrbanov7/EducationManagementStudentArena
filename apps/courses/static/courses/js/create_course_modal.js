document.addEventListener("DOMContentLoaded", function () {
    var modal = document.getElementById("createCourseModal");
    var modalBody = document.getElementById("createCourseModalBody");
    var closeModalButton = document.getElementById("closeCreateCourseModal");
    var submitInFlight = false;
    var activeTrigger = null;

    if (!modal || !modalBody) {
        return;
    }

    function ensureModalRoot() {
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
    }

    function modalLoadingMarkup() {
        var loadingText = modal.getAttribute("data-loading-text") || "Loading form...";
        return '<div class="create-course-modal-loading">' + loadingText + "</div>";
    }

    function modalErrorMarkup() {
        var errorText = modal.getAttribute("data-load-error-text") || "Form failed to load. Please try again.";
        return '<div class="create-course-modal-error">' + errorText + "</div>";
    }

    function buildModalUrl(baseUrl) {
        try {
            var url = new URL(baseUrl, window.location.origin);
            url.searchParams.set("modal", "1");
            return url.pathname + url.search;
        } catch (error) {
            return baseUrl + (baseUrl.indexOf("?") === -1 ? "?modal=1" : "&modal=1");
        }
    }

    function resolveSuccessUrl(data) {
        if (activeTrigger) {
            var successUrl = activeTrigger.getAttribute("data-success-url");
            if (successUrl) {
                return successUrl;
            }

            var successSection = activeTrigger.getAttribute("data-success-section");
            if (successSection) {
                var sectionUrl = new URL(window.location.href);
                sectionUrl.searchParams.set("section", successSection);
                return sectionUrl.pathname + sectionUrl.search;
            }
        }

        if (data && data.dashboard_url) {
            return data.dashboard_url;
        }

        return window.location.href;
    }

    function closeModal(resetContent) {
        modal.classList.remove("active");
        document.body.style.overflow = "";
        if (resetContent) {
            modalBody.innerHTML = modalLoadingMarkup();
        }
    }

    function bindCoverImagePreview() {
        var coverInput = modalBody.querySelector('input[name="cover_image"]');
        var previewWrap = modalBody.querySelector("#createCourseImagePreviewWrap");
        var previewImage = modalBody.querySelector("#createCourseImagePreview");
        if (!coverInput || !previewWrap || !previewImage) {
            return;
        }

        coverInput.addEventListener("change", function (event) {
            var file = event.target.files && event.target.files[0];
            if (!file) {
                previewImage.src = "";
                previewWrap.hidden = true;
                return;
            }

            var reader = new FileReader();
            reader.onload = function (loadEvent) {
                previewImage.src = loadEvent.target.result;
                previewWrap.hidden = false;
            };
            reader.readAsDataURL(file);
        });
    }

    function bindModalForm() {
        if (!modalBody) {
            return;
        }

        bindCoverImagePreview();

        var closeInlineButton = modalBody.querySelector(".js-close-create-course");
        if (closeInlineButton) {
            closeInlineButton.addEventListener("click", function () {
                closeModal(true);
            });
        }

        var form = modalBody.querySelector("#createCourseModalForm");
        if (!form) {
            return;
        }

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            if (submitInFlight) {
                return;
            }

            submitInFlight = true;
            var submitButton = form.querySelector('button[type="submit"]');
            var originalSubmitText = submitButton ? submitButton.innerHTML : "";
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = modal.getAttribute("data-submitting-text") || "Creating...";
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
                    var successData = await response.json();
                    if (successData.success) {
                        closeModal(true);
                        window.location.href = resolveSuccessUrl(successData);
                        return;
                    }
                }

                if (contentType.indexOf("application/json") !== -1) {
                    var errorData = await response.json();
                    if (errorData.html) {
                        modalBody.innerHTML = errorData.html;
                        bindModalForm();
                        return;
                    }
                }

                modalBody.innerHTML = modalErrorMarkup();
            } catch (error) {
                modalBody.innerHTML = modalErrorMarkup();
            } finally {
                submitInFlight = false;
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalSubmitText;
                }
            }
        });
    }

    async function openModal(createCourseUrl, trigger) {
        if (!createCourseUrl) {
            return;
        }

        activeTrigger = trigger || null;
        ensureModalRoot();
        modal.classList.add("active");
        document.body.style.overflow = "hidden";
        modalBody.innerHTML = modalLoadingMarkup();

        var modalUrl = buildModalUrl(createCourseUrl);

        try {
            var response = await fetch(modalUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            });

            if (!response.ok) {
                throw new Error("create course modal load failed");
            }

            modalBody.innerHTML = await response.text();
            bindModalForm();
        } catch (error) {
            modalBody.innerHTML = modalErrorMarkup();
        }
    }

    if (closeModalButton) {
        closeModalButton.addEventListener("click", function () {
            closeModal(true);
        });
    }

    modal.addEventListener("click", function (event) {
        if (event.target === modal) {
            closeModal(true);
        }
    });

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest(".js-open-create-course");
        if (!trigger) {
            return;
        }

        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }

        event.preventDefault();
        openModal(trigger.getAttribute("data-create-course-url"), trigger);
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && modal.classList.contains("active")) {
            closeModal(true);
        }
    });
});
