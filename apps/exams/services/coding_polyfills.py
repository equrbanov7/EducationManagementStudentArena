"""Source-level shims injected into sandboxed runtimes before execution.

The shims live as plain Python string constants so they can be unit-tested
without spinning up Docker, and so the contract between backend injection
and the frontend transcript layer is easy to read in one place.

Currently we only need a Node.js polyfill — Python, C++, and Java all have
the input primitives students expect.
"""

# Node.js sandbox lacks browser-only globals such as `prompt`, `alert`, and
# `confirm`. Students commonly write `prompt("...")` because that is what
# they learned in browser JS. We inject a tiny shim that reads from
# process.stdin so the same code works inside the Docker sandbox without
# rewriting it.
#
# Output mirrors how Python input() behaves: emit the prompt to stdout,
# return the next stdin line as the value. The frontend transcript layer
# is responsible for splicing the user's typed value back into the visible
# terminal output, so we deliberately do NOT echo the value here (that
# would double it).
NODE_PROMPT_POLYFILL = (
    "// EMSArena: prompt()/alert()/confirm() polyfill for Node sandbox.\n"
    "// Injected automatically — does not appear in the student's saved code.\n"
    "// Output mirrors how Python input() behaves: emit the prompt to stdout,\n"
    "// return the next stdin line as the value. The frontend transcript layer\n"
    "// is responsible for splicing the user's typed value back into the visible\n"
    "// terminal output, so we deliberately do NOT echo the value here (that\n"
    "// would double it).\n"
    "(function () {\n"
    "    if (typeof globalThis.prompt === 'function') { return; }\n"
    "    var __ems_stdin_chunks = [];\n"
    "    try {\n"
    "        var fs = require('fs');\n"
    "        var data = fs.readFileSync(0, 'utf-8');\n"
    "        __ems_stdin_chunks = data.replace(/\\r\\n/g, '\\n').split('\\n');\n"
    "        if (__ems_stdin_chunks.length && __ems_stdin_chunks[__ems_stdin_chunks.length - 1] === '') {\n"
    "            __ems_stdin_chunks.pop();\n"
    "        }\n"
    "    } catch (err) { __ems_stdin_chunks = []; }\n"
    "    var __ems_idx = 0;\n"
    "    function nextChunk() {\n"
    "        return __ems_idx < __ems_stdin_chunks.length ? __ems_stdin_chunks[__ems_idx++] : null;\n"
    "    }\n"
    "    globalThis.prompt = function (message) {\n"
    "        if (message !== undefined && message !== null && message !== '') {\n"
    "            try { process.stdout.write(String(message)); } catch (e) {}\n"
    "        }\n"
    "        return nextChunk();\n"
    "    };\n"
    "    globalThis.alert = function (message) {\n"
    "        try { process.stdout.write(String(message == null ? '' : message) + '\\n'); } catch (e) {}\n"
    "    };\n"
    "    globalThis.confirm = function (message) {\n"
    "        if (message !== undefined && message !== null && message !== '') {\n"
    "            try { process.stdout.write(String(message)); } catch (e) {}\n"
    "        }\n"
    "        var value = nextChunk();\n"
    "        return /^(y|yes|true|1)$/i.test(String(value || '').trim());\n"
    "    };\n"
    "    globalThis.readline = function () {\n"
    "        return nextChunk() || '';\n"
    "    };\n"
    "})();\n\n"
)


def javascript_main_has_top_level_input_loop(content: str) -> bool:
    """True when the student already wired their own prompt shim.

    Used to avoid double-injecting the polyfill on top of code that has
    already declared a `globalThis.prompt` (or similar) override.
    """
    return "globalThis.prompt" in (content or "")
