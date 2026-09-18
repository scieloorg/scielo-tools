function countedLabelText(key, fallback, count) {
    return `${manuscriptT(key, fallback)} (${count})`;
}

function createBodyCollapse(labelDatasetKey) {
    const wrap = document.createElement("details");
    wrap.className = "manuscript-field accordion-item";
    wrap.open = false;
    wrap.dataset.bodyCollapse = "1";
    const summary = document.createElement("summary");
    summary.dataset[labelDatasetKey] = "1";
    const body = document.createElement("div");
    body.className = "accordion-body";
    wrap.appendChild(summary);
    wrap.appendChild(body);
    return { wrap, body };
}

function updateParagraphsLabel(paragraphsWrap) {
    const label = paragraphsWrap.querySelector("[data-paragraphs-label]");
    const list = paragraphsWrap.querySelector("[data-paragraphs-list]");
    if (!label || !list) {
        return;
    }
    label.textContent = countedLabelText(
        "paragraphs",
        "Paragraphs",
        list.querySelectorAll("[data-paragraph-block]").length
    );
}

function bodyMarkedFromEditor(root, marked) {
    const data = JSON.parse(JSON.stringify(marked || {}));
    data.sections = [];
    root.querySelectorAll("[data-section-row]").forEach((row) => {
        const section = {
            title: row.querySelector('[data-field="title"]')?.value || "",
            content: [],
            sections: [],
        };
        row.querySelectorAll("[data-paragraph-block]").forEach((block) => {
            section.content.push({
                type: "p",
                text: block.textContent.trim(),
            });
        });
        data.sections.push(section);
    });
    return data;
}

function applyRichCommand(block, command) {
    document.execCommand(command, false, null);
    block.focus();
}

function createParagraphBlock(text) {
    const block = document.createElement("div");
    block.className = "manuscript-rich-block";
    block.contentEditable = "true";
    block.dataset.paragraphBlock = "1";
    block.innerHTML = text || "";
    const toolbar = document.createElement("div");
    toolbar.className = "manuscript-toolbar btn-group";
    ["bold", "italic", "superscript", "subscript"].forEach((command) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-sm btn-secondary";
        button.textContent = command.slice(0, 1).toUpperCase();
        button.addEventListener("mousedown", (event) => {
            event.preventDefault();
            applyRichCommand(block, command);
        });
        toolbar.appendChild(button);
    });
    const wrap = document.createElement("div");
    wrap.appendChild(toolbar);
    wrap.appendChild(block);
    return wrap;
}

function createSectionRow(section) {
    const row = document.createElement("div");
    row.className = "card manuscript-section-card";
    row.dataset.sectionRow = "1";

    const titleField = document.createElement("div");
    titleField.className = "card-body";
    const titleInner = document.createElement("div");
    titleInner.className = "manuscript-field";
    titleInner.innerHTML = `
        <label class="form-label">${escapeText(manuscriptT("sectionTitle", "Section title"))}</label>
        <input class="form-control" type="text" data-field="title" value="${escapeAttr(section.title || "")}">
    `;
    titleField.appendChild(titleInner);

    const paragraphsCollapse = createBodyCollapse("paragraphsLabel");
    const paragraphsWrap = paragraphsCollapse.wrap;
    const paragraphsList = document.createElement("div");
    paragraphsList.dataset.paragraphsList = "1";
    const blocks = section.content || [{ type: "p", text: "" }];
    blocks
        .filter((block) => block.type === "p")
        .forEach((block) => {
            paragraphsList.appendChild(createParagraphBlock(block.text || ""));
        });
    if (!paragraphsList.querySelector("[data-paragraph-block]")) {
        paragraphsList.appendChild(createParagraphBlock(""));
    }
    paragraphsCollapse.body.appendChild(paragraphsList);
    const addParagraph = document.createElement("button");
    addParagraph.type = "button";
    addParagraph.className = "btn btn-sm btn-secondary";
    addParagraph.textContent = manuscriptT("addParagraph", "Add paragraph");
    addParagraph.addEventListener("click", () => {
        paragraphsList.appendChild(createParagraphBlock(""));
        updateParagraphsLabel(paragraphsWrap);
    });
    paragraphsCollapse.body.appendChild(addParagraph);
    updateParagraphsLabel(paragraphsWrap);
    titleField.appendChild(paragraphsWrap);

    row.appendChild(titleField);

    return row;
}

function escapeAttr(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;");
}

function escapeText(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;");
}

function renderBodyEditor(container, marked) {
    container.innerHTML = "";
    const sections = (marked && marked.sections) || [
        { title: "", content: [{ type: "p", text: "" }], sections: [] },
    ];
    const list = document.createElement("div");
    sections.forEach((section) => list.appendChild(createSectionRow(section)));
    container.appendChild(list);

    const addSection = document.createElement("button");
    addSection.type = "button";
    addSection.className = "btn btn-sm btn-secondary";
    addSection.textContent = manuscriptT("addSection", "Add section");
    addSection.addEventListener("click", () => {
        list.appendChild(
            createSectionRow({ title: "", content: [{ type: "p", text: "" }], sections: [] })
        );
    });
    container.appendChild(addSection);
}

document.addEventListener("DOMContentLoaded", () => {
    const config = window.manuscriptEditorConfig;
    if (!config || config.step !== "body") {
        return;
    }
    const container = document.getElementById("body-wysiwyg-editor");
    if (!container) {
        return;
    }
    renderBodyEditor(container, config.marked || {});

    const saveButton = document.getElementById("body-save-draft");
    if (!saveButton) {
        return;
    }
    saveButton.addEventListener("click", async () => {
        const marked = bodyMarkedFromEditor(container, config.marked);
        try {
            await window.manuscriptSaveJson(config.saveUrl, { marked }, config.csrfToken);
            config.marked = marked;
            await window.manuscriptRefreshPreview(config.previewUrl);
            window.manuscriptToast(manuscriptT("bodyDraftSaved", "Body draft saved"));
        } catch (error) {
            window.manuscriptToast(error.message);
        }
    });
});
