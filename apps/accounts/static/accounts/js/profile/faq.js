(() => {
    "use strict";

    let timer;
    let pending;
    const inlineState = new WeakMap();

    function stopVideo(video) {
        const speaker = video.closest(".ems-faq-media");
        video.pause();
        video.removeAttribute("src");
        video.load();
        video.remove();
        if (speaker) speaker.querySelector("[data-faq-watch]").hidden = false;
    }

    function cancelSearch() {
        clearTimeout(timer);
        if (pending) pending.abort();
    }

    function formUrl(form) {
        const url = new URL(form.action, location.href);
        url.search = new URLSearchParams(new FormData(form)).toString();
        return url;
    }

    function explicitTime(button, chapter) {
        if (chapter) return {start: chapter.dataset.faqSeek};
        if (button.hasAttribute("data-faq-exact") || button.hasAttribute("data-faq-match")) {
            return {start: button.dataset.start};
        }
        return null;
    }

    function updateShortcuts(panel) {
        const film = window.EMSFaqFilm?.find(panel);
        if (!film) return;
        panel.querySelectorAll("[data-faq-shortcut]").forEach(shortcut => {
            const watch = shortcut.closest(".ems-faq-result").querySelector("[data-faq-watch]");
            const time = film.questionTime(watch, explicitTime(watch));
            if (time) {
                shortcut.querySelector("[data-shortcut-time]").textContent = time.stamp;
                shortcut.setAttribute("aria-label", watch.getAttribute("aria-label") + " · " + time.stamp);
            }
        });
    }

    async function showResults(panel, url, moveFocus) {
        cancelSearch();
        const controller = new AbortController();
        pending = controller;
        const results = panel.querySelector("[data-faq-results]");
        const retry = panel.querySelector("[data-faq-retry]");
        const endpoint = new URL(panel.dataset.resultsUrl, location.href);
        endpoint.search = url.search;
        endpoint.searchParams.set("faq_results", "1");
        results.setAttribute("aria-busy", "true");
        retry.hidden = true;
        try {
            const response = await fetch(endpoint, {
                signal: controller.signal,
                credentials: "same-origin",
                headers: {"X-Requested-With": "XMLHttpRequest"},
            });
            if (response.status === 409) {
                const payload = await response.json();
                if (controller.signal.aborted || !panel.isConnected) return;
                if (payload.view_as_ended === true && payload.redirect) {
                    const target = new URL(payload.redirect, location.origin);
                    if (target.origin === location.origin) {
                        panel.querySelectorAll("video").forEach(video => video.pause());
                        panel.remove();
                        location.assign(target.pathname + target.search);
                        return;
                    }
                }
            }
            if (!response.ok || response.redirected) throw new Error("faq unavailable");
            const html = await response.text();
            if (controller.signal.aborted || !panel.isConnected) return;
            results.querySelectorAll("video").forEach(stopVideo);
            results.innerHTML = html;
            panel.querySelector('[name="faq_q"]').value = url.searchParams.get("faq_q") || "";
            history.replaceState(history.state, "", url);
            updateShortcuts(panel);
            if (moveFocus) (results.querySelector("#faq-guide > summary") || results.querySelector("[data-faq-count]"))?.focus();
        } catch (error) {
            if (!controller.signal.aborted && panel.isConnected) {
                retry.querySelector("a").href = url;
                retry.hidden = false;
            }
        } finally {
            if (pending === controller) {
                results.removeAttribute("aria-busy");
                pending = null;
            }
        }
    }

    document.addEventListener("input", event => {
        if (event.target.matches("[data-faq-chapter-search]")) {
            const words = value => value.toLocaleLowerCase("az").replace(/ə/g, "e").replace(/ı/g, "i").normalize("NFD").replace(/\p{M}/gu, "");
            const terms = words(event.target.value).trim().split(/\s+/);
            event.target.closest(".ems-faq-chapters").querySelectorAll("li").forEach(row => {
                row.hidden = !terms.every(term => words(row.textContent).includes(term));
            });
            return;
        }
        const form = event.target.closest("[data-faq-search]");
        if (!form) return;
        cancelSearch();
        const panel = form.closest("[data-faq-panel]");
        timer = setTimeout(() => {
            if (panel.isConnected) showResults(panel, formUrl(form), false);
        }, 250);
    });

    document.addEventListener("submit", event => {
        const form = event.target.closest("[data-faq-search]");
        if (!form) return;
        event.preventDefault();
        showResults(form.closest("[data-faq-panel]"), formUrl(form), true);
    });

    // The generic cabinet navigation also delegates clicks. Claim only FAQ result links
    // during capture, including when this section's scripts were loaded by AJAX later.
    document.addEventListener("click", event => {
        const page = event.target.closest("[data-faq-page]");
        if (!page || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
        const panel = page.closest("[data-faq-panel]");
        if (!panel) return;
        event.preventDefault();
        showResults(panel, new URL(page.href), true);
    }, true);

    function playInline(button, start) {
        const media = button.closest(".ems-faq-media");
        let video = media.querySelector("video");
        if (!video) {
            video = document.createElement("video");
            video.controls = true;
            video.playsInline = true;
            video.preload = "none";
            video.tabIndex = 0;
            video.setAttribute("aria-label", button.getAttribute("aria-label"));
            if (button.dataset.track) {
                const track = document.createElement("track");
                track.kind = "captions";
                track.srclang = "az";
                track.label = button.dataset.language;
                track.src = button.dataset.track;
                video.append(track);
            }
            button.after(video);
            button.hidden = true;
            video.src = button.dataset.src;
        }
        const revision = (inlineState.get(video) || 0) + 1;
        inlineState.set(video, revision);
        const seek = () => {
            if (video.isConnected && inlineState.get(video) === revision) video.currentTime = start;
        };
        if (video.readyState >= 1) seek();
        else video.addEventListener("loadedmetadata", seek, {once: true});
        video.focus();
        video.play().catch(() => {});
    }

    document.addEventListener("click", event => {
        const browse = event.target.closest("[data-faq-open-chapters]");
        if (browse) {
            const watch = browse.closest(".ems-faq-media").querySelector("[data-faq-watch]");
            window.EMSFaqFilm?.find(browse.closest("[data-faq-panel]"))?.browseQuestion(watch);
            return;
        }
        const chapter = event.target.closest("[data-faq-seek]");
        const shortcut = event.target.closest("[data-faq-shortcut]");
        const scope = chapter?.closest(".ems-faq-media") || shortcut?.closest(".ems-faq-result");
        const button = scope?.querySelector("[data-faq-watch]") || event.target.closest("[data-faq-watch]");
        if (!button) return;
        const panel = button.closest("[data-faq-panel]");
        const active = button.closest(".ems-faq-media").querySelector("video");
        document.querySelectorAll(".ems-faq-media video").forEach(video => {
            if (video !== active) stopVideo(video);
        });
        const exact = explicitTime(button, chapter);
        if (window.EMSFaqFilm?.find(panel)?.openQuestion(button, exact)) {
            if (active) stopVideo(active);
            return;
        }
        if (shortcut) button.closest("[data-faq-item]").open = true;
        panel?.querySelector("[data-film-screen] video")?.pause();
        playInline(button, Number(exact ? exact.start : button.dataset.start) || 0);
    });

    document.addEventListener("toggle", event => {
        const item = event.target;
        if (!item.matches?.("[data-faq-item]") || item.open) return;
        const video = item.querySelector("video");
        if (video) stopVideo(video);
    }, true);

    const mount = () => document.querySelectorAll("[data-faq-panel]").forEach(updateShortcuts);
    document.addEventListener("profile:section:loaded", mount);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, {once: true});
    else mount();
})();
