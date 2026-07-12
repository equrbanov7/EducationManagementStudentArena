/* AJAX-safe profile section loading and section state helpers. */
(function (ns) {
    "use strict";

    ns.register(function installSectionLoader(ctx) {
        if (!ctx.profilePage) {
            return;
        }

        function refreshBadges() {
            if (!ctx.badgesUrl || typeof window.fetch !== "function") {
                return;
            }
            if (ctx.badgesRefreshInFlight) {
                try { ctx.badgesRefreshInFlight.abort(); } catch (e) { /* ignore */ }
            }
            var controller = (typeof AbortController === "function") ? new AbortController() : null;
            ctx.badgesRefreshInFlight = controller;
            var opts = {
                credentials: "same-origin",
                headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" }
            };
            if (controller) { opts.signal = controller.signal; }
            fetch(ctx.badgesUrl, opts)
                .then(function (resp) {
                    if (!resp.ok) { throw new Error("badges_http_" + resp.status); }
                    return resp.json();
                })
                .then(function (payload) {
                    if (!payload || payload.ok !== true || !payload.badges) {
                        return;
                    }
                    var badges = payload.badges;
                    Object.keys(badges).forEach(function (key) {
                        var value = badges[key];
                        var nodes = document.querySelectorAll(
                            '.profile-sidebar [data-badge-key="' + key + '"]'
                        );
                        nodes.forEach(function (node) {
                            if (value && value > 0) {
                                node.textContent = String(value);
                                node.style.display = "";
                            } else {
                                node.textContent = "";
                                node.style.display = "none";
                            }
                        });
                    });
                })
                .catch(function () { /* fail-soft */ })
                .then(function () {
                    if (ctx.badgesRefreshInFlight === controller) {
                        ctx.badgesRefreshInFlight = null;
                    }
                });
        }

        function resolveSectionFromUrl() {
            try {
                var params = new URLSearchParams(window.location.search);
                return params.get("section") || ctx.defaultSection;
            } catch (error) {
                return ctx.defaultSection;
            }
        }

        function isAjaxSafeSection(section) {
            return ctx.ajaxSafeSections.indexOf(section) !== -1
                && ctx.sectionFragmentUrlTemplate
                && ctx.sectionsHost
                && typeof window.fetch === "function";
        }

        function copySourceQueryToTarget(sourceUrl, targetUrl, section) {
            if (!sourceUrl) {
                targetUrl.searchParams.set("section", section);
                return targetUrl;
            }
            try {
                var source = new URL(sourceUrl, window.location.origin);
                source.searchParams.forEach(function (value, key) {
                    if (key !== "section") {
                        targetUrl.searchParams.append(key, value);
                    }
                });
            } catch (e) { /* ignore */ }
            targetUrl.searchParams.set("section", section);
            return targetUrl;
        }

        function buildSectionFragmentUrl(section, sourceUrl) {
            var fragmentPath = ctx.sectionFragmentUrlTemplate.replace("__SECTION__", encodeURIComponent(section));
            var target = new URL(fragmentPath, window.location.origin);
            copySourceQueryToTarget(sourceUrl, target, section);
            return target.pathname + target.search;
        }

        function pushSectionUrl(section, sourceUrl) {
            if (!window.history || !window.history.pushState) {
                return;
            }
            try {
                var nextUrl = new URL(ctx.profileBaseUrl, window.location.origin);
                copySourceQueryToTarget(sourceUrl, nextUrl, section);
                window.history.pushState({ section: section, ajax: true }, "", nextUrl.pathname + nextUrl.search);
            } catch (e) { /* ignore */ }
        }

        function extractSectionFromHtml(html, section) {
            try {
                var doc = null;
                if (typeof window.DOMParser === "function") {
                    try {
                        doc = new window.DOMParser().parseFromString(html, "text/html");
                    } catch (e) { doc = null; }
                }
                var root = doc || (function () {
                    var tmp = document.createElement("div");
                    tmp.innerHTML = html;
                    return tmp;
                })();
                var selector = '[data-profile-section-panel="' + section + '"]';
                return root.querySelector(selector);
            } catch (e) {
                return null;
            }
        }

        function getDocumentCspNonce() {
            if (ctx.profilePage) {
                var n = ctx.profilePage.getAttribute("data-csp-nonce");
                if (n) { return n; }
            }
            var anyScript = document.querySelector("script[nonce]");
            if (anyScript) {
                return anyScript.nonce || anyScript.getAttribute("nonce") || "";
            }
            return "";
        }

        function executeInlineScripts(panel) {
            if (!panel) {
                return;
            }
            var cspNonce = getDocumentCspNonce();
            var scripts = panel.querySelectorAll("script");
            scripts.forEach(function (oldScript) {
                var newScript = document.createElement("script");
                for (var i = 0; i < oldScript.attributes.length; i++) {
                    var attr = oldScript.attributes[i];
                    if (attr.name === "nonce") { continue; }
                    try { newScript.setAttribute(attr.name, attr.value); } catch (e) { /* ignore */ }
                }
                if (oldScript.textContent) {
                    newScript.textContent = oldScript.textContent;
                }
                if (cspNonce) {
                    try {
                        newScript.setAttribute("nonce", cspNonce);
                        newScript.nonce = cspNonce;
                    } catch (e) { /* ignore */ }
                }
                oldScript.parentNode.replaceChild(newScript, oldScript);
            });
        }

        function rebindCommonControls(panel) {
            if (!panel) { return; }

            if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.init === "function") {
                try { window.EMSBootstrapSelect.init(panel); } catch (e) { /* ignore */ }
            }

            try { ctx.initDebouncedSearchForms(); } catch (e) { /* ignore */ }

            if (window.EMSDebouncedSearchForms && typeof window.EMSDebouncedSearchForms.init === "function") {
                try { window.EMSDebouncedSearchForms.init(panel); } catch (e) { /* ignore */ }
            }

            if (window.EMSPagination && typeof window.EMSPagination.init === "function") {
                try { window.EMSPagination.init(panel); } catch (e) { /* ignore */ }
            }
        }

        function notifySectionLoaded(section, panel) {
            try {
                var ev = new CustomEvent("profile:section:loaded", {
                    detail: { section: section, panel: panel },
                    bubbles: true,
                    cancelable: false
                });
                document.dispatchEvent(ev);
                if (panel) {
                    panel.dispatchEvent(ev);
                }
            } catch (e) { /* ignore */ }

            try {
                if (window.EMSProfileReinitHooks && typeof window.EMSProfileReinitHooks === "object") {
                    Object.keys(window.EMSProfileReinitHooks).forEach(function (key) {
                        var hook = window.EMSProfileReinitHooks[key];
                        if (typeof hook === "function") {
                            try { hook(panel, section); } catch (err) { /* ignore */ }
                        }
                    });
                }
            } catch (e) { /* ignore */ }

            try { rebindCommonControls(panel); } catch (e) { /* ignore */ }
        }

        function replaceSectionHtml(section, html, options) {
            options = options || {};
            var node = extractSectionFromHtml(html, section);
            if (!node) {
                return false;
            }
            node.classList.add("is-active");
            var oldPanels = ctx.sectionsHost.querySelectorAll("[data-profile-section-panel]");
            oldPanels.forEach(function (p) {
                if (p.parentNode) {
                    p.parentNode.removeChild(p);
                }
            });
            ctx.sectionsHost.appendChild(node);

            var responseDoc = (function () {
                try {
                    return new window.DOMParser().parseFromString(html, "text/html");
                } catch (e) { return null; }
            })();
            if (responseDoc) {
                var responsePanels = responseDoc.querySelectorAll("[data-profile-section-panel]");
                responsePanels.forEach(function (p) {
                    var key = p.getAttribute("data-profile-section-panel");
                    if (!key || key === section) { return; }
                    if (ctx.sectionsHost.querySelector('[data-profile-section-panel="' + key + '"]')) {
                        return;
                    }
                    var ph = document.createElement("section");
                    ph.className = "profile-section-panel profile-section-placeholder";
                    ph.setAttribute("data-profile-section-panel", key);
                    ph.setAttribute("aria-hidden", "true");
                    ph.hidden = true;
                    ctx.sectionsHost.appendChild(ph);
                });
            }

            try { executeInlineScripts(node); } catch (e) { /* ignore */ }
            try { notifySectionLoaded(section, node); } catch (e) { /* ignore */ }
            ctx.updateSidebarActiveState(section);
            if (options.updateUrl !== false) {
                pushSectionUrl(section, options.sourceUrl);
            }
            ctx.sectionPanels = document.querySelectorAll("[data-profile-section-panel]");
            if (ctx.isMobileViewport()) {
                ctx.setSidebarCollapsed(true);
            }
            try { refreshBadges(); } catch (e) { /* ignore */ }
            return true;
        }

        function showSectionLoading() {
            if (ctx.sectionsHost) {
                ctx.sectionsHost.setAttribute("aria-busy", "true");
                ctx.sectionsHost.classList.add("is-loading");
            }
            // Üst route-progress zolağı: SPA yükləməsində səhifə yenilənmir,
            // ona görə zolağı burada başladıb clearSectionLoading-də bitiririk
            // (əks halda route_loading.js-in click handler-i onu başladır və
            // heç vaxt bitmirdi — "loading ilişib qalır" bug-ı).
            if (window.EMSRouteProgress) {
                window.EMSRouteProgress.start();
            }
        }

        function clearSectionLoading() {
            if (ctx.sectionsHost) {
                ctx.sectionsHost.removeAttribute("aria-busy");
                ctx.sectionsHost.classList.remove("is-loading");
            }
            if (window.EMSRouteProgress) {
                window.EMSRouteProgress.finish();
            }
        }

        function tryAjaxLoadSection(section, options) {
            options = options || {};
            if (!isAjaxSafeSection(section)) {
                return Promise.resolve(false);
            }
            if (ctx.ajaxLoadInFlight) {
                try { ctx.ajaxLoadInFlight.abort(); } catch (e) { /* ignore */ }
            }
            var controller = (typeof AbortController === "function") ? new AbortController() : null;
            ctx.ajaxLoadInFlight = controller;
            showSectionLoading();

            var fetchOpts = {
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest"
                }
            };
            if (controller) {
                fetchOpts.signal = controller.signal;
            }

            return fetch(buildSectionFragmentUrl(section, options.sourceUrl), fetchOpts)
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("http_" + response.status);
                    }
                    return response.json();
                })
                .then(function (payload) {
                    if (!payload || payload.ok !== true || !payload.html) {
                        throw new Error("bad_payload");
                    }
                    if (!replaceSectionHtml(section, payload.html, {
                        updateUrl: options.updateUrl,
                        sourceUrl: options.sourceUrl
                    })) {
                        throw new Error("section_not_in_response");
                    }
                    return true;
                })
                .catch(function (err) {
                    if (err && err.name === "AbortError") {
                        return true;
                    }
                    return false;
                })
                .then(function (result) {
                    clearSectionLoading();
                    if (ctx.ajaxLoadInFlight === controller) {
                        ctx.ajaxLoadInFlight = null;
                    }
                    return result;
                });
        }

        function setActiveSection(section, updateUrl) {
            var hasTargetPanel = false;
            var targetIsPlaceholder = false;
            ctx.sectionPanels.forEach(function (panel) {
                if (panel.getAttribute("data-profile-section-panel") === section) {
                    hasTargetPanel = true;
                    if (panel.classList.contains("profile-section-placeholder")) {
                        targetIsPlaceholder = true;
                    }
                }
            });

            if (!hasTargetPanel || targetIsPlaceholder) {
                return false;
            }

            ctx.sectionPanels.forEach(function (panel) {
                var isMatch = panel.getAttribute("data-profile-section-panel") === section;
                panel.classList.toggle("is-active", isMatch);
            });

            ctx.updateSidebarActiveState(section);

            if (updateUrl && window.history && window.history.pushState) {
                var nextUrl = new URL(ctx.profileBaseUrl, window.location.origin);
                nextUrl.searchParams.set("section", section);
                window.history.pushState({ section: section }, "", nextUrl.pathname + nextUrl.search);
            }

            return true;
        }

        ctx.refreshBadges = refreshBadges;
        ctx.resolveSectionFromUrl = resolveSectionFromUrl;
        ctx.isAjaxSafeSection = isAjaxSafeSection;
        ctx.copySourceQueryToTarget = copySourceQueryToTarget;
        ctx.tryAjaxLoadSection = tryAjaxLoadSection;
        ctx.setActiveSection = setActiveSection;
        ctx.replaceSectionHtml = replaceSectionHtml;

        window.EMSProfileLoadSection = function (section, sourceUrl, options) {
            options = options || {};
            options.sourceUrl = sourceUrl || options.sourceUrl || "";
            if (typeof options.updateUrl === "undefined") {
                options.updateUrl = true;
            }
            return tryAjaxLoadSection(section, options);
        };
    });
})(window.EMSProfile = window.EMSProfile || {});
