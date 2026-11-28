(() => {
    "use strict";

    let timer;
    let pending;

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

    async function showResults(panel, url, moveFocus) {
        cancelSearch();
        const controller = new AbortController();
        pending = controller;
        const results = panel.querySelector("[data-faq-results]");
        const endpoint = new URL(panel.dataset.resultsUrl, location.href);
        endpoint.search = url.search;
        endpoint.searchParams.set("faq_results", "1");
        results.setAttribute("aria-busy", "true");
        try {
            const response = await fetch(endpoint, { signal: controller.signal, credentials: "same-origin" });
            if (!response.ok || response.redirected) throw new Error("faq unavailable");
            const html = await response.text();
            if (controller.signal.aborted || !panel.isConnected) return;
            results.querySelectorAll("video").forEach(stopVideo);
            results.innerHTML = html;
            panel.querySelector('[name="faq_q"]').value = url.searchParams.get("faq_q") || "";
            history.replaceState(history.state, "", url);
            if (moveFocus) results.querySelector("[data-faq-count]").focus();
        } catch (error) {
            if (error.name !== "AbortError" && panel.isConnected) location.assign(url);
        } finally {
            if (pending === controller) {
                results.removeAttribute("aria-busy");
                pending = null;
            }
        }
    }

    document.addEventListener("input", (event) => {
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

    document.addEventListener("submit", (event) => {
        const form = event.target.closest("[data-faq-search]");
        if (!form) return;
        event.preventDefault();
        showResults(form.closest("[data-faq-panel]"), formUrl(form), false);
    });

    document.addEventListener("click", (event) => {
        const page = event.target.closest("[data-faq-page]");
        if (page && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
            event.preventDefault();
            showResults(page.closest("[data-faq-panel]"), new URL(page.href), true);
            return;
        }
        const chapter = event.target.closest("[data-faq-seek]");
        const button = chapter ? chapter.closest(".ems-faq-media").querySelector("[data-faq-watch]") :
            event.target.closest("[data-faq-watch]");
        if (!button) return;
        const start = Number(chapter ? chapter.dataset.faqSeek : button.dataset.start) || 0;
        const active = button.parentElement.querySelector("video");
        document.querySelectorAll(".ems-faq-media video").forEach((video) => {
            if (video !== active) stopVideo(video);
        });
        if (active) {
            active.currentTime = start;
            active.play().catch(() => {});
            return;
        }
        const video = document.createElement("video");
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
        if (start) video.addEventListener("loadedmetadata", () => { video.currentTime = start; }, { once: true });
        video.src = button.dataset.src;
        button.after(video);
        button.hidden = true;
        video.focus();
        video.play().catch(() => { /* Brauzerin yerli oynatma düyməsi qalır. */ });
    });

    document.addEventListener("toggle", (event) => {
        const item = event.target;
        if (!item.matches?.("[data-faq-item]") || item.open) return;
        const video = item.querySelector("video");
        if (video) stopVideo(video);
    }, true);
})();
