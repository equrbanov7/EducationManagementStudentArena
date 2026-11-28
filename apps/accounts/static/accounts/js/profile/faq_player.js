/* The featured player consumes only the role-filtered manifest supplied by Django. */
(() => {
    "use strict";

    const players = new WeakMap();
    const pageSize = 20;

    function formatTime(seconds) {
        const total = Math.max(0, Math.floor(Number(seconds) || 0));
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor(total / 60) % 60;
        const tail = String(total % 60).padStart(2, "0");
        return hours ? hours + ":" + String(minutes).padStart(2, "0") + ":" + tail : minutes + ":" + tail;
    }

    function words(value) {
        return String(value).toLocaleLowerCase("az").replace(/ə/g, "e").replace(/ı/g, "i")
            .normalize("NFD").replace(/\p{M}/gu, "");
    }

    class Film {
        constructor(root, data) {
            this.root = root;
            this.sources = new Map(data.sources.map(source => [source.key, source]));
            this.playlist = data.playlist.filter(key => this.sources.has(key));
            this.targets = data.targets;
            this.video = null;
            this.activeKey = null;
            this.currentRow = null;
            this.buttons = new Map();
            this.rows = [];
            this.page = 0;
            this.revision = 0;
            this.byStart = new Map();
            this.offsets = new Map();
            this.elements = {};
            for (const key of ["poster", "screen", "filter", "chapters", "empty", "count", "now", "toolbar", "error", "pages", "page", "prev", "next", "range", "clock"]) {
                this.elements[key] = root.querySelector("[data-film-" + key + "]");
            }
            this.duration = this.playlist.reduce((sum, key) => sum + (Number(this.sources.get(key).duration) || 0), 0);
            this.elements.range.max = Math.ceil(this.duration);
            this.totalLabel = formatTime(this.duration);
            if (this.duration) root.querySelector("[data-film-duration]").textContent = this.totalLabel;
            this.updateClock(0);
            this.indexChapters();
            this.filter();
            const drawer = this.root.querySelector("[data-film-drawer]");
            const width = this.root.getBoundingClientRect().width;
            if (width > 0 && width <= 736) drawer.open = false;
            this.root.addEventListener("input", event => {
                if (event.target === this.elements.filter) this.filter();
                if (event.target === this.elements.range) {
                    this.scrubbing = true;
                    this.updateClock(Number(event.target.value));
                }
            });
            this.elements.range.addEventListener("change", () => {
                this.scrubbing = false;
                this.seekProgram(Number(this.elements.range.value));
            });
            this.elements.range.addEventListener("blur", () => { this.scrubbing = false; });
            this.root.addEventListener("click", event => {
                const button = event.target.closest("button");
                if (!button) return;
                if (button === this.elements.prev || button === this.elements.next) {
                    this.page += (button === this.elements.next ? 1 : -1);
                    this.drawPage();
                    if (button.disabled) (button === this.elements.next ? this.elements.prev : this.elements.next).focus();
                    return;
                }
                if (button.matches("[data-film-begin]")) this.play(this.playlist[0], 0, true);
                if (button.matches("[data-film-seek]")) this.play(button.dataset.key, Number(button.dataset.filmSeek), false);
            });
        }

        indexChapters() {
            let offset = 0;
            for (const key of this.playlist) {
                const source = this.sources.get(key);
                this.offsets.set(key, offset);
                const chapters = source.chapters?.length ? source.chapters : [{start: 0, title: source.title}];
                const rows = [];
                this.byStart.set(key, rows);
                for (const chapter of chapters) {
                    const start = Number(chapter.start);
                    const row = {
                        key, start, title: chapter.title, context: source.title,
                        time: formatTime(offset + start),
                        terms: words(source.title + " " + chapter.title),
                    };
                    rows.push(row);
                    this.rows.push(row);
                }
                offset += Number(source.duration) || 0;
            }
            this.elements.count.textContent = this.rows.length;
        }

        filter() {
            const terms = words(this.elements.filter.value).trim().split(/\s+/).filter(Boolean);
            this.filtered = terms.length ? this.rows.filter(row => terms.every(word => row.terms.includes(word))) : this.rows;
            this.page = 0;
            this.drawPage();
        }

        drawPage() {
            const elements = this.elements;
            const pages = Math.ceil(this.filtered.length / pageSize);
            this.page = Math.max(0, Math.min(this.page, pages - 1));
            const fragment = document.createDocumentFragment();
            this.buttons.clear();
            const start = this.page * pageSize;
            for (const row of this.filtered.slice(start, start + pageSize)) {
                const item = document.createElement("li");
                const button = document.createElement("button");
                button.type = "button";
                button.dataset.filmSeek = row.start;
                button.dataset.key = row.key;
                const time = document.createElement("time");
                time.textContent = row.time;
                const label = document.createElement("span");
                label.textContent = row.title;
                if (this.playlist.length > 1 && row.title !== row.context) {
                    const subtitle = document.createElement("small");
                    subtitle.textContent = row.context;
                    label.prepend(subtitle);
                }
                button.append(time, label);
                if (row === this.currentRow) button.setAttribute("aria-current", "true");
                this.buttons.set(row, button);
                item.append(button);
                fragment.append(item);
            }
            elements.chapters.replaceChildren(fragment);
            elements.chapters.scrollTop = 0;
            elements.pages.hidden = pages < 2;
            elements.prev.disabled = this.page === 0;
            elements.next.disabled = this.page + 1 >= pages;
            elements.page.textContent = pages ? (this.page + 1) + " / " + pages : "";
            elements.empty.hidden = this.filtered.length > 0;
        }

        mark(time, reveal = false) {
            const rows = this.byStart.get(this.activeKey) || [];
            let active = rows[0] || null;
            for (const row of rows) {
                if (row.start > time) break;
                active = row;
            }
            if (active !== this.currentRow) {
                this.buttons.get(this.currentRow)?.removeAttribute("aria-current");
                this.currentRow = active;
                if (!active) return;
                this.elements.now.textContent = active.title;
            }
            if (!active) return;
            if (reveal && !this.buttons.has(active)) {
                let index = this.filtered.indexOf(active);
                if (index < 0) {
                    this.elements.filter.value = "";
                    this.filtered = this.rows;
                    index = this.rows.indexOf(active);
                }
                this.page = Math.floor(index / pageSize);
                this.drawPage();
            }
            this.buttons.get(active)?.setAttribute("aria-current", "true");
        }

        questionTime(button, explicitTime) {
            const target = this.targets?.[button.dataset.guideKey];
            if (!target) return null;
            const key = explicitTime ? target.source : target.key;
            if (!this.sources.has(key)) return null;
            const start = Number(explicitTime ? explicitTime.start : target.start);
            return {key, start, stamp: formatTime((this.offsets.get(key) || 0) + start)};
        }

        openQuestion(button, explicitTime) {
            const time = this.questionTime(button, explicitTime);
            if (!time) return false;
            this.play(time.key, time.start, true);
            this.root.scrollIntoView?.({block: "start"});
            return true;
        }

        browseQuestion(button) {
            const target = this.targets?.[button.dataset.guideKey];
            const source = this.sources.get(target?.source);
            if (!source) return;
            this.root.querySelector("[data-film-drawer]").open = true;
            this.elements.filter.value = source.title;
            this.filter();
            this.root.scrollIntoView?.({block: "start"});
            this.elements.filter.focus({preventScroll: true});
            this.elements.filter.select();
        }

        updateClock(position) {
            const time = Math.min(this.duration, Math.max(0, position));
            const text = formatTime(time) + " / " + this.totalLabel;
            if (!this.scrubbing) this.elements.range.value = Math.floor(time);
            if (this.elements.clock.textContent !== text) {
                this.elements.clock.textContent = text;
                this.elements.range.setAttribute("aria-valuetext", text);
            }
        }

        seekProgram(time) {
            let key = this.playlist[0];
            for (const candidate of this.playlist) {
                if (this.offsets.get(candidate) > time) break;
                key = candidate;
            }
            this.play(key, Math.min(time, this.duration) - this.offsets.get(key), false, true);
        }

        makeVideo() {
            const video = document.createElement("video");
            video.controls = true;
            video.playsInline = true;
            video.preload = "none";
            video.tabIndex = 0;
            video.addEventListener("timeupdate", () => {
                if (this.waitingForMetadata || video.readyState < 1) return;
                this.mark(video.currentTime);
                if (!this.scrubbing) this.updateClock(this.offsets.get(this.activeKey) + video.currentTime);
            });
            video.addEventListener("error", () => {
                this.elements.error.textContent = this.root.dataset.playError;
                this.elements.error.hidden = false;
            });
            video.addEventListener("ended", () => {
                if (!this.root.isConnected || !video.ended || this.waitingForMetadata) return;
                const next = this.playlist[this.playlist.indexOf(this.activeKey) + 1];
                if (next) this.play(next, 0, false, true);
            });
            this.elements.screen.append(video);
            this.elements.screen.hidden = false;
            this.elements.poster.hidden = true;
            this.elements.toolbar.hidden = false;
            this.video = video;
            return video;
        }

        play(key, start, focus, reveal = focus) {
            const source = this.sources.get(key);
            if (!source) return;
            const revision = ++this.revision;
            const video = this.video || this.makeVideo();
            const changed = key !== this.activeKey || Boolean(video.error);
            if (changed) {
                this.activeKey = key;
                this.waitingForMetadata = true;
                const oldTrack = video.querySelector("track");
                const captionsEnabled = oldTrack?.track?.mode === "showing";
                oldTrack?.remove();
                video.setAttribute("aria-label", source.title);
                if (source.track) {
                    const track = document.createElement("track");
                    track.kind = "captions";
                    track.label = this.root.dataset.language;
                    track.srclang = "az";
                    track.default = captionsEnabled;
                    track.src = source.track;
                    video.append(track);
                }
            }
            const time = Number.isFinite(start) && start >= 0 ? start : 0;
            const seek = () => {
                if (this.revision !== revision) return;
                this.waitingForMetadata = false;
                video.currentTime = Number.isFinite(video.duration) ? Math.min(time, video.duration) : time;
                this.mark(time);
            };
            if (this.waitingForMetadata || video.readyState < 1) video.addEventListener("loadedmetadata", seek, {once: true});
            else seek();
            if (changed) video.src = source.src;
            this.elements.error.hidden = true;
            this.mark(time, reveal);
            this.updateClock(this.offsets.get(key) + time);
            if (focus) video.focus({preventScroll: true});
            video.play().catch(() => { /* Native controls remain available if the browser requires another gesture. */ });
        }
    }

    function find(panel) {
        const root = panel?.querySelector("[data-faq-film]");
        if (!root) return null;
        if (players.has(root)) return players.get(root);
        const script = root.querySelector("#faq-film-data");
        if (!script) return null;
        const data = JSON.parse(script.textContent);
        if (!data.playlist?.length) return null;
        const player = new Film(root, data);
        players.set(root, player);
        return player;
    }

    function mount() { document.querySelectorAll("[data-faq-panel]").forEach(find); }
    window.EMSFaqFilm = {find};
    document.addEventListener("profile:section:loaded", mount);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, {once: true});
    else mount();
})();
