"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const scripts = ["faq_player.js", "faq.js"].map(name =>
    fs.readFileSync(path.join(__dirname, "../../apps/accounts/static/accounts/js/profile", name), "utf8")
);

const question = (flags = "") => `
<div class="ems-faq-result"><details data-faq-item><summary>Sual</summary><div class="ems-faq-media">
<button data-faq-watch data-guide-key="assignment" data-start="4.875" ${flags}
 data-src="/local/own.mp4" aria-label="Sual"></button><button data-faq-seek="1.125">1:01</button>
<button data-faq-open-chapters>Fəsillər</button></div></details>
<button data-faq-shortcut><span data-shortcut-time></span></button></div>`;

const first = {
    key: "tour", title: "Tələbə kabineti", src: "/local/tour.mp4", track: "/local/tour.vtt", duration: 90,
    chapters: Array.from({length: 42}, (_, i) => ({start: i * 2 + .125, title: "Fəsil " + i, menu: i % 2 === 0})),
};
const second = {
    key: "work", title: "Tapşırıqlar", src: "/local/work.mp4", track: "", duration: 10,
    chapters: [{start: 1.125, title: "Qəbul"}, {start: 4.875, title: "Qiymətə bax"}],
};
const manifest = {
    sources: [first, second], playlist: ["tour", "work"], targets: {assignment: {key: "tour", start: 22.125, source: "work"}},
};

function setup({featured = true, flags = ""} = {}) {
    const stage = `<section data-faq-film data-play-error="Xəta"><script type="application/json" id="faq-film-data">${JSON.stringify(manifest)}</script>
    <div data-film-poster><button data-film-begin>Başlat</button><span data-film-duration></span></div>
    <div data-film-screen hidden></div><details data-film-drawer open><summary>Fəsillər</summary>
    <input data-film-filter><ol data-film-chapters></ol><span data-film-count></span><p data-film-empty></p>
    <div data-film-pages><button data-film-prev></button><span data-film-page></span><button data-film-next></button></div>
    </details><div data-film-toolbar hidden><input type="range" data-film-range><span data-film-clock></span>
    <span data-film-now></span><button data-film-begin></button></div><p data-film-error hidden></p></section>`;
    const body = featured ? `<div data-faq-panel data-results-url="/search">${stage}
    <form action="/cabinet" data-faq-search><input name="faq_q"></form><p data-faq-retry hidden><a></a></p>
    <div data-faq-results>${question(flags)}</div></div>` : question(flags);
    const dom = new JSDOM(body, {url: "https://example.test/cabinet", runScripts: "outside-only"});
    const win = dom.window;
    const media = win.HTMLMediaElement.prototype;
    Object.defineProperties(media, {
        readyState: {get() { return this._ready || 0; }},
        ended: {get() { return Boolean(this._ended); }},
        duration: {get() { return this.src.endsWith("work.mp4") ? 10 : 90; }},
    });
    media.play = function () { return Promise.resolve(); };
    media.pause = media.load = function () {};
    scripts.forEach(script => win.eval(script));
    const doc = win.document;
    doc.dispatchEvent(new win.Event("DOMContentLoaded"));
    function qa(selector) { return [...doc.querySelectorAll(selector)]; }
    function q(selector) { return doc.querySelector(selector); }
    function trigger(node, name) { node.dispatchEvent(new win.Event(name, {bubbles: true, cancelable: true})); }
    function metadata() {
        const video = q("video");
        video._ready = 1;
        trigger(video, "loadedmetadata");
        return video;
    }
    return {win, doc, qa, q, trigger, metadata};
}

test("large cabinet opens without MP4/VTT and keeps only one page of chapters in the DOM", () => {
    const {q, qa, trigger} = setup();
    assert.equal(q("video,track,source"), null);
    assert.equal(q("[data-film-duration]").textContent, "1:40");
    assert.equal(qa("[data-film-seek]").length, 20);
    assert.equal(q("[data-film-count]").textContent, "44");
    assert.doesNotMatch(q("[data-film-chapters]").textContent, /true|false/);
    q("[data-film-next]").click();
    assert.equal(q("[data-film-page]").textContent, "2 / 3");
    const filter = q("[data-film-filter]");
    filter.value = "qiyMeTe";
    trigger(filter, "input");
    assert.equal(qa("[data-film-seek]").length, 1);
    assert.equal(q("[data-film-seek] time").textContent, "1:34");
    assert.equal(q("video,track"), null);
    filter.value = "xyz";
    trigger(filter, "input");
    assert.equal(q("[data-film-empty]").hidden, false);
    q("[data-faq-open-chapters]").click();
    assert.equal(qa("[data-film-seek]").length, 2);
    assert.equal(q("video"), null);
});

test("a question starts from its authored tour location while matches and explicit chapter requests use local clip times", () => {
    for (const [flags, src, time, stamp] of [
        ["", first.src, 22.125, "0:22"],
        ["data-faq-exact", second.src, 4.875, "1:34"],
        ["data-faq-match", second.src, 4.875, "1:34"],
    ]) {
        const {q, metadata} = setup({flags});
        assert.equal(q("[data-shortcut-time]").textContent, stamp);
        q("[data-faq-shortcut]").click();
        assert.equal(q("details[data-faq-item]").open, false);
        assert.equal(q("video").getAttribute("src"), src);
        assert.equal(metadata().currentTime, time);
        q("[data-faq-seek]").click();
        assert.equal(q("video").getAttribute("src"), second.src);
        assert.equal(metadata().currentTime, 1.125);
    }
});

test("new seek before metadata wins, and continuous playback plus global scrubbing keep the native player", () => {
    const {q, qa, trigger, metadata} = setup();
    q("[data-film-begin]").click();
    qa("[data-film-seek]")[3].click();
    qa("[data-film-seek]")[7].click();
    const video = metadata();
    assert.equal(video.currentTime, 14.125);
    assert.equal(q("track").getAttribute("src"), first.track);
    video._ended = true;
    trigger(video, "ended");
    assert.equal(q("video"), video);
    assert.equal(video.getAttribute("src"), second.src);
    assert.equal(q("track"), null);
    video._ended = false;
    metadata();
    assert.equal(video.currentTime, 0);
    const range = q("[data-film-range]");
    range.value = "93";
    trigger(range, "input");
    assert.equal(video.currentTime, 0);
    trigger(range, "change");
    assert.equal(video.currentTime, 3);
    assert.equal(range.getAttribute("aria-valuetext"), "1:33 / 1:40");
    range.value = "10";
    trigger(range, "change");
    assert.equal(video.getAttribute("src"), first.src);
    assert.equal(metadata().currentTime, 10);
});

test("AJAX search replaces only questions, preserves current media on failure, and wires new shortcuts", async () => {
    const {win, q, trigger, metadata} = setup();
    q("[data-film-begin]").click();
    const video = metadata();
    video.currentTime = 17.25;
    const form = q("[data-faq-search]");
    q("[name=faq_q]").value = "tapşırıq";
    win.fetch = async (url, options) => {
        assert.equal(options.headers["X-Requested-With"], "XMLHttpRequest");
        assert.equal(url.searchParams.get("faq_results"), "1");
        assert.equal(url.searchParams.get("faq_q"), "tapşırıq");
        return {ok: true, text: async () => '<p data-faq-count tabindex="-1">1</p>' + question("data-faq-match")};
    };
    trigger(form, "submit");
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(q("video"), video);
    assert.equal(video.currentTime, 17.25);
    assert.equal(q("[data-shortcut-time]").textContent, "1:34");
    win.fetch = async () => { throw new Error("offline"); };
    trigger(form, "submit");
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(q("[data-faq-retry]").hidden, false);
    assert.equal(q("video"), video);
    assert.equal(video.currentTime, 17.25);
});

test("public login keeps its on-demand inline controls without a private tour", () => {
    const {q, trigger, metadata} = setup({featured: false});
    assert.equal(q("video"), null);
    q("[data-faq-item]").open = true;
    q("[data-faq-watch]").click();
    q("[data-faq-seek]").click();
    assert.equal(metadata().currentTime, 1.125);
    assert.equal(q("video").getAttribute("src"), "/local/own.mp4");
    q("[data-faq-item]").open = false;
    trigger(q("[data-faq-item]"), "toggle");
    assert.equal(q("video"), null);
});


test("an expired view-as closes the old cabinet and accepts only its own origin as the return address", async () => {
    for (const [redirect, closed] of [["https://different.example/path", false], ["/cabinet", true]]) {
        const {win, q, trigger} = setup();
        let paused = false;
        q("[data-film-begin]").click();
        q("video").pause = () => { paused = true; };
        win.fetch = async (url, options) => {
            assert.equal(options.headers["X-Requested-With"], "XMLHttpRequest");
            return {status: 409, ok: false, json: async () => ({view_as_ended: true, redirect})};
        };
        trigger(q("[data-faq-search]"), "submit");
        await new Promise(resolve => setTimeout(resolve, 0));
        assert.equal(q("[data-faq-panel]") === null, closed);
        assert.equal(paused, closed);
        if (!closed) assert.equal(q("[data-faq-retry]").hidden, false);
    }
});
