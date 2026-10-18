/* ═══════════════════════════════════════════════════════════════════════════
   «Yeni Resurs» modalı (2026-10-19) — apps/courses/static/courses/js/resource_form_modal.js
   ƏSL kodla, jsdom-da.

   Bug: iPhone videosu (IMG_0189.MOV) nginx-in 64M limitinə dəyib HTML 413 alırdı; JS
   `response.json()` ilə çökür və ümumi «Xəta baş verdi» toast-ı göstərirdi. Format ipucu da hər
   tip üçün eyni idi. İndi: tipə görə ipucu/accept, yükləmədən əvvəl yoxlama, XHR irəliləyişi,
   status koduna görə aydın mesaj (modalın içində).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const MODAL_JS = fs.readFileSync(path.join(ROOT, "apps/courses/static/courses/js/resource_form_modal.js"), "utf8");
const MB = 1024 * 1024;

function radio(kind, id, attrs, checked) {
    return (
        `<input type="radio" name="resource_type" id="${id}" value="${kind}" data-accept="${attrs.accept}"` +
        ` data-hint="${attrs.hint}" data-max-bytes="${attrs.maxMb * MB}" data-max-mb="${attrs.maxMb}"` +
        ` data-extensions="${attrs.ext}" data-formats="${attrs.formats}"${checked ? " checked" : ""}>` +
        `<label for="${id}">${attrs.label}</label>`
    );
}

const HTML =
    '<div id="resourceFormModalConfig" hidden data-i18n-loading="Yüklənir" data-i18n-errors-header="Xətalar"' +
    ' data-i18n-uploading="Yüklənir: {pct}" data-i18n-processing="Server yoxlayır"' +
    ' data-i18n-ext-rejected="Bu format «{kind}» üçün qəbul edilmir: {ext}. İcazə verilənlər: {formats}"' +
    ' data-i18n-no-extension="(uzantısız)" data-i18n-too-large="Fayl çox böyükdür: {size} MB (maks. {max_mb} MB)"' +
    ' data-i18n-empty-file="Fayl boşdur." data-i18n-file-required="«{kind}» üçün fayl seçin."' +
    ' data-i18n-url-required="URL daxil edin" data-i18n-url-scheme="http/https" data-i18n-title-required="Ad yazın"' +
    ' data-i18n-server-limit="Fayl serverin qəbul etdiyi ölçüdən böyükdür (maks. {max_mb} MB)."' +
    ' data-i18n-session="Sessiya" data-i18n-forbidden="CSRF" data-i18n-network="Bağlantı kəsildi"' +
    ' data-i18n-timeout="Vaxt ({status})" data-i18n-server="Server xətası (kod {status})."></div>' +
    '<div id="resourceFormModal"><form id="resourceForm" method="post" action="/courses/resource-upload/1/">' +
    '<input type="hidden" name="csrfmiddlewaretoken" value="tok">' +
    radio("file", "typeFile", { accept: ".pdf,.zip", hint: "Fayl ipucu", maxMb: 100, ext: ".pdf .zip", formats: "PDF, ZIP", label: "Fayl" }, true) +
    radio("link", "typeLink", { accept: "", hint: "", maxMb: 0, ext: "", formats: "", label: "Link" }) +
    radio("video", "typeVideo", {
        accept: ".mp4,.mov,.webm,.m4v", hint: "Dəstəklənən formatlar: MP4, MOV, WEBM, M4V · maks. 200 MB",
        maxMb: 200, ext: ".mp4 .mov .webm .m4v", formats: "MP4, MOV, WEBM, M4V", label: "Video",
    }) +
    '<input id="resourceTitle" name="title" value="Mühazirə">' +
    '<div id="fileUploadSection"><div data-resource-dropzone>' +
    '<input type="file" id="resourceFile" name="file" accept=".pdf,.zip">' +
    '<span data-resource-file-name data-empty-label="Fayl seçin"></span><span data-resource-file-size hidden></span>' +
    '<button type="button" data-resource-file-clear hidden>x</button></div>' +
    '<p data-resource-file-hint>Fayl ipucu</p>' +
    '<div data-resource-progress hidden><progress data-resource-progress-bar max="100" value="0"></progress>' +
    '<span data-resource-progress-text></span></div></div>' +
    '<div id="urlInputSection" class="d-none"><input id="resourceUrl" name="url"></div>' +
    '<div id="resourceErrors" class="d-none"></div>' +
    '<div class="ems-bsd__foot"><button type="button" data-bs-dismiss="modal">Ləğv et</button>' +
    '<button type="submit" data-resource-submit>Əlavə et</button></div></form></div>';

async function page() {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/courses/1/dashboard/",
        virtualConsole: new VirtualConsole(),
    });
    const { window } = dom;
    const sent = [];
    class FakeXHR {
        constructor() {
            this.upload = new window.EventTarget();
            this.listeners = {};
            this.headers = {};
            this.status = 0;
        }
        open(method, url) { this.method = method; this.url = url; }
        setRequestHeader(name, value) { this.headers[name] = value; }
        addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
        send(body) { this.body = body; sent.push(this); }
        getResponseHeader(name) { return (this.respHeaders || {})[name.toLowerCase()] || null; }
        fire(type) { (this.listeners[type] || []).forEach((fn) => fn()); }
        respond(status, contentType, text) {
            this.status = status;
            this.respHeaders = { "content-type": contentType };
            this.responseText = text;
            this.fire("load");
        }
        abort() { this.fire("abort"); }
    }
    window.XMLHttpRequest = FakeXHR;
    window.notices = [];
    window.notify = (message, kind) => window.notices.push([kind, message]);
    window.hidden = 0;
    window.bootstrap = { Modal: { getInstance: () => ({ hide: () => { window.hidden += 1; } }) } };
    window.eval(INIT);
    window.eval(MODAL_JS);
    return { window, sent, doc: window.document };
}

function choose(window, id) {
    const input = window.document.getElementById(id);
    input.checked = true;
    input.dispatchEvent(new window.Event("change", { bubbles: true }));
}

function pickFile(window, name, size, type) {
    const file = new window.File(["x"], name, { type: type || "" });
    if (size !== undefined) { Object.defineProperty(file, "size", { value: size }); }
    const input = window.document.getElementById("resourceFile");
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    input.dispatchEvent(new window.Event("change", { bubbles: true }));
    return file;
}

function submit(window) {
    const form = window.document.getElementById("resourceForm");
    form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
}

function errorItems(doc) {
    return [...doc.querySelectorAll("#resourceErrors li")].map((li) => li.textContent);
}

test("type switch updates hint, accept and which field is submitted", async () => {
    const { window, doc } = await page();
    try {
        choose(window, "typeVideo");
        assert.equal(doc.querySelector("[data-resource-file-hint]").textContent,
            "Dəstəklənən formatlar: MP4, MOV, WEBM, M4V · maks. 200 MB");
        assert.equal(doc.getElementById("resourceFile").getAttribute("accept"), ".mp4,.mov,.webm,.m4v");
        choose(window, "typeLink");
        assert.ok(doc.getElementById("fileUploadSection").classList.contains("d-none"));
        assert.ok(!doc.getElementById("urlInputSection").classList.contains("d-none"));
        assert.equal(doc.getElementById("resourceFile").disabled, true);
        assert.equal(doc.getElementById("resourceUrl").disabled, false);
    } finally {
        window.close();
    }
});

test("wrong extension and oversize video are rejected before any upload", async () => {
    const { window, doc, sent } = await page();
    try {
        choose(window, "typeVideo");
        pickFile(window, "setup.exe", 10);
        assert.deepEqual(errorItems(doc), [
            "Bu format «Video» üçün qəbul edilmir: .exe. İcazə verilənlər: MP4, MOV, WEBM, M4V",
        ]);
        submit(window);
        assert.equal(sent.length, 0);
        pickFile(window, "IMG_0189.MOV", 312 * MB, "video/quicktime");
        assert.deepEqual(errorItems(doc), ["Fayl çox böyükdür: 312 MB (maks. 200 MB)"]);
        assert.equal(doc.querySelector("[data-resource-file-name]").textContent, "IMG_0189.MOV");
        assert.equal(doc.querySelector("[data-resource-file-size]").textContent, "312 MB");
        submit(window);
        assert.equal(sent.length, 0);
    } finally {
        window.close();
    }
});

test("valid video uploads via XHR with progress, disabled button and success", async () => {
    const { window, doc, sent } = await page();
    try {
        choose(window, "typeVideo");
        pickFile(window, "IMG_0189.MOV", 80 * MB, "video/quicktime");
        assert.deepEqual(errorItems(doc), []);
        submit(window);
        assert.equal(sent.length, 1);
        const xhr = sent[0];
        assert.equal(xhr.url, "http://localhost/courses/resource-upload/1/");
        assert.equal(xhr.headers["X-Requested-With"], "XMLHttpRequest");
        const button = doc.querySelector("[data-resource-submit]");
        assert.equal(button.disabled, true);
        const progress = Object.assign(new window.Event("progress"), { lengthComputable: true, loaded: 40, total: 80 });
        xhr.upload.dispatchEvent(progress);
        assert.equal(doc.querySelector("[data-resource-progress]").hidden, false);
        assert.equal(doc.querySelector("[data-resource-progress-bar]").value, 50);
        assert.equal(doc.querySelector("[data-resource-progress-text]").textContent, "Yüklənir: 50%");
        submit(window); // ikinci göndərmə yoxdur
        assert.equal(sent.length, 1);
        xhr.respond(200, "application/json", JSON.stringify({ success: true, message: "Əlavə edildi" }));
        assert.equal(button.disabled, false);
        assert.deepEqual(window.notices, [["success", "Əlavə edildi"]]);
        assert.equal(window.hidden, 1);
    } finally {
        window.close();
    }
});

test("nginx HTML 413 shows a clear size message instead of the generic toast", async () => {
    const { window, doc, sent } = await page();
    try {
        choose(window, "typeVideo");
        pickFile(window, "IMG_0189.MOV", 150 * MB, "video/quicktime");
        submit(window);
        sent[0].respond(413, "text/html", "<html><body>413 Request Entity Too Large</body></html>");
        assert.deepEqual(errorItems(doc), ["Fayl serverin qəbul etdiyi ölçüdən böyükdür (maks. 200 MB)."]);
        assert.deepEqual(window.notices, []);
        assert.equal(doc.querySelector("[data-resource-submit]").disabled, false);
        assert.equal(doc.querySelector("[data-resource-progress]").hidden, true);
    } finally {
        window.close();
    }
});

test("server JSON field errors are shown as text (not HTML), network errors are explained", async () => {
    const { window, doc, sent } = await page();
    try {
        choose(window, "typeVideo");
        pickFile(window, "clip.mp4", 5 * MB, "video/mp4");
        submit(window);
        const payload = '<img src=x onerror="window.__xss=1"> uyğun deyil';
        sent[0].respond(400, "application/json", JSON.stringify({ success: false, errors: { file: [payload] } }));
        assert.deepEqual(errorItems(doc), [payload]);
        assert.equal(doc.querySelector("#resourceErrors img"), null);
        assert.equal(window.__xss, undefined);
        submit(window);
        sent[1].fire("error");
        assert.deepEqual(errorItems(doc), ["Bağlantı kəsildi"]);
        submit(window);
        sent[2].respond(502, "text/html", "<html>Bad Gateway</html>");
        assert.deepEqual(errorItems(doc), ["Vaxt (502)"]);
    } finally {
        window.close();
    }
});

test("modal cannot be dismissed mid-upload; cancel aborts the upload", async () => {
    const { window, doc, sent } = await page();
    try {
        choose(window, "typeVideo");
        pickFile(window, "clip.mp4", 5 * MB, "video/mp4");
        submit(window);
        const modal = doc.getElementById("resourceFormModal");
        const hide = new window.Event("hide.bs.modal", { cancelable: true });
        modal.dispatchEvent(hide);
        assert.equal(hide.defaultPrevented, true);
        doc.querySelector('[data-bs-dismiss="modal"]').dispatchEvent(new window.Event("click", { bubbles: true }));
        const hideAgain = new window.Event("hide.bs.modal", { cancelable: true });
        modal.dispatchEvent(hideAgain);
        assert.equal(hideAgain.defaultPrevented, false);
        assert.equal(doc.querySelector("[data-resource-submit]").disabled, false);
        assert.equal(sent.length, 1);
    } finally {
        window.close();
    }
});
