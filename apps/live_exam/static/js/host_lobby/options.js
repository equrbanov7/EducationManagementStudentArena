import { esc } from './utils.js';

export function optionTone(index) {
    return ["red", "blue", "yellow", "green"][index % 4];
}

const OPTION_SHAPES = ["triangle", "diamond", "circle", "square", "pentagon", "hexagon"];

export function optionShapeKey(option, index) {
    const fallback = OPTION_SHAPES[index % OPTION_SHAPES.length] || "circle";
    const raw = String(option?.shape || fallback).toLowerCase();
    return raw.replace(/[^a-z0-9_-]/g, "") || fallback;
}

export function optionMarkerLabel(option, index) {
    if (option?.shape_label) return option.shape_label;
    const shape = optionShapeKey(option, index).replace(/[-_]/g, " ");
    return shape.charAt(0).toUpperCase() + shape.slice(1);
}

export function optionMarkerMarkup(option, index, className) {
    const shape = optionShapeKey(option, index);
    const label = optionMarkerLabel(option, index);
    return `
        <span class="${className} ${className}--shape" aria-label="${esc(label)}" title="${esc(label)}">
            <span class="answer-shape answer-shape--${shape}" aria-hidden="true"></span>
        </span>
    `;
}

export function answerOptionMarkup(option, index) {
    return `
        <article class="host-option host-option--${optionTone(index)}">
            <div class="host-option__main">
                ${optionMarkerMarkup(option, index, "host-option__label")}
                <span class="host-option__text">${esc(option?.text || "")}</span>
            </div>
        </article>
    `;
}

export function revealOptionMarkup(option, index, distribution, correctOptionIds) {
    const optionId = Number(option?.id || 0);
    const isCorrect = correctOptionIds.includes(optionId);

    return `
        <article class="host-option host-option--${optionTone(index)} is-reveal ${isCorrect ? "is-correct" : "is-wrong"}">
            <div class="host-option__main">
                ${optionMarkerMarkup(option, index, "host-option__label")}
                <span class="host-option__text">${esc(option?.text || "")}</span>
                <span class="host-option__verdict">${isCorrect ? "✓" : "✕"}</span>
            </div>
        </article>
    `;
}

export function distributionBarMarkup(option, index, distribution, correctOptionIds) {
    const optionId = Number(option?.id || 0);
    const count = Number(distribution.counts.get(optionId) || 0);
    const totalAnswers = Math.max(0, Number(distribution.totalAnswers || 0));
    const ratio = totalAnswers > 0 ? Math.round((count / totalAnswers) * 100) : 0;
    const isCorrect = correctOptionIds.includes(optionId);

    return `
        <div class="distribution-bar distribution-bar--${optionTone(index)} ${isCorrect ? "is-correct" : ""}">
            <div class="distribution-bar__meta">
                <div class="distribution-bar__label-wrap">
                    ${optionMarkerMarkup(option, index, "distribution-bar__label")}
                    <span class="distribution-bar__answer">${esc(option?.text || "")}</span>
                </div>
                <div class="distribution-bar__stats">
                    <span>${count}</span>
                    <span>${ratio}%</span>
                    ${isCorrect ? '<span class="distribution-bar__correct">✓</span>' : ""}
                </div>
            </div>
            <div class="distribution-bar__track" aria-hidden="true">
                <span style="width:${ratio}%"></span>
            </div>
        </div>
    `;
}
