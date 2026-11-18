function manuscriptT(key, fallback) {
    const i18n = window.manuscriptI18n || {};
    return i18n[key] || fallback || key;
}

function manuscriptToast(message) {
    const node = document.createElement("div");
    node.className = "alert alert-info manuscript-toast";
    node.setAttribute("role", "alert");
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 3000);
}

async function manuscriptSaveJson(url, payload, csrfToken) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || manuscriptT("saveFailed", "Save failed"));
    }
    return data;
}

async function manuscriptRefreshPreview(previewUrl, panelId) {
    const frame = document.getElementById("manuscript-preview-frame");
    const modalFrame = document.getElementById("manuscript-preview-modal-frame");
    if (frame && previewUrl) {
        const separator = previewUrl.includes("?") ? "&" : "?";
        const nextUrl = `${previewUrl}${separator}t=${Date.now()}`;
        frame.src = nextUrl;
        if (modalFrame) {
            modalFrame.src = nextUrl;
        }
        return;
    }
    const panel = document.getElementById(panelId || "manuscript-preview-panel");
    if (!panel || !previewUrl) {
        return;
    }
    const response = await fetch(previewUrl);
    panel.innerHTML = await response.text();
}

function bindManuscriptPreviewModal() {
    if (window.__manuscriptPreviewModalBound) {
        return;
    }
    const modal = document.getElementById("manuscript-preview-modal");
    const openBtn = document.querySelector("[data-preview-expand-open]");
    if (!modal || !openBtn) {
        return;
    }
    window.__manuscriptPreviewModalBound = true;
    const closeBtn = modal.querySelector("[data-preview-expand-close]");
    const mainFrame = document.getElementById("manuscript-preview-frame");
    const modalFrame = document.getElementById("manuscript-preview-modal-frame");
    const newTabLink = document.getElementById("manuscript-preview-modal-newtab");

    const openModal = () => {
        if (mainFrame && modalFrame) {
            const currentSrc = mainFrame.getAttribute("src") || mainFrame.src;
            if (currentSrc && modalFrame.getAttribute("src") !== currentSrc) {
                modalFrame.setAttribute("src", currentSrc);
            }
            if (newTabLink && currentSrc) {
                newTabLink.setAttribute("href", currentSrc);
            }
        }
        if (typeof modal.showModal === "function") {
            modal.showModal();
        } else {
            modal.setAttribute("open", "open");
        }
    };

    const closeModal = () => {
        if (typeof modal.close === "function" && modal.open) {
            modal.close();
        } else {
            modal.removeAttribute("open");
        }
    };

    openBtn.addEventListener("click", openModal);
    if (closeBtn) {
        closeBtn.addEventListener("click", closeModal);
    }
    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    const publishButton = document.getElementById("manuscript-publish");
    if (!publishButton) {
        return;
    }
    publishButton.addEventListener("click", async () => {
        const config = window.manuscriptEditorConfig || {};
        const url = publishButton.dataset.url;
        try {
            const response = await fetch(url, {
                method: "POST",
                headers: { "X-CSRFToken": config.csrfToken },
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || manuscriptT("publishFailed", "Publish failed"));
            }
            manuscriptToast(
                data.preview_url || manuscriptT("publicationStubCreated", "Publication stub created")
            );
        } catch (error) {
            manuscriptToast(error.message);
        }
    });
});

window.manuscriptT = manuscriptT;
window.manuscriptToast = manuscriptToast;
window.manuscriptSaveJson = manuscriptSaveJson;
window.manuscriptRefreshPreview = manuscriptRefreshPreview;

function manuscriptMarkingConfig() {
    const root = document.querySelector(".manuscript-wizard");
    const editor = window.manuscriptEditorConfig || {};
    const stateNode = document.getElementById("manuscript-marking-state");
    let state = editor.markingState;
    if (!state && stateNode) {
        state = JSON.parse(stateNode.textContent);
    }
    return {
        step: editor.step || (root && root.dataset.step) || "",
        statusUrl: editor.markingStatusUrl || (root && root.dataset.markingStatusUrl) || "",
        state: state || {},
    };
}

function applyManuscriptMeter(host, meter, info, active) {
    if (!meter) {
        return;
    }
    const isStepLink = host.hasAttribute("data-marking-part");
    const isDone = info.status === "done" || (isStepLink && host.classList.contains("is-complete") && !active);
    if (meter.hidden === active) {
        meter.hidden = !active;
    }
    let percent = 0;
    if (isDone && !active) {
        percent = 100;
    } else if (active && info.percent != null && info.percent !== "") {
        percent = Math.round(Number(info.percent));
        if (Number.isNaN(percent)) {
            percent = 0;
        }
        percent = Math.max(0, Math.min(100, percent));
    }
    const percentStr = String(percent);
    if (meter.getAttribute("aria-valuenow") !== percentStr) {
        meter.setAttribute("aria-valuenow", percentStr);
    }
    const bar = meter.querySelector(".manuscript-wizard__step-meter-bar");
    const targetWidth = `${percent}%`;
    if (bar && bar.style.width !== targetWidth) {
        bar.style.width = targetWidth;
    }
    const showPercent = active || (isStepLink && isDone);
    host.querySelectorAll(".manuscript-wizard__step-percent").forEach((node) => {
        if (node.hidden === showPercent) {
            node.hidden = !showPercent;
        }
        if (node.textContent !== targetWidth) {
            node.textContent = targetWidth;
        }
    });
    const fillLabel = host.querySelector(".manuscript-wizard__step-label--fill");
    if (fillLabel) {
        if (fillLabel.hidden === active) {
            fillLabel.hidden = !active;
        }
        const targetClip = `inset(0 calc(100% - ${percent}%) 0 0)`;
        if (fillLabel.style.clipPath !== targetClip) {
            fillLabel.style.clipPath = targetClip;
        }
    }
}

function applyManuscriptMarkingState(state) {
    document.querySelectorAll("[data-marking-part]").forEach((link) => {
        const info = state[link.dataset.markingPart] || {};
        const status = info.status || "idle";
        const active = status === "pending" || status === "running";
        if (link.classList.contains("is-running") !== active) {
            link.classList.toggle("is-running", active);
        }
        if (status === "error") {
            if (!link.classList.contains("is-error")) {
                link.classList.add("is-error");
            }
        } else if (active || status === "done") {
            if (link.classList.contains("is-error")) {
                link.classList.remove("is-error");
            }
        }
        if (status === "done" && !link.classList.contains("is-complete")) {
            link.classList.add("is-complete");
        }
        if (active) {
            if (link.getAttribute("aria-busy") !== "true") {
                link.setAttribute("aria-busy", "true");
            }
        } else if (link.hasAttribute("aria-busy")) {
            link.removeAttribute("aria-busy");
        }
        applyManuscriptMeter(
            link,
            link.querySelector(".manuscript-wizard__step-meter"),
            info,
            active
        );
    });
    document.querySelectorAll("[data-marking-submit]").forEach((button) => {
        const info = state[button.dataset.markingSubmit] || {};
        const status = info.status || "idle";
        const active = status === "pending" || status === "running";
        if (button.disabled !== active) {
            button.disabled = active;
        }
        if (button.classList.contains("is-running") !== active) {
            button.classList.toggle("is-running", active);
        }
        applyManuscriptMeter(
            button,
            button.querySelector(".manuscript-wizard__step-meter"),
            info,
            active
        );
    });
    document.querySelectorAll("[data-marking-approve]").forEach((button) => {
        const status = (state[button.dataset.markingApprove] || {}).status;
        const shouldDisable = status === "pending" || status === "running";
        if (button.disabled !== shouldDisable) {
            button.disabled = shouldDisable;
        }
    });
}

function bindManuscriptMarkingStatus() {
    if (window.__manuscriptMarkingBound) {
        return;
    }
    window.__manuscriptMarkingBound = true;
    const listNodes = Array.from(
        document.querySelectorAll("[data-manuscript-list-progress]")
    );
    const activeListNodes = listNodes.filter(
        (node) => node.dataset.markingActive === "true"
    );
    if (activeListNodes.length) {
        const pollList = async () => {
            const remaining = [];
            await Promise.all(
                activeListNodes.map(async (node) => {
                    if (node.dataset.markingActive !== "true") {
                        return;
                    }
                    const url = node.dataset.markingStatusUrl;
                    if (!url) {
                        return;
                    }
                    const response = await fetch(url);
                    if (!response.ok) {
                        remaining.push(node);
                        return;
                    }
                    const data = await response.json();
                    const overall = data.overall || {};
                    const status = overall.status || "idle";
                    const active = status === "pending" || status === "running";
                    const percent = Math.max(
                        0,
                        Math.min(100, Math.round(Number(overall.percent || 0)))
                    );
                    const percentStr = String(percent);
                    const targetWidth = `${percent}%`;
                    node.dataset.markingActive = active ? "true" : "false";
                    if (node.classList.contains("is-running") !== active) {
                        node.classList.toggle("is-running", active);
                    }
                    const isComplete = !active && (status === "done" || percent === 100);
                    if (node.classList.contains("is-complete") !== isComplete) {
                        node.classList.toggle("is-complete", isComplete);
                    }
                    const isError = !active && status === "error";
                    if (node.classList.contains("is-error") !== isError) {
                        node.classList.toggle("is-error", isError);
                    }
                    const bar = node.querySelector(".manuscript-list-progress__bar");
                    if (bar && bar.getAttribute("aria-valuenow") !== percentStr) {
                        bar.setAttribute("aria-valuenow", percentStr);
                    }
                    const fill = node.querySelector(".manuscript-list-progress__fill");
                    if (fill && fill.style.width !== targetWidth) {
                        fill.style.width = targetWidth;
                    }
                    const label = node.querySelector(
                        ".manuscript-list-progress__percent"
                    );
                    if (label && label.textContent !== targetWidth) {
                        label.textContent = targetWidth;
                    }
                    if (active) {
                        remaining.push(node);
                    }
                })
            );
            if (remaining.length) {
                window.setTimeout(pollList, 2000);
            }
        };
        window.setTimeout(pollList, 2000);
    }
    const config = manuscriptMarkingConfig();
    applyManuscriptMarkingState(config.state);
    if (!config.statusUrl) {
        return;
    }
    const parts = ["front", "body", "back", "validate", "package"];
    const startedDone = {};
    parts.forEach((part) => {
        startedDone[part] = (config.state[part] || {}).status === "done";
    });
    const hasActive = parts.some((part) => {
        const status = (config.state[part] || {}).status;
        return status === "pending" || status === "running";
    });
    if (!hasActive) {
        return;
    }
    const poll = async () => {
        const response = await fetch(config.statusUrl);
        if (!response.ok) {
            window.setTimeout(poll, 2000);
            return;
        }
        const data = await response.json();
        applyManuscriptMarkingState(data);
        const step = config.step;
        if (parts.includes(step)) {
            const now = (data[step] || {}).status;
            if (!startedDone[step] && now === "done") {
                window.location.reload();
                return;
            }
            if (now === "error" && !startedDone[step]) {
                startedDone[step] = true;
                const error = (data[step] || {}).error;
                if (error) {
                    manuscriptToast(error);
                }
            }
        }
        if (
            parts.some((part) => {
                const status = (data[part] || {}).status;
                return status === "pending" || status === "running";
            })
        ) {
            window.setTimeout(poll, 2000);
        }
    };
    window.setTimeout(poll, 2000);
}

function renderManuscriptFiguresList(listNode, figures) {
    if (!listNode || !Array.isArray(figures)) {
        return;
    }
    listNode.innerHTML = "";
    figures.forEach((fig) => {
        if (!fig || !fig.html) {
            return;
        }
        const wrapper = document.createElement("div");
        wrapper.innerHTML = fig.html.trim();
        if (wrapper.firstElementChild) {
            listNode.appendChild(wrapper.firstElementChild);
        }
    });
}

function bindManuscriptFigureActions() {
    if (window.__manuscriptFigureActionsBound) {
        return;
    }
    window.__manuscriptFigureActionsBound = true;

    document.addEventListener("submit", async (event) => {
        const form = event.target.closest("[data-figure-update-form]");
        if (!form) {
            return;
        }
        event.preventDefault();
        const listNode = form.closest("[data-package-figures-list]");
        const item = form.closest("[data-figure-id]");
        const statusNode = item ? item.querySelector("[data-figure-status]") : null;
        const errorNode = item ? item.querySelector("[data-figure-error]") : null;
        if (statusNode) {
            statusNode.hidden = true;
        }
        if (errorNode) {
            errorNode.hidden = true;
            errorNode.textContent = "";
        }
        const formData = new FormData(form);
        const config = window.manuscriptEditorConfig || {};
        const token = formData.get("csrfmiddlewaretoken") || config.csrfToken || "";
        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: {
                    "X-CSRFToken": token,
                    "X-Requested-With": "XMLHttpRequest",
                    Accept: "application/json",
                },
                body: formData,
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                if (errorNode) {
                    errorNode.textContent = data.error_message || "Update failed";
                    errorNode.hidden = false;
                }
                return;
            }
            if (listNode && Array.isArray(data.figures)) {
                renderManuscriptFiguresList(listNode, data.figures);
                const updatedItem = listNode.querySelector(
                    `[data-figure-id="${data.figure_id}"]`
                );
                const updatedStatus = updatedItem
                    ? updatedItem.querySelector("[data-figure-status]")
                    : null;
                if (updatedStatus) {
                    updatedStatus.hidden = false;
                }
            } else if (statusNode) {
                statusNode.hidden = false;
            }
            if (config.previewUrl) {
                await manuscriptRefreshPreview(config.previewUrl);
            }
        } catch (_err) {
            if (errorNode) {
                errorNode.textContent = "Update failed";
                errorNode.hidden = false;
            }
        }
    });

    document.addEventListener("click", async (event) => {
        const deleteBtn = event.target.closest("[data-figure-delete-url]");
        if (!deleteBtn) {
            return;
        }
        event.preventDefault();
        const listNode = deleteBtn.closest("[data-package-figures-list]");
        const item = deleteBtn.closest("[data-figure-id]");
        const form = deleteBtn.closest("form");
        const errorNode = item ? item.querySelector("[data-figure-error]") : null;
        const config = window.manuscriptEditorConfig || {};
        const tokenInput = form
            ? form.querySelector("input[name='csrfmiddlewaretoken']")
            : null;
        const token = (tokenInput && tokenInput.value) || config.csrfToken || "";
        try {
            const response = await fetch(
                deleteBtn.getAttribute("data-figure-delete-url"),
                {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": token,
                        "X-Requested-With": "XMLHttpRequest",
                        Accept: "application/json",
                    },
                }
            );
            const data = await response.json();
            if (!response.ok || !data.success) {
                if (errorNode) {
                    errorNode.textContent = data.error_message || "Delete failed";
                    errorNode.hidden = false;
                }
                return;
            }
            if (listNode && Array.isArray(data.figures)) {
                renderManuscriptFiguresList(listNode, data.figures);
            } else if (item) {
                item.remove();
            }
            if (config.previewUrl) {
                await manuscriptRefreshPreview(config.previewUrl);
            }
        } catch (_err) {
            if (errorNode) {
                errorNode.textContent = "Delete failed";
                errorNode.hidden = false;
            }
        }
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
        bindManuscriptPreviewModal();
        bindManuscriptFigureActions();
        bindManuscriptMarkingStatus();
    });
} else {
    bindManuscriptPreviewModal();
    bindManuscriptFigureActions();
    bindManuscriptMarkingStatus();
}
