"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const ROOT = path.resolve(__dirname, "../..");
const source = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/applications_content.js"), "utf8");
const dialog = fs.readFileSync(path.join(ROOT, "apps/accounts/templates/accounts/profile/sections/_applications_content_dialog.html"), "utf8");
function setup() {
    const dom = new JSDOM('<div id="root">' + dialog + '<button data-apx-edit-reply="e1">Edit</button></div>', { runScripts: "outside-only" });
    const w = dom.window;
    w.EMSDelegate = { on(type, selector, fn) { w.document.addEventListener(type, event => { const node = event.target.closest(selector); if (node) { fn(event, node); } }); } };
    const root = w.document.getElementById("root");
    const posts = [];
    const ns = w.EMSApplications = { root, api: {}, t: key => key, esc: text => String(text), dateTime: text => text,
        current: { id: "a1", subject: "Subject", body: "Body", updated_at: "stamp1", events: [{ id: "e1", text: "Correct current reply", revision: "r2", can_moderate: true }] },
        submitAction: (id, action, fields) => { posts.push({ id, action, fields }); return Promise.resolve({}); },
        dialogs: { open: () => { const box = root.querySelector("[data-apx-dialog]"); box.hidden = false; return box; }, close: () => {}, showErrors: () => {} }
    };
    w.eval(source);
    return { dom, w, ns, posts };
}

test("reply editor sends the exact event and revision, not a different active request", async () => {
    const { dom, w, ns, posts } = setup();
    w.document.querySelector("[data-apx-edit-reply]").click();
    assert.equal(w.document.querySelector("textarea").value, "Correct current reply");
    assert.equal(w.document.querySelector("[data-apx-content-title]").textContent, "editReply");
    assert.equal(w.document.querySelector("[data-apx-content-subject-field]").hidden, true);
    w.document.querySelector("textarea").value = "Amended reply";
    ns.current = { id: "other-request" };
    w.document.querySelector("[data-apx-content-save]").click();
    await Promise.resolve();
    assert.equal(posts[0].id, "a1");
    assert.equal(posts[0].action, "edit_reply");
    assert.equal(posts[0].fields.event, "e1");
    assert.equal(posts[0].fields.revision, "r2");
    assert.equal(posts[0].fields.text, "Amended reply");
    dom.window.close();
});

test("deleted request shows restore only when server permits it", () => {
    const { dom, ns } = setup();
    const hidden = { deleted_at: "stamp", content_actions: { can_restore: true } };
    const html = ns.contentButtons(hidden);
    assert.match(html, /data-apx-restore-application/);
    assert.match(html, /restoreApplication/);
    assert.doesNotMatch(html, /data-apx-delete-application|data-apx-edit-application/);
    assert.doesNotMatch(ns.contentButtons({ content_actions: {} }), /<button/);
    dom.window.close();
});
