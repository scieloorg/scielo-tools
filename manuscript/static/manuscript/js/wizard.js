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
    if (frame && previewUrl) {
        const separator = previewUrl.includes("?") ? "&" : "?";
        frame.src = `${previewUrl}${separator}t=${Date.now()}`;
        return;
    }
    const panel = document.getElementById(panelId || "manuscript-preview-panel");
    if (!panel || !previewUrl) {
        return;
    }
    const response = await fetch(previewUrl);
    panel.innerHTML = await response.text();
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

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindManuscriptMarkingStatus);
} else {
    bindManuscriptMarkingStatus();
}
