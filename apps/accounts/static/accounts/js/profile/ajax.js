/* Delegated AJAX links/forms and profile-section navigation events. */
(function (ns) {
    "use strict";

    ns.register(function installProfileAjaxEvents(ctx) {
        if (!ctx.profilePage || !ctx.sectionLinks.length || !ctx.sectionPanels.length) {
            return;
        }

        ctx.sectionLinks.forEach(function (link) {
            link.addEventListener("click", function (event) {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                    return;
                }

                var section = link.getAttribute("data-section");
                if (!section) {
                    return;
                }

                if (link.getAttribute("data-force-navigation") === "true") {
                    return;
                }

                if (ctx.isAjaxSafeSection(section)) {
                    event.preventDefault();
                    ctx.tryAjaxLoadSection(section, {
                        updateUrl: true,
                        sourceUrl: link.getAttribute("href")
                    }).then(function (ok) {
                        if (!ok) {
                            var nextUrl = new URL(ctx.profileBaseUrl, window.location.origin);
                            nextUrl.searchParams.set("section", section);
                            window.location.href = nextUrl.pathname + nextUrl.search;
                        }
                    });
                    return;
                }

                if (ctx.setActiveSection(section, true)) {
                    event.preventDefault();
                    if (ctx.isMobileViewport()) {
                        ctx.setSidebarCollapsed(true);
                    }
                }
            });
        });

        document.addEventListener("click", function (event) {
            if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }

            var trigger = event.target.closest("a[href]");
            if (!trigger || trigger.getAttribute("data-force-navigation") === "true") {
                return;
            }
            if (!trigger.closest("[data-profile-section-panel]") && !trigger.hasAttribute("data-profile-ajax-link")) {
                return;
            }

            var linkUrl;
            try {
                linkUrl = new URL(trigger.getAttribute("href"), window.location.origin);
            } catch (e) {
                return;
            }
            var section = trigger.getAttribute("data-section") || linkUrl.searchParams.get("section");
            if (!section || !ctx.isAjaxSafeSection(section)) {
                return;
            }

            event.preventDefault();
            ctx.tryAjaxLoadSection(section, {
                updateUrl: true,
                sourceUrl: linkUrl.pathname + linkUrl.search
            }).then(function (ok) {
                if (!ok) {
                    window.location.href = linkUrl.pathname + linkUrl.search;
                }
            });
        });

        document.addEventListener("submit", function (event) {
            var form = event.target;
            if (!form || !form.matches || !form.matches("form[data-profile-ajax-form]")) {
                return;
            }
            var method = (form.getAttribute("method") || "get").toLowerCase();
            if (method !== "get") {
                return;
            }
            var formData = new FormData(form);
            var section = form.getAttribute("data-section") || formData.get("section");
            if (!section || !ctx.isAjaxSafeSection(section)) {
                return;
            }

            event.preventDefault();
            var actionUrl;
            try {
                actionUrl = new URL(form.getAttribute("action") || ctx.profileBaseUrl, window.location.origin);
            } catch (e) {
                actionUrl = new URL(ctx.profileBaseUrl, window.location.origin);
            }
            actionUrl.search = "";
            formData.forEach(function (value, key) {
                if (typeof File !== "undefined" && value instanceof File) {
                    return;
                }
                actionUrl.searchParams.set(key, value);
            });
            actionUrl.searchParams.set("section", section);

            ctx.tryAjaxLoadSection(section, {
                updateUrl: true,
                sourceUrl: actionUrl.pathname + actionUrl.search
            }).then(function (ok) {
                if (!ok) {
                    window.location.href = actionUrl.pathname + actionUrl.search;
                }
            });
        });

        document.addEventListener("submit", function (event) {
            var form = event.target;
            if (!form || !form.matches || !form.matches("form[data-profile-ajax-post]")) {
                return;
            }
            var section = form.getAttribute("data-section");
            if (!section || !ctx.isAjaxSafeSection(section) || form.getAttribute("data-ajax-busy") === "1") {
                return;
            }

            event.preventDefault();
            form.setAttribute("data-ajax-busy", "1");
            var submitButtons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
            submitButtons.forEach(function (button) {
                button.disabled = true;
            });

            fetch(form.getAttribute("action"), {
                method: (form.getAttribute("method") || "post").toUpperCase(),
                body: new FormData(form),
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest"
                }
            })
                .then(function (response) {
                    var contentType = response.headers.get("content-type") || "";
                    if (contentType.indexOf("application/json") !== -1) {
                        return response.json().then(function (payload) {
                            if (payload && payload.html && ctx.replaceSectionHtml(section, payload.html, {
                                updateUrl: true,
                                sourceUrl: ctx.profileBaseUrl + "?section=" + encodeURIComponent(section)
                            })) {
                                return true;
                            }
                            if (response.ok) {
                                return ctx.tryAjaxLoadSection(section, {
                                    updateUrl: true,
                                    sourceUrl: ctx.profileBaseUrl + "?section=" + encodeURIComponent(section)
                                });
                            }
                            throw new Error("bad_post_payload");
                        });
                    }
                    if (response.redirected && response.url) {
                        return ctx.tryAjaxLoadSection(section, { updateUrl: true, sourceUrl: response.url });
                    }
                    if (response.ok) {
                        return ctx.tryAjaxLoadSection(section, {
                            updateUrl: true,
                            sourceUrl: ctx.profileBaseUrl + "?section=" + encodeURIComponent(section)
                        });
                    }
                    throw new Error("post_http_" + response.status);
                })
                .then(function (ok) {
                    if (!ok) {
                        HTMLFormElement.prototype.submit.call(form);
                    }
                })
                .catch(function () {
                    HTMLFormElement.prototype.submit.call(form);
                })
                .then(function () {
                    form.setAttribute("data-ajax-busy", "0");
                    submitButtons.forEach(function (button) {
                        button.disabled = false;
                    });
                });
        });

        window.addEventListener("popstate", function (event) {
            var state = event.state || {};
            var section = state.section;
            if (!section) {
                try {
                    var params = new URLSearchParams(window.location.search);
                    section = params.get("section") || ctx.defaultSection;
                } catch (e) {
                    section = ctx.defaultSection;
                }
            }
            if (!ctx.isAjaxSafeSection(section)) {
                return;
            }
            ctx.tryAjaxLoadSection(section, { updateUrl: false, sourceUrl: window.location.href }).then(function (ok) {
                if (!ok) {
                    window.location.reload();
                }
            });
        });

        document.addEventListener("click", function (event) {
            var trigger = event.target.closest(".js-open-create-post");
            if (!trigger) {
                return;
            }

            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }

            event.preventDefault();
            ctx.setActiveSection("create-post", true);
            ctx.openCreatePostModal();
        });

        document.addEventListener("click", function (event) {
            var trigger = event.target.closest(".js-open-create-exam");
            if (!trigger) {
                return;
            }

            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }

            event.preventDefault();
            ctx.setActiveSection("my-exams", true);
            ctx.openCreateExamModal(trigger.getAttribute("data-create-exam-url"));
        });
    });
})(window.EMSProfile = window.EMSProfile || {});
