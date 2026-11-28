// Resource URLs come from Django's static manifest. Each subject loads on first use.
const mounted = new WeakSet();
const subjects = new Set(["physics", "chemistry", "mathematics", "biology", "astronomy"]);

function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text != null) element.textContent = text;
    return element;
}

function setupRoom(root) {
    if (!root || mounted.has(root)) return;
    mounted.add(root);
    const get = key => root.querySelector("[data-" + key + "]");
    const catalog = get("catalog");
    const work = get("work");
    const bench = get("bench");
    const shelf = get("tools");
    const rangeBox = get("controls");
    const locale = root.lang || document.documentElement.lang || "az";
    const formatter = new Intl.NumberFormat(locale, {maximumFractionDigits: 4});
    const local = value => (value && typeof value === "object" ? value[locale] ?? value.az : value) ?? "";
    const cards = Array.from(catalog.querySelectorAll("[data-experiment]"));
    const filters = Array.from(catalog.querySelectorAll("[data-filter]"));
    let experiment;
    let modelLang = "az";
    let opener;
    let state;
    let pending = 0;
    let gesture;
    let ignoreMouseClick = false;

    function addSubjectStyles(subject) {
        if (subject !== "biology" && subject !== "chemistry") return;
        const href = root.dataset.bioCss;
        if (!href || Array.from(document.querySelectorAll('link[rel="stylesheet"]')).some(link => link.href === new URL(href, document.baseURI).href)) return;
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        document.head.append(link);
    }

    function initialState() {
        const values = Object.fromEntries(experiment.controls.map(control => [control.id, Number(control.value)]));
        return {...values, ...experiment.defaults, runs: 0};
    }

    function formattedControl(control) {
        const choice = control.choices?.find(item => Number(item.value) === state[control.id]);
        if (choice) return local(choice.label);
        return [formatter.format(state[control.id]), local(control.unit)].filter(Boolean).join(" ");
    }

    function clearHistory() {
        get("history-rows").replaceChildren();
        get("history").hidden = true;
    }

    function recordRun(results) {
        const row = node("tr");
        const number = node("th", null, formatter.format(state.runs));
        number.scope = "row";
        const conditions = node("td");
        const measurements = node("td");
        conditions.lang = measurements.lang = modelLang;
        const tool = experiment.tools.find(option => option.id === state.tool);
        conditions.append(node("strong", null, local(tool?.label)));
        for (const control of experiment.controls) {
            conditions.append(node("span", null, local(control.label) + " · " + formattedControl(control)));
        }
        for (const result of results) {
            measurements.append(node("span", null, local(result.label) + " · " + local(result.value)));
        }
        row.append(number, conditions, measurements);
        const rows = get("history-rows");
        rows.prepend(row);
        if (rows.children.length > 4) rows.lastElementChild.remove();
        get("history").hidden = false;
    }

    function draw(announce = false) {
        const scene = experiment.render({...state, lang: locale});
        const svg = get("svg");
        svg.setAttribute("aria-label", local(experiment.title));
        // Subject modules ship with the application and return their own SVG markup.
        svg.innerHTML = scene.svg;
        const rows = scene.results.map(result => {
            const row = node("div", "sr-measure");
            row.append(node("dt", null, local(result.label)), node("dd", null, local(result.value)));
            return row;
        });
        get("results").replaceChildren(...rows);
        get("explanation").textContent = local(scene.explanation);
        get("count").textContent = state.runs ? root.dataset.runCaption + " " + formatter.format(state.runs) : "";
        if (announce) {
            const readings = node("span", null, rows.map(row => Array.from(row.children, el => el.textContent).join(" ")).join(". "));
            readings.lang = modelLang;
            get("announce").replaceChildren(get("count").textContent + " ", readings);
        }
        const selected = [];
        shelf.querySelectorAll("[data-shelf-item]").forEach(button => {
            const control = button.dataset.choiceControl;
            const active = control ? Number(button.value) === state[control] : button.dataset.tool === state.tool;
            button.setAttribute("aria-pressed", String(active));
            if (active) selected.push(button.textContent);
        });
        get("active-tool").textContent = selected.join(" · ");
        for (const control of experiment.controls) {
            if (control.choices?.length) continue;
            const slider = rangeBox.querySelector('[name="' + control.id + '"]');
            slider.value = state[control.id];
            const display = formattedControl(control);
            slider.setAttribute("aria-valuetext", display);
            slider.parentElement.querySelector("output").textContent = display;
        }
        return scene.results;
    }

    function shelfButton(label) {
        const button = node("button", "sr-tool", local(label));
        button.type = "button";
        button.lang = modelLang;
        button.dataset.shelfItem = "";
        return button;
    }

    function mountControls() {
        const tools = node("div", "sr-items");
        tools.dataset.selectionGroup = "";
        for (const tool of experiment.tools) {
            const button = shelfButton(tool.label);
            button.dataset.tool = tool.id;
            tools.append(button);
        }
        shelf.replaceChildren(tools);
        const sliders = [];
        for (const control of experiment.controls) {
            if (control.choices?.length) {
                const group = node("fieldset", "sr-material");
                const legend = node("legend", null, local(control.label));
                legend.lang = modelLang;
                const options = node("div", "sr-items");
                options.dataset.selectionGroup = "";
                for (const choice of control.choices) {
                    const button = shelfButton(choice.label);
                    button.dataset.choiceControl = control.id;
                    button.value = String(choice.value);
                    options.append(button);
                }
                group.append(legend, options);
                shelf.append(group);
                continue;
            }
            const label = node("label", "sr-control");
            label.lang = modelLang;
            const slider = node("input");
            slider.type = "range";
            slider.name = control.id;
            slider.min = control.min;
            slider.max = control.max;
            slider.step = control.step;
            slider.setAttribute("aria-label", local(control.label));
            slider.addEventListener("input", () => {
                state[control.id] = slider.valueAsNumber;
                draw();
            });
            const output = node("output");
            output.setAttribute("aria-hidden", "true");
            label.append(node("span", null, local(control.label)), output, slider);
            sliders.push(label);
        }
        rangeBox.replaceChildren(...sliders);
    }

    async function openCard(card) {
        const subject = card.dataset.subject;
        if (!subjects.has(subject)) return;
        const request = ++pending;
        catalog.setAttribute("aria-busy", "true");
        get("feedback").textContent = root.dataset.loading;
        try {
            addSubjectStyles(subject);
            const module = await import(root.dataset[subject]);
            if (request !== pending || !root.isConnected) return;
            experiment = module.experiments[card.dataset.experiment];
            modelLang = experiment.lang || (typeof experiment.title === "object" && experiment.title[locale] ? locale : "az");
            for (const key of ["title", "prompt", "setup", "svg", "active-tool", "results", "explanation"]) {
                get(key).setAttribute("lang", modelLang);
            }
            opener = card;
            state = initialState();
            work.dataset.subject = subject;
            get("context").textContent = card.querySelector(".sr-subject").textContent;
            get("title").textContent = local(experiment.title);
            get("prompt").textContent = local(experiment.prompt);
            get("setup").textContent = local(experiment.setup);
            get("announce").textContent = "";
            clearHistory();
            mountControls();
            draw();
            work.hidden = false;
            catalog.hidden = true;
            get("feedback").textContent = "";
            get("title").focus({preventScroll: true});
            root.scrollIntoView({block: "start"});
        } catch {
            if (request === pending) get("feedback").textContent = root.dataset.error;
        } finally {
            if (request === pending) catalog.removeAttribute("aria-busy");
        }
    }

    function selectItem(button) {
        if (!button || !experiment || !shelf.contains(button)) return;
        if (button.dataset.choiceControl) {
            state[button.dataset.choiceControl] = Number(button.value);
        } else {
            state.tool = button.dataset.tool;
        }
        draw();
    }

    filters.forEach(button => button.addEventListener("click", () => {
        ++pending;
        catalog.removeAttribute("aria-busy");
        get("feedback").textContent = "";
        filters.forEach(filter => filter.setAttribute("aria-pressed", String(filter === button)));
        cards.forEach(card => {
            card.hidden = button.dataset.filter !== "all" && card.dataset.subject !== button.dataset.filter;
        });
    }));
    cards.forEach(card => card.addEventListener("click", () => openCard(card)));
    get("back").addEventListener("click", () => {
        ++pending;
        work.hidden = true;
        catalog.hidden = false;
        get("svg").replaceChildren();
        opener?.focus();
    });
    get("run").addEventListener("click", () => { state.runs += 1; recordRun(draw(true)); });
    get("reset").addEventListener("click", () => { state = initialState(); clearHistory(); draw(true); });
    shelf.addEventListener("click", event => {
        if (ignoreMouseClick && event.detail) return;
        selectItem(event.target.closest("[data-shelf-item]"));
    });
    shelf.addEventListener("keydown", event => {
        const step = {ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1}[event.key];
        if (!step) return;
        const group = event.target.closest("[data-selection-group]");
        if (!group) return;
        const buttons = Array.from(group.querySelectorAll("[data-shelf-item]"));
        const index = buttons.indexOf(event.target);
        if (index < 0) return;
        event.preventDefault();
        const next = buttons[(index + step + buttons.length) % buttons.length];
        next.focus();
        selectItem(next);
    });

    function overBench(event) {
        const rect = bench.getBoundingClientRect();
        return event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
    }
    function endGesture(event) {
        if (gesture?.id !== event.pointerId) return;
        const {button, dragging} = gesture;
        gesture = null;
        shelf.removeAttribute("data-dragging");
        bench.removeAttribute("data-drop");
        if (!dragging) return;
        ignoreMouseClick = true;
        if (event.type === "pointerup" && overBench(event)) selectItem(button);
        window.setTimeout(() => { ignoreMouseClick = false; }, 0);
    }
    shelf.addEventListener("pointerdown", event => {
        const button = event.target.closest("[data-shelf-item]");
        if (!button || event.button !== 0 || !event.isPrimary) return;
        gesture = {button, id: event.pointerId, x: event.clientX, y: event.clientY, dragging: false};
        button.setPointerCapture(event.pointerId);
    });
    shelf.addEventListener("pointermove", event => {
        if (gesture?.id !== event.pointerId) return;
        if (!gesture.dragging && Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) < 6) return;
        gesture.dragging = true;
        shelf.setAttribute("data-dragging", "");
        bench.dataset.drop = overBench(event) ? "ready" : "target";
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach(type => shelf.addEventListener(type, endGesture));
}

document.querySelectorAll("[data-science-room]").forEach(setupRoom);
document.addEventListener("profile:section:loaded", event => {
    if (event.detail?.section === "science-room") setupRoom(event.detail.panel);
});
