function mainTitle(marked) {
    const titles = marked.titles || [];
    const main = titles.find((item) => item.kind === "main") || titles[0];
    return main ? main.text || "" : "";
}

function setMainTitle(marked, value) {
    const data = marked;
    data.titles = data.titles || [];
    let main = data.titles.find((item) => item.kind === "main");
    if (!main) {
        main = { kind: "main", text: value, language: "en" };
        data.titles.unshift(main);
    } else {
        main.text = value;
    }
    return data;
}

function articleDoi(marked) {
    const ids = marked.article_ids || [];
    const doi = ids.find((item) => item.pub_id_type === "doi");
    return doi ? doi.value || "" : "";
}

function setArticleDoi(marked, value) {
    const data = marked;
    data.article_ids = data.article_ids || [];
    let doi = data.article_ids.find((item) => item.pub_id_type === "doi");
    if (!doi) {
        doi = { pub_id_type: "doi", value };
        data.article_ids.push(doi);
    } else {
        doi.value = value;
    }
    return data;
}

function defaultAbstractTitle() {
    return manuscriptT("abstract", "Abstract");
}

function defaultKeywordsTitle() {
    return manuscriptT("keywords", "Keywords");
}

function countedLabelText(key, fallback, count) {
    return `${manuscriptT(key, fallback)} (${count})`;
}

function createFrontCollapse(labelDatasetKey) {
    const wrap = document.createElement("details");
    wrap.className = "manuscript-field accordion-item";
    wrap.open = false;
    wrap.dataset.frontCollapse = "1";
    const summary = document.createElement("summary");
    summary.dataset[labelDatasetKey] = "1";
    const body = document.createElement("div");
    body.className = "accordion-body";
    wrap.appendChild(summary);
    wrap.appendChild(body);
    return { wrap, body };
}

function updateAuthorsLabel(authorsWrap) {
    const label = authorsWrap.querySelector("[data-authors-label]");
    const list = authorsWrap.querySelector("[data-authors-list]");
    if (!label || !list) {
        return;
    }
    label.textContent = countedLabelText(
        "authors",
        "Authors",
        list.querySelectorAll("[data-author-row]").length
    );
}

function updateAbstractsLabel(abstractsWrap) {
    const label = abstractsWrap.querySelector("[data-abstracts-label]");
    const list = abstractsWrap.querySelector("[data-abstracts-list]");
    if (!label || !list) {
        return;
    }
    label.textContent = countedLabelText(
        "abstracts",
        "Abstracts",
        list.querySelectorAll("[data-abstract-row]").length
    );
}

function keywordItemCount(list) {
    let total = 0;
    list.querySelectorAll("[data-keyword-row]").forEach((row) => {
        const raw = row.querySelector('[data-field="items"]')?.value || "";
        raw.split(",")
            .map((item) => item.trim())
            .filter(Boolean)
            .forEach(() => {
                total += 1;
            });
    });
    return total;
}

function updateKeywordsLabel(keywordsWrap) {
    const label = keywordsWrap.querySelector("[data-keywords-label]");
    const list = keywordsWrap.querySelector("[data-keywords-list]");
    if (!label || !list) {
        return;
    }
    label.textContent = countedLabelText("keywords", "Keywords", keywordItemCount(list));
}

function filledHistoryCount(list) {
    let total = 0;
    list.querySelectorAll("[data-history-row]").forEach((row) => {
        const year = (row.querySelector('[data-field="year"]')?.value || "").trim();
        if (year) {
            total += 1;
        }
    });
    return total;
}

function updateHistoryLabel(historyWrap) {
    const label = historyWrap.querySelector("[data-history-label]");
    const list = historyWrap.querySelector("[data-history-list]");
    if (!label || !list) {
        return;
    }
    label.textContent = countedLabelText("history", "History", filledHistoryCount(list));
}

function frontMarkedFromForm(root, marked) {
    let data = JSON.parse(JSON.stringify(marked || {}));
    data = setMainTitle(data, root.querySelector('[data-field="article_title"]')?.value || "");
    data = setArticleDoi(data, root.querySelector('[data-field="doi"]')?.value || "");

    data.authors = [];
    root.querySelectorAll("[data-author-row]").forEach((row) => {
        data.authors.push({
            contrib_type: "author",
            surname: row.querySelector('[data-field="surname"]')?.value || "",
            given_names: row.querySelector('[data-field="given_names"]')?.value || "",
        });
    });

    data.abstracts = [];
    root.querySelectorAll("[data-abstract-row]").forEach((row) => {
        data.abstracts.push({
            kind: "main",
            language: row.querySelector('[data-field="language"]')?.value || "",
            title: row.querySelector('[data-field="title"]')?.value || defaultAbstractTitle(),
            text: row.querySelector('[data-field="text"]')?.value || "",
        });
    });

    data.keywords = [];
    root.querySelectorAll("[data-keyword-row]").forEach((row) => {
        data.keywords.push({
            language: row.querySelector('[data-field="language"]')?.value || "",
            title: row.querySelector('[data-field="title"]')?.value || defaultKeywordsTitle(),
            keywords: (row.querySelector('[data-field="items"]')?.value || "")
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
        });
    });

    data.history = [];
    root.querySelectorAll("[data-history-row]").forEach((row) => {
        const type = (row.querySelector('[data-field="type"]')?.value || "").trim();
        const day = (row.querySelector('[data-field="day"]')?.value || "").trim();
        const month = (row.querySelector('[data-field="month"]')?.value || "").trim();
        const year = (row.querySelector('[data-field="year"]')?.value || "").trim();
        if (!type || !year) {
            return;
        }
        const item = { type, year };
        if (day) {
            item.day = day;
        }
        if (month) {
            item.month = month;
        }
        data.history.push(item);
    });
    if (!data.history.length) {
        delete data.history;
    }

    const counts = {
        fig_count: (root.querySelector('[data-field="fig_count"]')?.value || "").trim(),
        table_count: (root.querySelector('[data-field="table_count"]')?.value || "").trim(),
        equation_count: (root.querySelector('[data-field="equation_count"]')?.value || "").trim(),
        ref_count: (root.querySelector('[data-field="ref_count"]')?.value || "").trim(),
    };
    if (Object.values(counts).some(Boolean)) {
        data.counts = counts;
    } else {
        delete data.counts;
    }

    return data;
}

function renderFrontEditor(container, marked) {
    const data = marked || {};
    container.innerHTML = "";

    const titleField = document.createElement("div");
    titleField.className = "manuscript-field";
    titleField.innerHTML = `
        <label class="form-label">${escapeText(manuscriptT("articleTitle", "Article title"))}</label>
        <input class="form-control" type="text" data-field="article_title" value="${escapeAttr(mainTitle(data))}">
    `;
    container.appendChild(titleField);

    const doiField = document.createElement("div");
    doiField.className = "manuscript-field";
    doiField.innerHTML = `
        <label class="form-label">${escapeText(manuscriptT("doi", "DOI"))}</label>
        <input class="form-control" type="text" data-field="doi" value="${escapeAttr(articleDoi(data))}">
    `;
    container.appendChild(doiField);

    const authorsCollapse = createFrontCollapse("authorsLabel");
    const authorsWrap = authorsCollapse.wrap;
    const authorsList = document.createElement("div");
    authorsList.dataset.authorsList = "1";
    (data.authors || [{ surname: "", given_names: "" }]).forEach((author) => {
        authorsList.appendChild(createAuthorRow(author));
    });
    authorsCollapse.body.appendChild(authorsList);
    const addAuthor = document.createElement("button");
    addAuthor.type = "button";
    addAuthor.className = "btn btn-sm btn-secondary";
    addAuthor.textContent = manuscriptT("addAuthor", "Add author");
    addAuthor.addEventListener("click", () => {
        authorsList.appendChild(createAuthorRow({ surname: "", given_names: "" }));
        updateAuthorsLabel(authorsWrap);
    });
    authorsCollapse.body.appendChild(addAuthor);
    updateAuthorsLabel(authorsWrap);
    container.appendChild(authorsWrap);

    const abstractsCollapse = createFrontCollapse("abstractsLabel");
    const abstractsWrap = abstractsCollapse.wrap;
    const abstractsList = document.createElement("div");
    abstractsList.dataset.abstractsList = "1";
    (data.abstracts || [{ language: "en", title: defaultAbstractTitle(), text: "" }]).forEach(
        (abstract) => {
            abstractsList.appendChild(createAbstractRow(abstract));
        }
    );
    abstractsCollapse.body.appendChild(abstractsList);
    const addAbstract = document.createElement("button");
    addAbstract.type = "button";
    addAbstract.className = "btn btn-sm btn-secondary";
    addAbstract.textContent = manuscriptT("addAbstract", "Add abstract");
    addAbstract.addEventListener("click", () => {
        abstractsList.appendChild(
            createAbstractRow({ language: "", title: defaultAbstractTitle(), text: "" })
        );
        updateAbstractsLabel(abstractsWrap);
    });
    abstractsCollapse.body.appendChild(addAbstract);
    updateAbstractsLabel(abstractsWrap);
    container.appendChild(abstractsWrap);

    const keywordsCollapse = createFrontCollapse("keywordsLabel");
    const keywordsWrap = keywordsCollapse.wrap;
    const keywordsList = document.createElement("div");
    keywordsList.dataset.keywordsList = "1";
    (data.keywords || [{ language: "en", title: defaultKeywordsTitle(), keywords: [] }]).forEach(
        (group) => {
            keywordsList.appendChild(createKeywordRow(group));
        }
    );
    keywordsCollapse.body.appendChild(keywordsList);
    keywordsList.addEventListener("input", (event) => {
        if (event.target.matches('[data-field="items"]')) {
            updateKeywordsLabel(keywordsWrap);
        }
    });
    const addKeywords = document.createElement("button");
    addKeywords.type = "button";
    addKeywords.className = "btn btn-sm btn-secondary";
    addKeywords.textContent = manuscriptT("addKeywordGroup", "Add keyword group");
    addKeywords.addEventListener("click", () => {
        keywordsList.appendChild(
            createKeywordRow({ language: "", title: defaultKeywordsTitle(), keywords: [] })
        );
        updateKeywordsLabel(keywordsWrap);
    });
    keywordsCollapse.body.appendChild(addKeywords);
    updateKeywordsLabel(keywordsWrap);
    container.appendChild(keywordsWrap);

    const historyCollapse = createFrontCollapse("historyLabel");
    const historyWrap = historyCollapse.wrap;
    const historyList = document.createElement("div");
    historyList.dataset.historyList = "1";
    const historyItems =
        data.history && data.history.length
            ? data.history
            : [
                  { type: "received", day: "", month: "", year: "" },
                  { type: "accepted", day: "", month: "", year: "" },
              ];
    historyItems.forEach((item) => {
        historyList.appendChild(createHistoryRow(item));
    });
    historyCollapse.body.appendChild(historyList);
    const addHistory = document.createElement("button");
    addHistory.type = "button";
    addHistory.className = "btn btn-sm btn-secondary";
    addHistory.textContent = manuscriptT("addHistoryDate", "Add date");
    addHistory.addEventListener("click", () => {
        historyList.appendChild(createHistoryRow({ type: "accepted", day: "", month: "", year: "" }));
        updateHistoryLabel(historyWrap);
    });
    historyCollapse.body.appendChild(addHistory);
    historyList.addEventListener("input", () => updateHistoryLabel(historyWrap));
    historyList.addEventListener("change", () => updateHistoryLabel(historyWrap));
    updateHistoryLabel(historyWrap);
    container.appendChild(historyWrap);

    const countsCollapse = createFrontCollapse("countsLabel");
    const countsWrap = countsCollapse.wrap;
    const counts = data.counts || {};
    countsCollapse.body.innerHTML = `
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("figCount", "Figures"))}</label>
            <input class="form-control" type="text" data-field="fig_count" value="${escapeAttr(counts.fig_count || "")}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("tableCount", "Tables"))}</label>
            <input class="form-control" type="text" data-field="table_count" value="${escapeAttr(counts.table_count || "")}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("equationCount", "Equations"))}</label>
            <input class="form-control" type="text" data-field="equation_count" value="${escapeAttr(counts.equation_count || "")}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("refCount", "References"))}</label>
            <input class="form-control" type="text" data-field="ref_count" value="${escapeAttr(counts.ref_count || "")}">
        </div>
    `;
    const countsLabel = countsWrap.querySelector("[data-counts-label]");
    if (countsLabel) {
        countsLabel.textContent = manuscriptT("counts", "Counts");
    }
    container.appendChild(countsWrap);
}

function createAuthorRow(author) {
    const row = document.createElement("div");
    row.className = "card manuscript-section-card";
    row.dataset.authorRow = "1";
    row.innerHTML = `
        <div class="card-body">
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("surname", "Surname"))}</label>
            <input class="form-control" type="text" data-field="surname" value="${escapeAttr(author.surname || "")}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("givenNames", "Given names"))}</label>
            <input class="form-control" type="text" data-field="given_names" value="${escapeAttr(author.given_names || "")}">
        </div>
        </div>
    `;
    return row;
}

function createHistoryRow(item) {
    const row = document.createElement("div");
    row.className = "card manuscript-section-card";
    row.dataset.historyRow = "1";
    const selected = item.type || "received";
    const types = [
        ["received", manuscriptT("received", "Received")],
        ["rev-request", manuscriptT("revisionRequested", "Revision requested")],
        ["rev-recd", manuscriptT("revised", "Revised")],
        ["accepted", manuscriptT("accepted", "Accepted")],
    ];
    const options = types
        .map(([value, label]) => {
            const isSelected = value === selected ? " selected" : "";
            return `<option value="${escapeAttr(value)}"${isSelected}>${escapeText(label)}</option>`;
        })
        .join("");
    row.innerHTML = `
        <div class="card-body">
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("dateType", "Date type"))}</label>
            <select class="form-control" data-field="type">${options}</select>
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("day", "Day"))}</label>
            <input class="form-control" type="text" data-field="day" value="${escapeAttr(item.day || "")}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("month", "Month"))}</label>
            <input class="form-control" type="text" data-field="month" value="${escapeAttr(item.month || "")}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("year", "Year"))}</label>
            <input class="form-control" type="text" data-field="year" value="${escapeAttr(item.year || "")}">
        </div>
        </div>
    `;
    return row;
}

function createAbstractRow(abstract) {
    const row = document.createElement("div");
    row.className = "card manuscript-section-card";
    row.dataset.abstractRow = "1";
    row.innerHTML = `
        <div class="card-body">
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("language", "Language"))}</label>
            <input class="form-control" type="text" data-field="language" value="${escapeAttr(abstract.language || "")}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("title", "Title"))}</label>
            <input class="form-control" type="text" data-field="title" value="${escapeAttr(abstract.title || defaultAbstractTitle())}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("text", "Text"))}</label>
            <textarea class="form-control" rows="4" data-field="text">${escapeText(abstract.text || "")}</textarea>
        </div>
        </div>
    `;
    return row;
}

function createKeywordRow(group) {
    const row = document.createElement("div");
    row.className = "card manuscript-section-card";
    row.dataset.keywordRow = "1";
    row.innerHTML = `
        <div class="card-body">
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("language", "Language"))}</label>
            <input class="form-control" type="text" data-field="language" value="${escapeAttr(group.language || "")}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("keywordGroupTitle", "Group title"))}</label>
            <input class="form-control" type="text" data-field="title" value="${escapeAttr(group.title || defaultKeywordsTitle())}">
        </div>
        <div class="manuscript-field">
            <label class="form-label">${escapeText(manuscriptT("keywordsCommaSeparated", "Keywords (comma separated)"))}</label>
            <input class="form-control" type="text" data-field="items" value="${escapeAttr((group.keywords || []).join(", "))}">
        </div>
        </div>
    `;
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

document.addEventListener("DOMContentLoaded", () => {
    const config = window.manuscriptEditorConfig;
    if (!config || config.step !== "front") {
        return;
    }
    const container = document.getElementById("front-wysiwyg-editor");
    if (!container) {
        return;
    }
    renderFrontEditor(container, config.marked || {});

    const saveButton = document.getElementById("front-save-draft");
    if (!saveButton) {
        return;
    }
    saveButton.addEventListener("click", async () => {
        const marked = frontMarkedFromForm(container, config.marked);
        try {
            await window.manuscriptSaveJson(config.saveUrl, { marked }, config.csrfToken);
            config.marked = marked;
            await window.manuscriptRefreshPreview(config.previewUrl);
            window.manuscriptToast(manuscriptT("frontDraftSaved", "Front draft saved"));
        } catch (error) {
            window.manuscriptToast(error.message);
        }
    });
});
