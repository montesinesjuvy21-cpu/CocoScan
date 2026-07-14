(function () {
    const SUPABASE_REPORT_IMAGE_BASE_URL =
        "https://utvltqgxqnpcqrphuojc.supabase.co/storage/v1/object/public/reports/";

    let currentReportModalRecord = null;
    let currentReportModalMode = "farmer";
    let activeReportModalSubmissionController = null;

    function getModalRoot() {
        return document.querySelector("[data-report-modal]");
    }

    function escapeHtml(text) {
        return String(text ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function normalizeList(value) {
        if (Array.isArray(value)) {
            return value
                .map((item) => String(item ?? "").trim())
                .filter(Boolean);
        }

        if (typeof value === "string") {
            const cleaned = value.trim();
            return cleaned ? [cleaned] : [];
        }

        return [];
    }

    function normalizeConfidence(value) {
        if (value === null || value === undefined || value === "") {
            return "--";
        }

        if (typeof value === "string") {
            const cleaned = value.trim();
            if (!cleaned) return "--";
            if (cleaned.endsWith("%")) return cleaned;
            const parsed = Number(cleaned);
            if (Number.isNaN(parsed)) return cleaned;
            return `${parsed <= 1 ? Math.round(parsed * 100) : Math.round(parsed)}%`;
        }

        const parsed = Number(value);
        if (Number.isNaN(parsed)) {
            return String(value);
        }

        return `${parsed <= 1 ? Math.round(parsed * 100) : Math.round(parsed)}%`;
    }

    function resolveReportImageUrl(imageUrl) {
        if (!imageUrl) return "";

        const resolved = String(imageUrl).trim();
        if (!resolved) return "";

        if (resolved.startsWith("http://") || resolved.startsWith("https://") || resolved.startsWith("data:") || resolved.startsWith("blob:")) {
            return resolved;
        }

        return `${SUPABASE_REPORT_IMAGE_BASE_URL}${resolved.replace(/^\/+/, "")}`;
    }

    function formatTimestamp(value) {
        if (!value) return "Timestamp unavailable";

        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return String(value);
        }

        return new Intl.DateTimeFormat("en-US", {
            timeZone: "Asia/Manila",
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: true,
        }).format(parsed);
    }

    function normalizeReportData(reportData = {}) {
        const gps = reportData.gps || {};
        const primaryImage = reportData.primary_image || reportData.img || reportData.image_url || reportData.image || "";
        const additionalImages = normalizeList(reportData.additional_images || reportData.supporting_images);

        return {
            id: reportData.id ?? null,
            mode: reportData.mode || currentReportModalMode,
            pest: reportData.pest || reportData.pest_type || reportData.prediction || "Unknown Pest",
            confidence: normalizeConfidence(reportData.confidence || reportData.pest_confidence),
            status: String(reportData.status || reportData.current_status || "").trim() || (currentReportModalMode === "scan" ? "Ready to Submit" : "Pending"),
            timestamp: reportData.timestamp || reportData.created_at || reportData.submitted_at || reportData.photo_taken_at || "",
            farmer: reportData.farmer || reportData.farmer_name || "Farmer",
            notes: reportData.notes || reportData.field_notes || reportData.farmer_notes || "",
            locationText: reportData.location_text || reportData.full_location || reportData.location || "No location logged",
            latitude: gps.latitude ?? reportData.latitude ?? "",
            longitude: gps.longitude ?? reportData.longitude ?? "",
            accuracy: gps.accuracy ?? reportData.gps_accuracy ?? "",
            source: gps.source ?? reportData.location_source ?? "",
            primaryImage: resolveReportImageUrl(primaryImage),
            additionalImages,
            initialRecommendations: normalizeList(reportData.initial_recommendations || reportData.recommendations),
            expertRecommendations: normalizeList(reportData.expert_recommendations || reportData.expert_recommendation),
            weather: reportData.weather || {},
        };
    }

    function setDisplay(element, visible, displayValue = "block") {
        if (!element) return;
        element.style.display = visible ? displayValue : "none";
    }

    function isRecommendationIssuedStatus(status) {
        const normalized = String(status ?? "").trim().toLowerCase();
        return ["recommendation issued", "reviewed", "reviewed & issued", "recommendation-issued", "recommendation_issued", "resolved", "completed"].includes(normalized);
    }

    function clearNode(node) {
        if (!node) return;
        node.innerHTML = "";
    }

    function setReportModalSubmissionState(isSubmitting, pendingLabel = "Submitting your report…") {
        const followUpButton = document.getElementById("summary-followup-button");
        const scanSubmitButton = document.getElementById("report-scan-submit-btn");
        const agriSubmitButton = document.getElementById("report-agri-submit-btn");
        const cancelButton = document.getElementById("report-modal-cancel-btn");
        const actionButtons = [followUpButton, scanSubmitButton, agriSubmitButton].filter(Boolean);

        actionButtons.forEach((button) => {
            if (!button) return;
            const shouldDisable = isSubmitting && button.id !== "summary-followup-button";
            button.disabled = shouldDisable;
            button.classList.toggle("is-disabled", shouldDisable);
            button.setAttribute("aria-busy", isSubmitting ? "true" : "false");

            if (isSubmitting) {
                if (!button.dataset.defaultHtml) {
                    button.dataset.defaultHtml = button.innerHTML;
                }
                const icon = button.id === "summary-followup-button" ? "fa-solid fa-rotate" : "fa-solid fa-spinner fa-spin";
                button.innerHTML = `<i class="${icon}"></i> ${pendingLabel}`;
            } else if (button.dataset.defaultHtml) {
                button.innerHTML = button.dataset.defaultHtml;
            }
        });

        if (cancelButton) {
            cancelButton.disabled = false;
            cancelButton.classList.remove("is-disabled");
            cancelButton.setAttribute("aria-busy", "false");
        }
    }

    function abortActiveReportModalSubmission() {
        if (activeReportModalSubmissionController) {
            activeReportModalSubmissionController.abort();
            activeReportModalSubmissionController = null;
        }
        setReportModalSubmissionState(false);
    }

    function renderList(node, items, emptyText) {
        if (!node) return;
        node.innerHTML = "";

        if (!items || items.length === 0) {
            const li = document.createElement("li");
            li.innerHTML = `<i class="fa-solid fa-circle-info" style="color: #d97706;"></i> <span>${escapeHtml(emptyText)}</span>`;
            node.appendChild(li);
            return;
        }

        items.forEach((item) => {
            const li = document.createElement("li");
            li.innerHTML = `<i class="fa-solid fa-circle-check"></i> <span>${escapeHtml(item)}</span>`;
            node.appendChild(li);
        });
    }

    function renderAdditionalImages(node, images) {
        if (!node) return;
        node.innerHTML = "";

        if (!images || images.length === 0) {
            node.innerHTML = '<div style="width:100%;"><p style="font-size: 0.82rem; color: var(--text-muted); margin: 0; text-align: left;">No additional images uploaded.</p></div>';
            return;
        }

        images.forEach((imageUrl, index) => {
            const frame = document.createElement("div");
            frame.style.borderRadius = "12px";
            frame.style.overflow = "hidden";
            frame.style.background = "#eaeaea";
            frame.style.aspectRatio = "1 / 1";

            const image = document.createElement("img");
            image.src = resolveReportImageUrl(imageUrl);
            image.alt = `Additional report image ${index + 1}`;
            image.style.width = "100%";
            image.style.height = "100%";
            image.style.objectFit = "cover";
            frame.appendChild(image);
            node.appendChild(frame);
        });
    }

    function weatherLine(value, suffix) {
        if (value === null || value === undefined || value === "") {
            return "--";
        }
        return suffix ? `${value}${suffix}` : String(value);
    }

    async function fetchWeatherSnapshot(latitude, longitude) {
        try {
            if (latitude === "" || longitude === "" || latitude === null || longitude === null || latitude === undefined || longitude === undefined) {
                throw new Error("Missing coordinates");
            }

            const latValue = Number(latitude);
            const lngValue = Number(longitude);
            if (Number.isNaN(latValue) || Number.isNaN(lngValue)) {
                throw new Error("Invalid coordinates");
            }

            const weatherUrl = `https://api.open-meteo.com/v1/forecast?latitude=${latValue}&longitude=${lngValue}&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m`;
            const response = await fetch(weatherUrl);
            if (!response.ok) {
                throw new Error(`Weather service returned ${response.status}`);
            }

            const data = await response.json();
            const current = data.current || {};
            return {
                location: `${latValue.toFixed(4)}, ${lngValue.toFixed(4)}`,
                temp: current.temperature_2m ?? "--",
                humidity: current.relative_humidity_2m ?? "--",
                rainfall: current.precipitation ?? "--",
                wind: current.wind_speed_10m ?? "--",
                is_down: false,
            };
        } catch (error) {
            return {
                location: "Weather unavailable",
                temp: "--",
                humidity: "--",
                rainfall: "--",
                wind: "--",
                is_down: true,
            };
        }
    }

    function applyStatusStyle(report) {
        const severityBanner = document.getElementById("report-severity-banner");
        const statusNode = document.getElementById("report-status-text");

        const pestStyles = {
            "rhinoceros beetle": { backgroundColor: "#164630", textColor: "#ffffff" },
            "brontispa": { backgroundColor: "#d97706", textColor: "#ffffff" }
        };

        const pestKey = String(report.pest || "").trim().toLowerCase();
        const bannerStyle = pestStyles[pestKey] || null;

        if (statusNode) {
            statusNode.textContent = report.status || "--";
            statusNode.style.color = report.status === "Recommendation Issued" ? "#059669" : "#d97706";
        }

        if (severityBanner) {
            if (bannerStyle) {
                severityBanner.style.backgroundColor = bannerStyle.backgroundColor;
                severityBanner.style.color = bannerStyle.textColor;
            } else {
                severityBanner.style.backgroundColor = "#f8fafc";
                severityBanner.style.color = "#102a43";
            }
        }
    }

    function applyModeState(mode, report = currentReportModalRecord) {
        const scanButton = document.getElementById("report-scan-submit-btn");
        const farmerButton = document.getElementById("summary-followup-button");
        const agriButton = document.getElementById("report-agri-submit-btn");
        const cancelButton = document.getElementById("report-modal-cancel-btn");
        const notesInput = document.getElementById("field-notes-capture");
        const notesDisplay = document.getElementById("report-notes-display");
        const expertInput = document.getElementById("expert-notes-input");
        const expertHelp = document.getElementById("expert-notes-help");
        const scanOnlyNodes = document.querySelectorAll("[data-scan-only]");
        const readonlyOnlyNodes = document.querySelectorAll("[data-readonly-only]");
        const isReviewed = isRecommendationIssuedStatus(report?.status || "");

        setDisplay(scanButton, mode === "scan", "flex");
        setDisplay(farmerButton, false, "flex");
        setDisplay(agriButton, mode === "agriculturist" && !isReviewed, "flex");
        setDisplay(cancelButton, !(mode === "agriculturist" && isReviewed), "inline-flex");

        scanOnlyNodes.forEach((node) => setDisplay(node, mode === "scan", "block"));
        readonlyOnlyNodes.forEach((node) => setDisplay(node, mode !== "scan", "block"));

        if (farmerButton) {
            const canFollowUp = mode === "farmer" && isReviewed;
            farmerButton.disabled = !canFollowUp;
            farmerButton.classList.toggle("is-disabled", !canFollowUp);
            farmerButton.style.pointerEvents = canFollowUp ? "auto" : "none";
            farmerButton.style.backgroundColor = canFollowUp ? "" : "#cbd5e1";
            farmerButton.style.color = canFollowUp ? "" : "#475569";
            farmerButton.style.borderColor = canFollowUp ? "" : "#94a3b8";
            farmerButton.setAttribute("aria-disabled", String(!canFollowUp));
            farmerButton.title = canFollowUp ? "Proceed to follow up" : "Awaiting expert recommendation";
            farmerButton.innerHTML = canFollowUp
                ? '<i class="fa-solid fa-rotate"></i> Update Status'
                : '<i class="fa-solid fa-lock"></i> Awaiting Recommendation';
        }

        if (notesInput && notesDisplay) {
            if (mode === "scan") {
                setDisplay(notesInput, true, "block");
                setDisplay(notesDisplay, false);
            } else {
                setDisplay(notesInput, false);
                setDisplay(notesDisplay, true, "block");
            }
        }

        if (expertInput) {
            const shouldShowInput = mode === "agriculturist" && !isReviewed;
            setDisplay(expertInput, shouldShowInput, "block");
            if (!shouldShowInput) {
                expertInput.value = "";
            }
        }

        if (expertHelp) {
            const shouldShowHelp = mode === "agriculturist";
            setDisplay(expertHelp, shouldShowHelp, "block");
            if (shouldShowHelp) {
                expertHelp.innerHTML = isReviewed
                    ? '<em>Recommendation already issued and locked for this report.</em>'
                    : '<em>Add treatment guidance for the farmer and submit.</em>';
            } else {
                expertHelp.innerHTML = "";
            }
        }
    }

    function renderWorkflowActions(mode, report = currentReportModalRecord) {
        const workflowCard = document.getElementById("workflow-actions-card");
        const workflowHelp = document.getElementById("workflow-actions-help");
        const workflowButtons = document.getElementById("workflow-actions-buttons");
        const workflowInput = document.getElementById("workflow-detail-input");
        if (!workflowCard || !workflowButtons) {
            return;
        }

        const normalizedStatus = String(report?.status || "").trim();
        workflowButtons.innerHTML = "";
        if (workflowInput) {
            workflowInput.value = "";
            workflowInput.placeholder = "Add notes, a reason, availability, or the selected schedule...";
        }

        const actions = [];
        if (mode === "agriculturist") {
            if (["Pending Assessment", "Recommendation Issued", "Waiting for Farmer Feedback"].includes(normalizedStatus)) {
                actions.push({
                    label: "Request On-site Visit",
                    icon: "fa-solid fa-map-location-dot",
                    action: "request-visit",
                    help: "Capture the need for a field visit and the justification for the farmer.",
                });
            }
            if (normalizedStatus === "Waiting for Schedule") {
                actions.push({
                    label: "Select Visit Schedule",
                    icon: "fa-solid fa-calendar-check",
                    action: "select-visit-schedule",
                    help: "Choose one farmer-supplied schedule option for the visit.",
                });
            }
            if (normalizedStatus === "Visit Scheduled") {
                actions.push({
                    label: "Confirm Visit Completed",
                    icon: "fa-solid fa-circle-check",
                    action: "complete-visit",
                    help: "Record the visit outcome and any proof or inspection details.",
                });
            }
            if (normalizedStatus === "Inspection Completed") {
                actions.push({
                    label: "Mark as Resolved",
                    icon: "fa-solid fa-check-double",
                    action: "mark-resolved",
                    help: "Close the case after the inspection and final follow-up.",
                });
            }
        } else if (mode === "farmer") {
            if (normalizedStatus === "On-site Visit Requested") {
                actions.push({
                    label: "Share Availability",
                    icon: "fa-solid fa-calendar-days",
                    action: "provide-availability",
                    help: "Send your available dates and time slots to the agriculturist.",
                });
            }
            if (["Recommendation Issued", "Waiting for Farmer Feedback", "Inspection Completed"].includes(normalizedStatus)) {
                actions.push({
                    label: "Confirm Resolution",
                    icon: "fa-solid fa-thumbs-up",
                    action: "confirm-resolution",
                    help: "Confirm that the recommendation worked or that the visit completed the case.",
                });
            }
        }

        if (workflowHelp) {
            workflowHelp.textContent = actions[0]?.help || "Advance the report to the next stage.";
        }

        if (actions.length === 0) {
            setDisplay(workflowCard, false, "block");
            return;
        }

        setDisplay(workflowCard, true, "block");
        actions.forEach((action) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn-control submit-primary";
            button.innerHTML = `<i class="${action.icon}"></i> ${action.label}`;
            button.onclick = () => submitWorkflowAction(action.action);
            workflowButtons.appendChild(button);
        });
    }

    async function submitWorkflowAction(actionName) {
        const workflowInput = document.getElementById("workflow-detail-input");
        const detail = (workflowInput?.value || "").trim();
        const report = currentReportModalRecord;
        if (!report?.id) {
            alert("This report is missing an identifier.");
            return;
        }
        if (!detail) {
            alert("Please add a short note before advancing the workflow.");
            return;
        }

        const payload = { report_id: report.id, reason: detail };
        let endpoint = "";
        let statusLabel = "";
        let requestKey = "reason";

        if (actionName === "request-visit") {
            endpoint = "/agriculturist/request-visit";
            statusLabel = "On-site Visit Requested";
        } else if (actionName === "provide-availability") {
            endpoint = "/farmer/provide-availability";
            statusLabel = "Waiting for Schedule";
            requestKey = "availability";
        } else if (actionName === "select-visit-schedule") {
            endpoint = "/agriculturist/select-visit-schedule";
            statusLabel = "Visit Scheduled";
            requestKey = "schedule";
        } else if (actionName === "complete-visit") {
            endpoint = "/agriculturist/complete-visit";
            statusLabel = "Inspection Completed";
            requestKey = "details";
        } else if (actionName === "confirm-resolution") {
            endpoint = "/farmer/confirm-resolution";
            statusLabel = "Resolved";
            requestKey = "confirmation";
        } else if (actionName === "mark-resolved") {
            endpoint = "/agriculturist/mark-resolved";
            statusLabel = "Resolved";
            requestKey = "resolution_note";
        }

        if (!endpoint) {
            alert("This workflow step is not available yet.");
            return;
        }

        payload[requestKey] = detail;

        try {
            const response = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) {
                alert(data.message || "The workflow action could not be completed.");
                return;
            }
            if (report) {
                report.status = statusLabel;
                applyStatusStyle(report);
                renderWorkflowActions(currentReportModalMode, report);
            }
            alert(data.message || "Workflow action completed.");
        } catch (error) {
            alert("The workflow action could not be completed right now.");
        }
    }

    function closeReportModal() {
        abortActiveReportModalSubmission();

        const modalRoot = getModalRoot();
        if (modalRoot) {
            modalRoot.classList.remove("open-modal");
            modalRoot.setAttribute("aria-hidden", "true");
        }

        currentReportModalRecord = null;
        currentReportModalMode = "farmer";

        const followUpModal = document.getElementById("followup-modal");
        if (followUpModal && followUpModal.classList.contains("open-modal")) {
            followUpModal.classList.remove("open-modal");
        }

        if (typeof window.resetWorkflowStateToHome === "function") {
            window.resetWorkflowStateToHome();
        }
    }

    async function populateWeather(report) {
        const weather = report.weather || {};
        const hasWeatherData = weather && Object.keys(weather).length > 0 && weather.temp !== undefined;

        if (!hasWeatherData) {
            const snapshot = await fetchWeatherSnapshot(report.latitude, report.longitude);
            if (currentReportModalRecord && currentReportModalRecord.id === report.id && currentReportModalMode === report.mode) {
                currentReportModalRecord.weather = snapshot;
                renderWeather(snapshot);
            }
            return;
        }

        renderWeather(weather);
    }

    function renderWeather(weather) {
        const locationNode = document.getElementById("report-weather-location");
        const tempNode = document.getElementById("report-weather-temp");
        const humidityNode = document.getElementById("report-weather-humidity");
        const windNode = document.getElementById("report-weather-wind");
        const rainfallNode = document.getElementById("report-weather-rainfall");

        if (locationNode) locationNode.textContent = weatherLine(weather?.location, "");
        if (tempNode) tempNode.textContent = weatherLine(weather?.temp, weather?.temp === "--" ? "" : "°C");
        if (humidityNode) humidityNode.textContent = weatherLine(weather?.humidity, weather?.humidity === "--" ? "" : "%");
        if (windNode) windNode.textContent = weatherLine(weather?.wind, weather?.wind === "--" ? "" : " km/h");
        if (rainfallNode) rainfallNode.textContent = weather?.is_down ? "Weather data unavailable" : `Rainfall: ${weatherLine(weather?.rainfall, weather?.rainfall === "--" ? "" : " mm")}`;
    }

    function openReportModal(reportData = {}, mode = "farmer") {
        const modalRoot = getModalRoot();
        if (!modalRoot) {
            return;
        }

        currentReportModalMode = mode || "farmer";
        currentReportModalRecord = normalizeReportData({ ...reportData, mode: currentReportModalMode });

        const report = currentReportModalRecord;

        const pestTitle = document.getElementById("report-pest-title");
        const confidenceNode = document.getElementById("report-confidence");
        const primaryImage = document.getElementById("report-primary-image");
        const farmerNameNode = document.getElementById("report-farmer-name");
        const locationNode = document.getElementById("report-location-text");
        const timestampNode = document.getElementById("report-timestamp-text");
        const gpsNode = document.getElementById("report-gps-text");
        const notesInput = document.getElementById("field-notes-capture");
        const notesDisplay = document.getElementById("report-notes-display");
        const expertInput = document.getElementById("expert-notes-input");
        const expertCard = document.getElementById("report-expert-card");
        const closeHeaderBtn = document.getElementById("report-close-btn-header");

        const isReviewed = isRecommendationIssuedStatus(report?.status || "");
        if (closeHeaderBtn) {
            setDisplay(closeHeaderBtn, mode === "agriculturist" && isReviewed, "inline-flex");
        }

        if (pestTitle) pestTitle.textContent = report.pest;
        if (confidenceNode) confidenceNode.textContent = report.confidence;
        if (farmerNameNode) farmerNameNode.textContent = report.farmer;
        if (locationNode) locationNode.textContent = report.locationText;
        if (timestampNode) timestampNode.textContent = formatTimestamp(report.timestamp);
        if (gpsNode) {
            const gpsParts = [];
            if (report.latitude !== "" && report.latitude !== null && report.longitude !== "" && report.longitude !== null) {
                gpsParts.push(`GPS: ${report.latitude}, ${report.longitude}`);
            }
            if (report.accuracy) {
                gpsParts.push(`Accuracy: ${report.accuracy}`);
            }
            if (report.source) {
                gpsParts.push(`Source: ${report.source}`);
            }
            gpsNode.textContent = gpsParts.length > 0 ? gpsParts.join(" • ") : "GPS unavailable";
        }

        if (primaryImage) {
            primaryImage.src = report.primaryImage || "https://images.unsplash.com/photo-1590005354167-6da97870c913?auto=format&fit=crop&w=480&q=80";
        }

        if (notesInput) {
            notesInput.value = report.notes || "";
        }
        if (notesDisplay) {
            notesDisplay.textContent = report.notes || "No notes logged.";
        }
        if (expertInput) {
            expertInput.value = "";
        }

        if (currentReportModalMode === "scan") {
            const scanPreviewGrid = document.getElementById("supporting-preview-grid");
            if (scanPreviewGrid && report.additionalImages.length === 0) {
                renderAdditionalImages(scanPreviewGrid, []);
            }
        } else {
            renderAdditionalImages(document.getElementById("report-additional-images-grid"), report.additionalImages);
        }
        renderList(document.getElementById("report-initial-list"), report.initialRecommendations, "No initial recommendations available.");
        renderList(document.getElementById("report-expert-list"), report.expertRecommendations, "No expert recommendation available yet.");

        applyStatusStyle(report);
        applyModeState(currentReportModalMode, report);
        renderWorkflowActions(currentReportModalMode, report);

        if (expertCard) {
            setDisplay(expertCard, true, "flex");
        }

        setReportModalSubmissionState(false);
        modalRoot.classList.add("open-modal");
        modalRoot.setAttribute("aria-hidden", "false");
    }

    window.openReportModal = openReportModal;
    window.closeReportModal = closeReportModal;
    window.resolveReportImageUrl = resolveReportImageUrl;
    window.setReportModalSubmissionState = setReportModalSubmissionState;
    window.abortReportSubmission = abortActiveReportModalSubmission;

    window.__cocoScanReportModal = {
        get currentReport() {
            return currentReportModalRecord;
        },
        get currentMode() {
            return currentReportModalMode;
        },
        closeReportModal,
    };
})();