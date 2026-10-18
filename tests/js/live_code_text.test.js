/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-19: canlı imtahanda kod nümunəsi (host_lobby/code_text.js) — sətirlər
   birləşmir, girinti saxlanılır, ```…``` açıq blokdur, istifadəçi mətni HTML kimi
   şərh olunmur. SAF ES modulu — data: URL ilə OLDUĞU KİMİ import olunur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const FILE = path.join(ROOT, "apps/live_exam/static/js/host_lobby/code_text.js");

let modPromise = null;
function load() {
    if (!modPromise) {
        const src = fs.readFileSync(FILE, "utf8");
        modPromise = import("data:text/javascript;base64," + Buffer.from(src).toString("base64"));
    }
    return modPromise;
}

const kinds = (segments) => segments.map((s) => s.type);

test("plain prose stays a single text segment (line breaks kept verbatim)", async () => {
    const { splitCodeSegments, hasCodeBlock } = await load();
    const text = "Azərbaycanın paytaxtı hansıdır?\nVariantlardan birini seçin.";
    assert.deepEqual(splitCodeSegments(text), [{ type: "text", text }]);
    assert.equal(hasCodeBlock(text), false);
    assert.equal(hasCodeBlock(""), false);
    assert.equal(hasCodeBlock(null), false);
});

test("fenced ``` block is code with its language; indentation kept, common indent removed", async () => {
    const { splitCodeSegments } = await load();
    const segments = splitCodeSegments("Nəticə nədir?\n```python\n  for i in range(3):\n      print(i)\n```\nSeçin.");
    assert.deepEqual(kinds(segments), ["text", "code", "text"]);
    assert.equal(segments[0].text, "Nəticə nədir?");
    assert.equal(segments[1].lang, "python");
    assert.equal(segments[1].text, "for i in range(3):\n    print(i)");
    assert.equal(segments[2].text, "Seçin.");
});

test("unclosed fence runs to the end; a single fenced line is still code", async () => {
    const { splitCodeSegments } = await load();
    assert.deepEqual(splitCodeSegments("```\nx++"), [{ type: "code", text: "x++", lang: "" }]);
    assert.deepEqual(kinds(splitCodeSegments("A:\n```js\nlet a = 1;\n```")), ["text", "code"]);
});

test("pasted code without fences is detected (C-like and Python), prose before it stays text", async () => {
    const { splitCodeSegments } = await load();
    const c = splitCodeSegments(
        "Aşağıdakı kodun nəticəsi nədir:\n#include <stdio.h>\nint main() {\n    int x = 5;\n\n    printf(\"%d\", x);\n    return 0;\n}"
    );
    assert.deepEqual(kinds(c), ["text", "code"]);
    assert.equal(c[0].text, "Aşağıdakı kodun nəticəsi nədir:");
    assert.match(c[1].text, /^#include <stdio.h>\nint main\(\) \{\n    int x = 5;\n\n    printf/);
    assert.ok(c[1].text.endsWith("    return 0;\n}"));

    const py = splitCodeSegments("x = 5\nfor i in range(3):\n    x += i\nprint(x)\nCavab neçədir?");
    assert.deepEqual(kinds(py), ["code", "text"]);
    assert.equal(py[0].text, "x = 5\nfor i in range(3):\n    x += i\nprint(x)");
    assert.equal(py[1].text, "Cavab neçədir?");
});

test("prose is not mistaken for code (single code-ish line, indented list, names in brackets)", async () => {
    const { hasCodeBlock } = await load();
    assert.equal(hasCodeBlock("x = 5 olarsa, 2x + 3 neçədir?"), false);
    assert.equal(hasCodeBlock("Hansı doğrudur?\n  a) birinci\n  b) ikinci"), false);
    assert.equal(hasCodeBlock("Ali (tələbə)\nVəli (müəllim)"), false);
    assert.equal(hasCodeBlock("Cavab:\nBakı"), false);
});

test("renderCodeText builds DOM with textContent only — markup in the text stays inert text", async () => {
    const { renderCodeText } = await load();
    const dom = new JSDOM("<!doctype html><h2 id=q></h2>");
    const el = dom.window.document.getElementById("q");
    const evil = 'Nə çap olunur?\n```html\n<img src=x onerror="alert(1)">\n<script>alert(2)</script>\n```';
    assert.equal(renderCodeText(el, evil), true);
    assert.equal(el.querySelector("img"), null);
    assert.equal(el.querySelector("script"), null);
    const code = el.querySelector("code.lx-code");
    assert.ok(code);
    assert.equal(code.dataset.lang, "html");
    assert.equal(code.getAttribute("translate"), "no");
    assert.equal(code.textContent, '<img src=x onerror="alert(1)">\n<script>alert(2)</script>');
    assert.equal(el.querySelector(".lx-code-text").textContent, "Nə çap olunur?");
    assert.ok(el.classList.contains("has-code"));
});

test("hydrateCodeText upgrades escaped markup once and leaves plain text untouched", async () => {
    const { hydrateCodeText } = await load();
    const dom = new JSDOM(
        "<!doctype html><div id=root>" +
            '<h2 data-code-text id=a>Kod:\n```\nif (a) {\n  b();\n}\n```</h2>' +
            "<p data-code-text id=b>Sadə sual\nikinci sətir</p>" +
            "<span data-code-text id=c>&lt;b&gt;qalın deyil&lt;/b&gt;</span>" +
            "</div>"
    );
    const doc = dom.window.document;
    hydrateCodeText(doc.getElementById("root"));
    const a = doc.getElementById("a");
    assert.equal(a.querySelector("code.lx-code").textContent, "if (a) {\n  b();\n}");
    assert.equal(a.dataset.codeText, "done");
    const b = doc.getElementById("b");
    assert.equal(b.children.length, 0);
    assert.equal(b.textContent, "Sadə sual\nikinci sətir");
    const c = doc.getElementById("c");
    assert.equal(c.querySelector("b"), null);
    assert.equal(c.textContent, "<b>qalın deyil</b>");
    // ikinci çağırış heç nəyi dəyişmir (idempotent)
    const before = a.innerHTML;
    hydrateCodeText(doc.getElementById("root"));
    assert.equal(a.innerHTML, before);
    hydrateCodeText(null);
});

test("CRLF input is normalised", async () => {
    const { splitCodeSegments } = await load();
    const segments = splitCodeSegments("S:\r\n```\r\na = 1;\r\nb = 2;\r\n```");
    assert.deepEqual(segments[1], { type: "code", text: "a = 1;\nb = 2;", lang: "" });
});
