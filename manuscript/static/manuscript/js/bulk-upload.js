(function () {
    function renderPackageFigures(listNode, figures) {
        if (!listNode || !Array.isArray(figures)) {
            return;
        }
        listNode.innerHTML = "";
        figures.forEach(function (fig) {
            if (!fig || !fig.html) {
                return;
            }
            var wrapper = document.createElement("div");
            wrapper.innerHTML = fig.html.trim();
            var item = wrapper.firstElementChild;
            if (item) {
                listNode.appendChild(item);
            }
        });
    }

    function bindFigureListActions(root, csrfToken) {
        if (!root || root.dataset.figureActionsBound === "1") {
            return;
        }
        root.dataset.figureActionsBound = "1";

        root.addEventListener("submit", function (event) {
            var form = event.target.closest("[data-figure-update-form]");
            if (!form) {
                return;
            }
            event.preventDefault();
            var item = form.closest("[data-figure-id]");
            var listNode = form.closest("[data-package-figures-list]");
            var statusNode = item ? item.querySelector("[data-figure-status]") : null;
            var errorNode = item ? item.querySelector("[data-figure-error]") : null;
            if (statusNode) {
                statusNode.hidden = true;
            }
            if (errorNode) {
                errorNode.hidden = true;
                errorNode.textContent = "";
            }
            var formData = new FormData(form);
            var token = formData.get("csrfmiddlewaretoken") || csrfToken;
            fetch(form.action, {
                method: "POST",
                headers: {
                    "X-CSRFToken": token,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: formData,
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    var data = result.data || {};
                    if (!result.ok || !data.success) {
                        if (errorNode) {
                            errorNode.textContent = data.error_message || "Update failed";
                            errorNode.hidden = false;
                        }
                        return;
                    }
                    if (listNode && Array.isArray(data.figures)) {
                        renderPackageFigures(listNode, data.figures);
                        var updatedItem = listNode.querySelector(
                            '[data-figure-id="' + data.figure_id + '"]'
                        );
                        var updatedStatus = updatedItem
                            ? updatedItem.querySelector("[data-figure-status]")
                            : null;
                        if (updatedStatus) {
                            updatedStatus.hidden = false;
                        }
                    } else if (statusNode) {
                        statusNode.hidden = false;
                    }
                })
                .catch(function () {
                    if (errorNode) {
                        errorNode.textContent = "Update failed";
                        errorNode.hidden = false;
                    }
                });
        });

        root.addEventListener("click", function (event) {
            var deleteBtn = event.target.closest("[data-figure-delete-url]");
            if (!deleteBtn) {
                return;
            }
            event.preventDefault();
            var url = deleteBtn.getAttribute("data-figure-delete-url");
            var form = deleteBtn.closest("form");
            var listNode = deleteBtn.closest("[data-package-figures-list]");
            var item = deleteBtn.closest("[data-figure-id]");
            var errorNode = item ? item.querySelector("[data-figure-error]") : null;
            var tokenInput = form
                ? form.querySelector("input[name='csrfmiddlewaretoken']")
                : null;
            var token = (tokenInput && tokenInput.value) || csrfToken;
            fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": token,
                    "X-Requested-With": "XMLHttpRequest",
                },
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    var data = result.data || {};
                    if (!result.ok || !data.success) {
                        if (errorNode) {
                            errorNode.textContent = data.error_message || "Delete failed";
                            errorNode.hidden = false;
                        }
                        return;
                    }
                    if (listNode && Array.isArray(data.figures)) {
                        renderPackageFigures(listNode, data.figures);
                    } else if (item) {
                        item.remove();
                    }
                })
                .catch(function () {
                    if (errorNode) {
                        errorNode.textContent = "Delete failed";
                        errorNode.hidden = false;
                    }
                });
        });
    }

    function bindPackageFigureUpload(packageNode, $, csrfToken) {
        if (!packageNode) {
            return;
        }
        var form = packageNode.querySelector("[data-package-figure-upload-form]");
        var dropZone = packageNode.querySelector("[data-package-dropzone]");
        var listNode = packageNode.querySelector("[data-package-figures-list]");
        var errorNode = packageNode.querySelector("[data-package-figure-error]");
        if (!window.__manuscriptFigureActionsBound) {
            bindFigureListActions(packageNode, csrfToken);
        }
        if (!form || !$ || !$.fn.fileupload) {
            return;
        }
        $(form).fileupload({
            dataType: "json",
            sequentialUploads: true,
            dropZone: dropZone ? $(dropZone) : $(form),
            formData: function () {
                return [{ name: "csrfmiddlewaretoken", value: csrfToken }];
            },
            add: function (e, data) {
                if (errorNode) {
                    errorNode.hidden = true;
                    errorNode.textContent = "";
                }
                data.submit();
            },
            done: function (e, data) {
                var response = data.result || {};
                if (response.success && Array.isArray(response.figures)) {
                    renderPackageFigures(listNode, response.figures);
                } else if (errorNode) {
                    errorNode.textContent = response.error_message || "Upload failed";
                    errorNode.hidden = false;
                }
            },
            fail: function (e, data) {
                var message = "Upload failed";
                if (
                    data.jqXHR &&
                    data.jqXHR.responseJSON &&
                    data.jqXHR.responseJSON.error_message
                ) {
                    message = data.jqXHR.responseJSON.error_message;
                }
                if (errorNode) {
                    errorNode.textContent = message;
                    errorNode.hidden = false;
                }
            },
        });
    }

    function initBulkUpload() {
        var container = document.querySelector(".manuscript-bulk-upload");
        var form = document.getElementById("manuscript-bulk-upload-form");
        if (!container || !form || !window.jQuery || !window.jQuery.fn.fileupload) {
            return;
        }
        var $ = window.jQuery;
        var overallProgress = document.getElementById("overall-progress");
        var overallBar = overallProgress ? overallProgress.querySelector(".bar") : null;
        var uploadList = document.getElementById("upload-list");
        var completeActions = document.getElementById("bulk-upload-complete-actions");
        var csrfInput = form.querySelector("input[name='csrfmiddlewaretoken']");
        var csrfToken = csrfInput ? csrfInput.value : "";

        var successCount = 0;

        $(form).fileupload({
            dataType: "json",
            sequentialUploads: true,
            dropZone: $(container).find("> .drop-zone"),
            formData: function () {
                return [{ name: "csrfmiddlewaretoken", value: csrfToken }];
            },
            add: function (e, data) {
                var file = data.files && data.files[0];
                if (!file) {
                    return;
                }
                if (overallProgress) {
                    overallProgress.hidden = false;
                }
                var li = document.createElement("li");
                li.className = "upload-list__item";
                var header = document.createElement("div");
                header.className = "manuscript-upload-item__header";
                var title = document.createElement("strong");
                title.textContent = file.name;
                var status = document.createElement("span");
                status.className = "upload-list__status";
                status.textContent = " (0%)";
                header.appendChild(title);
                header.appendChild(status);
                li.appendChild(header);
                if (uploadList) {
                    uploadList.appendChild(li);
                }
                data.context = { item: li, status: status };
                data.submit();
            },
            progress: function (e, data) {
                if (!data.context || !data.total) {
                    return;
                }
                var pct = parseInt((data.loaded / data.total) * 100, 10);
                data.context.status.textContent = " (" + pct + "%)";
            },
            progressall: function (e, data) {
                if (!overallBar || !data.total) {
                    return;
                }
                var pct = parseInt((data.loaded / data.total) * 100, 10);
                overallBar.style.width = pct + "%";
                overallBar.textContent = pct + "%";
            },
            done: function (e, data) {
                var response = data.result || {};
                if (response.success) {
                    successCount += 1;
                    if (data.context) {
                        data.context.item.classList.add("upload-complete");
                        data.context.status.textContent = " (100%)";
                        if (response.html) {
                            var wrap = document.createElement("div");
                            wrap.innerHTML = response.html.trim();
                            var packageNode = wrap.firstElementChild;
                            if (packageNode) {
                                data.context.item.appendChild(packageNode);
                                bindPackageFigureUpload(packageNode, $, csrfToken);
                            }
                        }
                    }
                } else if (data.context) {
                    data.context.item.classList.add("upload-failure");
                    data.context.status.textContent =
                        " — " + (response.error_message || "Error");
                }
            },
            fail: function (e, data) {
                var message = "Upload failed";
                if (
                    data.jqXHR &&
                    data.jqXHR.responseJSON &&
                    data.jqXHR.responseJSON.error_message
                ) {
                    message = data.jqXHR.responseJSON.error_message;
                }
                if (data.context) {
                    data.context.item.classList.add("upload-failure");
                    data.context.status.textContent = " — " + message;
                }
            },
            stop: function () {
                if (successCount > 0 && completeActions) {
                    completeActions.hidden = false;
                }
            },
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initBulkUpload);
    } else {
        initBulkUpload();
    }
})();
