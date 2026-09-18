function countedLabelText(key, fallback, count) {
    return `${manuscriptT(key, fallback)} (${count})`;
}

function createBackCollapse(labelDatasetKey) {
    const wrap = document.createElement("details");
    wrap.className = "manuscript-field accordion-item";
    wrap.open = false;
    wrap.dataset.backCollapse = "1";
    const summary = document.createElement("summary");
    if (labelDatasetKey) {
        summary.dataset[labelDatasetKey] = "1";
    }
    const body = document.createElement("div");
    body.className = "accordion-body";
    wrap.appendChild(summary);
    wrap.appendChild(body);
    return { wrap, body, summary };
}

function updateReferencesLabel(referencesWrap) {
    const label = referencesWrap.querySelector("[data-references-label]");
    const list = referencesWrap.querySelector("[data-references-list]");
    if (!label || !list) {
        return;
    }
    label.textContent = countedLabelText(
        "references",
        "References",
        list.querySelectorAll("[data-reference-row]").length
    );
}

function renderBackEditor(container, references) {
    container.innerHTML = "";
    const referencesCollapse = createBackCollapse("referencesLabel");
    const referencesWrap = referencesCollapse.wrap;
    const list = document.createElement("div");
    list.dataset.referencesList = "1";
    (references || []).forEach((ref) => list.appendChild(createReferenceCard(ref)));
    referencesCollapse.body.appendChild(list);

    const addReference = document.createElement("button");
    addReference.type = "button";
    addReference.id = "back-add-reference";
    addReference.className = "btn btn-sm btn-secondary";
    addReference.textContent = manuscriptT("addReference", "Add reference");
    addReference.addEventListener("click", () => {
        list.appendChild(createReferenceCard({ mixed_citation: "", marked: {} }));
        updateReferencesLabel(referencesWrap);
    });
    referencesCollapse.body.appendChild(addReference);
    updateReferencesLabel(referencesWrap);
    container.appendChild(referencesWrap);
    return { list, referencesWrap };
}

function referencePayloadFromCard(card) {
    return {
        id: card.dataset.refId || null,
        mixed_citation: card.querySelector('[data-field="mixed_citation"]')?.value || "",
        marked: parseMarked(card.querySelector('[data-field="marked"]')?.value || "{}"),
    };
}

function parseMarked(value) {
    try {
        return JSON.parse(value);
    } catch (error) {
        return {};
    }
}

function createReferenceCard(ref) {
    const card = document.createElement("div");
    card.className = "card manuscript-ref-card";
    card.dataset.refId = ref.id || "";
    card.dataset.referenceRow = "1";

    const cardBody = document.createElement("div");
    cardBody.className = "card-body";

    const mixedField = document.createElement("div");
    mixedField.className = "manuscript-field";
    mixedField.innerHTML = `
        <label class="form-label">${escapeText(manuscriptT("mixedCitation", "Mixed citation"))}</label>
        <textarea class="form-control" rows="3" data-field="mixed_citation">${escapeText(ref.mixed_citation || "")}</textarea>
    `;
    cardBody.appendChild(mixedField);

    const markedCollapse = createBackCollapse("");
    markedCollapse.summary.textContent = manuscriptT(
        "structuredMarkedJson",
        "Structured marked (JSON)"
    );
    const markedField = document.createElement("div");
    markedField.className = "manuscript-field";
    markedField.innerHTML = `
        <textarea class="form-control" rows="6" data-field="marked">${escapeText(JSON.stringify(ref.marked || {}, null, 2))}</textarea>
    `;
    markedCollapse.body.appendChild(markedField);
    cardBody.appendChild(markedCollapse.wrap);

    const actions = document.createElement("div");
    actions.className = "manuscript-actions btn-group";
    const remarkButton = document.createElement("button");
    remarkButton.type = "button";
    remarkButton.className = "btn btn-sm btn-outline-primary";
    remarkButton.textContent = manuscriptT("remark", "Re-mark");
    remarkButton.addEventListener("click", () => remarkReference(card));
    actions.appendChild(remarkButton);

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "btn btn-sm btn-secondary";
    removeButton.textContent = manuscriptT("remove", "Remove");
    removeButton.addEventListener("click", () => {
        card.remove();
        const referencesWrap = card.closest("[data-back-collapse]");
        if (referencesWrap) {
            updateReferencesLabel(referencesWrap);
        }
    });
    actions.appendChild(removeButton);

    cardBody.appendChild(actions);
    card.appendChild(cardBody);
    return card;
}

async function remarkReference(card) {
    const config = window.manuscriptEditorConfig;
    const refId = card.dataset.refId;
    if (!refId || !config.remarkUrlTemplate) {
        window.manuscriptToast(
            manuscriptT(
                "saveBeforeRemark",
                "Save references before re-marking individual items"
            )
        );
        return;
    }
    const url = config.remarkUrlTemplate.replace("{id}", refId);
    const response = await fetch(url, {
        method: "POST",
        headers: { "X-CSRFToken": config.csrfToken },
    });
    const data = await response.json();
    if (!response.ok) {
        window.manuscriptToast(data.error || manuscriptT("remarkFailed", "Re-mark failed"));
        return;
    }
    card.querySelector('[data-field="mixed_citation"]').value = data.mixed_citation || "";
    card.querySelector('[data-field="marked"]').value = JSON.stringify(data.marked || {}, null, 2);
    window.manuscriptToast(manuscriptT("referenceRemarked", "Reference re-marked"));
}

function escapeText(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;");
}

document.addEventListener("DOMContentLoaded", () => {
    const config = window.manuscriptEditorConfig;
    if (!config || config.step !== "back") {
        return;
    }
    const container = document.getElementById("back-wysiwyg-editor");
    if (!container) {
        return;
    }
    const { list } = renderBackEditor(container, config.references || []);

    const saveButton = document.getElementById("back-save-draft");
    if (!saveButton) {
        return;
    }
    saveButton.addEventListener("click", async () => {
        const references = Array.from(list.querySelectorAll(".manuscript-ref-card")).map(
            referencePayloadFromCard
        );
        try {
            await window.manuscriptSaveJson(config.saveUrl, { references }, config.csrfToken);
            config.references = references;
            await window.manuscriptRefreshPreview(config.previewUrl);
            window.manuscriptToast(manuscriptT("referencesDraftSaved", "References draft saved"));
        } catch (error) {
            window.manuscriptToast(error.message);
        }
    });
});
