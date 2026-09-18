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

function bindManuscriptMarkingOverlay() {
    const overlay = document.getElementById("manuscript-marking-overlay");
    const messageNode = document.getElementById("manuscript-marking-message");
    const timerNode = document.getElementById("manuscript-marking-timer");
    if (!overlay || !messageNode || !timerNode) {
        return;
    }
    document.body.appendChild(overlay);
    let marking = false;
    let allowNative = false;
    let timerId = 0;
    document.addEventListener(
        "submit",
        (event) => {
            const form = event.target;
            const submitter = event.submitter;
            if (
                !(form instanceof HTMLFormElement) ||
                !submitter ||
                submitter.name !== "action" ||
                submitter.value !== "mark"
            ) {
                return;
            }
            if (allowNative) {
                return;
            }
            event.preventDefault();
            if (marking) {
                return;
            }
            marking = true;
            const step = (window.manuscriptEditorConfig || {}).step;
            const messages = {
                front: manuscriptT("markingFront", "Marking front..."),
                body: manuscriptT("markingBody", "Marking body..."),
                back: manuscriptT("markingReferences", "Marking references..."),
            };
            messageNode.textContent =
                messages[step] || manuscriptT("markingFront", "Marking front...");
            overlay.hidden = false;
            overlay.classList.add("is-visible");
            overlay.setAttribute("aria-busy", "true");
            const started = Date.now();
            const tick = () => {
                const total = Math.floor((Date.now() - started) / 1000);
                const minutes = String(Math.floor(total / 60)).padStart(2, "0");
                const seconds = String(total % 60).padStart(2, "0");
                timerNode.textContent = `${minutes}:${seconds}`;
            };
            tick();
            timerId = window.setInterval(tick, 1000);
            window.requestAnimationFrame(() => {
                allowNative = true;
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit(submitter);
                    return;
                }
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = "action";
                input.value = "mark";
                form.appendChild(input);
                form.submit();
            });
        },
        true
    );
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindManuscriptMarkingOverlay);
} else {
    bindManuscriptMarkingOverlay();
}
