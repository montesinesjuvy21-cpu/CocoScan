(function () {
    const SUPABASE_REPORT_IMAGE_BASE_URL =
        "https://utvltqgxqnpcqrphuojc.supabase.co/storage/v1/object/public/reports/";

    // Inject compact schedule input styles once so templates don't need edits
    (function injectScheduleInputStyles() {
        if (typeof document === 'undefined' || document.getElementById('schedule-input-styles')) return;
        const css = `
            .schedule-input {
                width: 100%;
                box-sizing: border-box;
                height: 44px;
                line-height: 44px;
                padding: 6px 10px;
                border-radius: 10px;
                font-size: 0.95rem;
                border: 1px solid #e6eaf0;
                background: #ffffff;
                -webkit-appearance: none;
                appearance: none;
                vertical-align: middle;
            }
            /* ensure date/time controls align visually when placed in grid columns */
            .farmer-schedule-row .schedule-input { display: block; }
            .farmer-schedule-row { box-sizing: border-box; box-shadow: 0 1px 2px rgba(16,24,40,0.04); }
            .farmer-schedule-row .remove-schedule-btn { width: 100%; justify-self: stretch; margin-top: 8px; }
        `;
        const style = document.createElement('style');
        style.id = 'schedule-input-styles';
        style.appendChild(document.createTextNode(css));
        document.head.appendChild(style);
    })();

    let currentReportModalRecord = null;
    let currentReportModalMode = "farmer";
    let activeReportModalSubmissionController = null;
    let currentWorkflowDefaultSubmitAction = null;

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
        const notes = reportData.notes || reportData.field_notes || reportData.farmer_notes || "";
        const feedbackData = extractFarmerFeedback(notes, reportData.status);

        return {
            id: reportData.id ?? null,
            mode: reportData.mode || currentReportModalMode,
            pest: reportData.pest || reportData.pest_type || reportData.prediction || "Unknown Pest",
            confidence: normalizeConfidence(reportData.confidence || reportData.pest_confidence),
            status: String(reportData.status || reportData.current_status || "").trim() || (currentReportModalMode === "scan" ? "Ready to Submit" : "Pending"),
            timestamp: reportData.timestamp || reportData.created_at || reportData.submitted_at || reportData.photo_taken_at || "",
            farmer: reportData.farmer || reportData.farmer_name || "Farmer",
            notes,
            locationText: reportData.location_text || reportData.full_location || reportData.location || "No location logged",
            latitude: gps.latitude ?? reportData.latitude ?? "",
            longitude: gps.longitude ?? reportData.longitude ?? "",
            accuracy: gps.accuracy ?? reportData.gps_accuracy ?? "",
            source: gps.source ?? reportData.location_source ?? "",
            primaryImage: resolveReportImageUrl(primaryImage),
            additionalImages,
            initialRecommendations: normalizeList(reportData.initial_recommendations || reportData.recommendations),
            expertRecommendations: normalizeList(reportData.expert_recommendations || reportData.expert_recommendation),
            farmerFeedbackReason: feedbackData.reason,
            farmerFeedbackConfirmation: feedbackData.confirmation,
            farmerSchedules: feedbackData.schedules,
            weather: reportData.weather || {},
        };
    }

    function extractFarmerFeedback(notes = "", status = "") {
        const raw = String(notes || "").trim();
        const feedback = { reason: "", confirmation: "", schedules: [] };

        if (/Farmer confirmed the assessment resolved/i.test(raw) || /confirmed the assessment resolved/i.test(raw)) {
            feedback.confirmation = "resolved";
            return feedback;
        }

        if (/farmer requested a visit/i.test(raw)) {
            const reasonMatch = raw.match(/Reason:\s*([^\.]+)\./i);
            feedback.reason = reasonMatch ? reasonMatch[1].trim() : "";

            const optionRegex = /Option\s*\d+:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*at\s*([0-9]{2}:[0-9]{2})\./gi;
            let match;
            while ((match = optionRegex.exec(raw)) !== null) {
                const date = match[1];
                const time = match[2];
                let display = `${date} ${time}`;
                try {
                    const dt = new Date(`${date}T${time}`);
                    if (!Number.isNaN(dt.getTime())) {
                        display = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(dt) + ' • ' + new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).format(dt);
                    }
                } catch (e) {
                    // keep fallback
                }
                feedback.schedules.push({ date, time, display });
            }
        }

        return feedback;
    }

    function getStatusKey(status) {
        return String(status || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    }

    function setDisplay(element, visible, displayValue = "block") {
        if (!element) return;
        element.style.display = visible ? displayValue : "none";
    }

    function getWorkflowStatusDisplayLabel(status) {
        const normalized = getStatusKey(status);
        const labels = {
            "under_review": "Under Review",
            "assessment_issued": "Assessment Issued",
            "visit_requested": "Visit Requested",
            "waiting_for_agriculturist_confirmation": "Waiting for Agriculturist Confirmation",
            "waiting_agriculturist_confirmation": "Waiting for Agriculturist Confirmation",
            "visit_scheduled": "Visit Scheduled",
            "visit_completed": "Visit Completed",
            "final_remarks_issued": "Final Remarks Issued",
            "recommendation_issued": "Recommendation Issued",
            "closed": "Closed",
            "resolved": "Resolved",
        };
        return labels[normalized] || normalized || "Pending";
    }

    function getWorkflowStatusBadgeStyle(status) {
        const normalized = getStatusKey(status);
        const palette = {
            "under_review": { backgroundColor: "#fef3c7", color: "#92400e" },
            "assessment_issued": { backgroundColor: "#ecfdf5", color: "#065f46" },
            "visit_requested": { backgroundColor: "#fdf2f8", color: "#be185d" },
            "waiting_for_agriculturist_confirmation": { backgroundColor: "#eff6ff", color: "#1d4ed8" },
            "waiting_agriculturist_confirmation": { backgroundColor: "#eff6ff", color: "#1d4ed8" },
            "visit_scheduled": { backgroundColor: "#fefce8", color: "#a16207" },
            "visit_completed": { backgroundColor: "#ecfeff", color: "#0f766e" },
            "final_remarks_issued": { backgroundColor: "#ede9fe", color: "#5b21b6" },
            "recommendation_issued": { backgroundColor: "#ecfdf5", color: "#065f46" },
            "resolved": { backgroundColor: "#dcfce7", color: "#166534" },
            "closed": { backgroundColor: "#dcfce7", color: "#166534" },
        };
        return palette[normalized] || { backgroundColor: "#f8fafc", color: "#475569" };
    }

    function isRecommendationIssuedStatus(status) {
        const normalized = getStatusKey(status);
        return [
            "recommendation_issued",
            "recommendation-issued",
            "reviewed",
            "reviewed_&_issued",
            "final_remarks_issued",
            "resolved",
            "closed",
            "completed",
            "assessment_issued",
            "assessment-issued",
            "assessment issued",
        ].includes(normalized);
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
            const statusStyle = getWorkflowStatusBadgeStyle(report.status || "--");
            statusNode.textContent = getWorkflowStatusDisplayLabel(report.status || "--");
            statusNode.style.color = statusStyle.color;
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

        const statusKey = getStatusKey(report?.status || "");
        const assessmentAlreadyIssued = ["assessment_issued", "recommendation_issued", "waiting_for_agriculturist_confirmation", "waiting_agriculturist_confirmation", "visit_requested", "visit_scheduled", "visit_completed", "final_remarks_issued", "resolved", "closed"].includes(statusKey) || (Array.isArray(report.expertRecommendations) && report.expertRecommendations.length > 0);

        setDisplay(scanButton, mode === "scan", "flex");
        setDisplay(farmerButton, false, "flex");
        setDisplay(agriButton, mode === "agriculturist" && !assessmentAlreadyIssued && !isReviewed, "flex");
        setDisplay(cancelButton, true, "inline-flex");

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

        // Agriculturist submit button state: disable when assessment already issued or report reviewed
        if (agriButton) {
            const statusKey = getStatusKey(report?.status || "");
            const assessmentAlreadyIssued = statusKey === "assessment_issued";
            const disableAgri = assessmentAlreadyIssued || isReviewed;
            agriButton.disabled = disableAgri;
            agriButton.classList.toggle("is-disabled", disableAgri);
            agriButton.setAttribute("aria-disabled", String(disableAgri));
            if (disableAgri) {
                agriButton.style.backgroundColor = "#cbd5e1";
                agriButton.style.color = "#475569";
                agriButton.innerHTML = '<i class="fa-solid fa-lock"></i> Assessment Issued';
            } else {
                if (agriButton.dataset.defaultHtml) {
                    agriButton.innerHTML = agriButton.dataset.defaultHtml;
                } else {
                    agriButton.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Submit Assessment';
                }
                agriButton.style.backgroundColor = "";
                agriButton.style.color = "";
            }
        }

        if (expertInput) {
            const statusKey = getStatusKey(report?.status || "");
            const allowExpertInput = mode === "agriculturist" && !isReviewed && statusKey !== "assessment_issued";
            setDisplay(expertInput, allowExpertInput, "block");
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
    }

    async function submitExpertAssessment() {
        const expertInput = document.getElementById("expert-notes-input");
        const report = currentReportModalRecord;
        if (!report?.id) {
            alert("This report does not have a valid identifier.");
            return;
        }
        if (!expertInput) {
            return submitWorkflowAction(currentWorkflowDefaultSubmitAction || "submit-assessment");
        }

        const assessment = String(expertInput.value || "").trim();
        if (!assessment) {
            alert("Please provide expert assessment notes before submitting.");
            return;
        }

        setReportModalSubmissionState(true, "Submitting assessment…");
        try {
            const response = await fetch("/agriculturist/submit-assessment", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ report_id: report.id, assessment_notes: assessment }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) {
                alert(data.message || "The assessment could not be saved.");
                return;
            }
            report.status = "assessment_issued";
            if (!Array.isArray(report.expertRecommendations)) {
                report.expertRecommendations = [];
            }
            report.expertRecommendations.push(assessment);
            renderList(document.getElementById("report-expert-list"), report.expertRecommendations, "No expert recommendation available yet.");
            applyStatusStyle(report);
            renderWorkflowActions(currentReportModalMode, report);
            // Refresh lists on the page if available and close modal for agriculturists
            if (typeof window.  renderReportsGrid === "function") {
                try { window.renderReportsGrid(); } catch (e) { console.debug(e); }
            }
            if (currentReportModalMode === "agriculturist") {
                closeReportModal();
            }
            alert(data.message || "Assessment notes saved successfully.");
        } catch (error) {
            console.error("Assessment submission error:", error);
            alert("The assessment could not be submitted right now.");
        } finally {
            setReportModalSubmissionState(false);
        }
    }

    window.submitExpertValidation = function () {
        return submitExpertAssessment();
    };

    function renderWorkflowActions(mode, report = currentReportModalRecord) {
        const workflowCard = document.getElementById("workflow-actions-card");
        const workflowHelp = document.getElementById("workflow-actions-help");
        const workflowButtons = document.getElementById("workflow-actions-buttons");
        const workflowInput = document.getElementById("workflow-detail-input");
        const workflowFormFields = document.getElementById("workflow-form-fields");
        const feedbackContainer = document.getElementById("report-farmer-feedback");
        if (!workflowCard || !workflowButtons) {
            return;
        }

        const normalizedStatus = getStatusKey(report?.status || "");
        workflowButtons.innerHTML = "";
        currentWorkflowDefaultSubmitAction = null;
        if (workflowFormFields) {
            workflowFormFields.innerHTML = "";
        }
        if (workflowInput) {
            workflowInput.value = "";
            workflowInput.style.display = "block";
            workflowInput.placeholder = "Add notes, a reason, availability, or the selected schedule...";
        }

        const actions = [];
        if (mode === "farmer") {
            setDisplay(workflowCard, false);
        }
        if (feedbackContainer) {
            feedbackContainer.innerHTML = "";
            const feedbackCard = document.getElementById('report-farmer-feedback-card');
            if (feedbackCard) setDisplay(feedbackCard, false, 'block');
        }
        if (mode === "agriculturist") {
            // Agriculturist uses the report-expert-card for assessment submission in pending view.
            // Do not create a workflow action for initial assessment here to avoid duplicating UI.
            if (normalizedStatus === "visit_requested") {
                actions.push({
                    label: Array.isArray(report.farmerSchedules) && report.farmerSchedules.length ? "Confirm Selected Schedule" : "Accept Request",
                    icon: "fa-solid fa-calendar-check",
                    action: "accept-visit-request",
                    help: "Confirm one of the farmer's preferred schedules or choose a custom visit date/time.",
                });
                actions.push({
                    label: "Reject Request",
                    icon: "fa-solid fa-ban",
                    action: "reject-visit-request",
                    help: "Reject the visit request and explain why.",
                });
                if (workflowFormFields) {
                    if (Array.isArray(report.farmerSchedules) && report.farmerSchedules.length) {
                        workflowFormFields.innerHTML = `
                        <div style="display:grid; gap:10px;">
                            <p style="margin:0; font-weight:600; color:#334155;">Or pick a custom schedule instead</p>
                            <div style="display:grid; gap:8px; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));">
                                    <div style="display:grid; gap:6px;"><label style="font-size:0.9rem; font-weight:600; color:#334155;">Preferred date</label><input id="visit-review-date" type="date" class="schedule-input"></div>
                                    <div style="display:grid; gap:6px;"><label style="font-size:0.9rem; font-weight:600; color:#334155;">Preferred time</label><input id="visit-review-time" type="time" class="schedule-input"></div>
                                </div>
                        </div>`;
                    } else {
                        workflowFormFields.innerHTML = `
                        <div style="display:grid; gap:10px;">
                            <label style="font-size:0.9rem; font-weight:600; color:#334155;">Decision</label>
                            <select id="visit-review-decision" style="min-height:auto; padding:10px 12px; width:100%; box-sizing:border-box;">
                                <option value="accept">Accept request</option>
                                <option value="reject">Reject request</option>
                            </select>
                                <div style="display:grid; gap:8px; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));">
                                <div style="display:grid; gap:6px;">
                                    <label style="font-size:0.9rem; font-weight:600; color:#334155;">Preferred date</label>
                                    <input id="visit-review-date" type="date" class="schedule-input">
                                </div>
                                <div style="display:grid; gap:6px;">
                                    <label style="font-size:0.9rem; font-weight:600; color:#334155;">Preferred time</label>
                                    <input id="visit-review-time" type="time" class="schedule-input">
                                </div>
                            </div>
                        </div>`;
                    }
                }
                if (feedbackContainer) {
                    const summaryMessage = report.farmerFeedbackReason
                        ? `<p style="margin:0; font-size:0.95rem; color:#334155;"><strong>Farmer request reason:</strong> ${escapeHtml(report.farmerFeedbackReason)}</p>`
                        : `<p style="margin:0; font-size:0.95rem; color:#334155;">The farmer has requested a visit.</p>`;
                    feedbackContainer.innerHTML = `
                            <p style="font-size:0.92rem; color:#334155; margin:0 0 10px;">Farmer feedback has been submitted and is ready for review.</p>
                            ${summaryMessage}`;
                    const feedbackCard = document.getElementById('report-farmer-feedback-card');
                    if (feedbackCard) setDisplay(feedbackCard, true, 'block');
                }
            } else if (normalizedStatus === "visit_scheduled") {
                actions.push({
                    label: "Complete Visit",
                    icon: "fa-solid fa-circle-check",
                    action: "complete-visit",
                    help: "Record the visit summary and upload one or more visit images.",
                });
                if (workflowInput) {
                    workflowInput.placeholder = "Enter the visit summary and findings...";
                }
                if (workflowFormFields) {
                    workflowFormFields.innerHTML = `
                        <div style="display:grid; gap:10px;">
                            <label style="font-size:0.9rem; font-weight:600; color:#334155;">Visit images</label>
                            <input id="workflow-visit-images" type="file" accept="image/*" multiple style="min-height:auto; padding:12px 14px;">
                        </div>`;
                }
            } else if (normalizedStatus === "visit_completed") {
                actions.push({
                    label: "Submit Final Remarks",
                    icon: "fa-solid fa-comment-dots",
                    action: "submit-final-remarks",
                    help: "Submit the final remarks and optional notes for closure.",
                });
                if (workflowInput) {
                    workflowInput.placeholder = "Enter the final remarks for the report...";
                }
                if (workflowFormFields) {
                    workflowFormFields.innerHTML = `
                        <div style="display:grid; gap:10px;">
                            <label style="font-size:0.9rem; font-weight:600; color:#334155;">Additional notes</label>
                            <textarea id="workflow-additional-notes" class="notes-input-box" placeholder="Add any optional follow-up notes..." style="min-height:90px;"></textarea>
                        </div>`;
                }
            } else if (normalizedStatus === "final_remarks_issued") {
                actions.push({
                    label: "Mark as Resolved",
                    icon: "fa-solid fa-check-double",
                    action: "mark-resolved",
                    help: "Close the case after the final remarks are issued.",
                });
                if (workflowInput) {
                    workflowInput.placeholder = "Optional closing note for the case...";
                }
            }
        } else if (mode === "farmer") {
            if (normalizedStatus === "assessment_issued") {
                actions.push({
                    label: "Submit Feedback",
                    icon: "fa-solid fa-comments",
                    action: "farmer-feedback",
                    help: "Tell us whether the assessment helped your issue. If not, request a visit.",
                });
                if (workflowInput) {
                    setDisplay(workflowInput, false);
                }
                if (feedbackContainer) {
                    feedbackContainer.innerHTML = `
                        <div style="display:grid; gap:18px; padding:8px 0;">
                           <p style="font-size:0.92rem; color:#334155; margin:0; line-height:1.55;">
                                Did the initial recommendation and expert assessment resolve your issue?<br>
                                <em style="font-size:0.72rem; color:#64748b;">
                                    If not, you can request an on-site visit and provide your preferred schedule.
                                </em>
                            </p>
                            <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-bottom:0;">
                                <label style="display:flex; align-items:center; gap:8px; font-weight:600; color:#102a43;">
                                    <input type="radio" name="farmer-feedback-choice" value="resolved" checked style="accent-color:#059669;"> Yes
                                </label>
                                <label style="display:flex; align-items:center; gap:8px; font-weight:600; color:#102a43;">
                                    <input type="radio" name="farmer-feedback-choice" value="needs-assistance" style="accent-color:#be185d;"> No
                                </label>
                            </div>
                            <div id="farmer-visit-request-details" style="display:none; display:grid; gap:16px; padding-top:10px;">
                                <div style="display:grid; gap:10px;">
                                    <strong style="font-size:0.95rem;">Choose up to 3 preferred schedules</strong>
                                    <button type="button" id="farmer-add-schedule-btn" class="btn-control submit-primary" style="min-height:42px; padding:10px 14px; justify-self:start;">+ Add Schedule</button>
                                </div>
                                <div style="display:grid; gap:8px;">
                                    <label style="font-size:0.9rem; font-weight:600; color:#334155; margin-bottom:6px;">Reason for requesting a visit</label>
                                    <textarea id="farmer-visit-reason" class="notes-input-box" placeholder="Describe why you still need assistance..." style="min-height:110px; width:100%; box-sizing:border-box; padding:14px 16px;"></textarea>
                                </div>
                                <div id="farmer-schedules-list" style="display:grid; gap:16px;"></div>
                            </div>
                            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:6px;">
                                <button id="farmer-submit-feedback-btn" class="btn-control submit-primary" type="button">Submit Request</button>
                            </div>
                        </div>`;
                    // Attach add schedule behavior and initialize one row
                    const schedulesList = document.getElementById('farmer-schedules-list');
                    const addBtn = document.getElementById('farmer-add-schedule-btn');
                    if (schedulesList && addBtn) {
                        addBtn.addEventListener('click', (ev) => {
                            addFarmerScheduleRow(schedulesList);
                        });
                        // start with one schedule row
                        addFarmerScheduleRow(schedulesList);
                    }
                    // Wire submit button to trigger the workflow action click
                    const submitFeedbackBtn = document.getElementById('farmer-submit-feedback-btn');
                    if (submitFeedbackBtn) {
                        submitFeedbackBtn.addEventListener('click', () => submitWorkflowAction('farmer-feedback'));
                    }
                    const feedbackRadios = feedbackContainer.querySelectorAll("input[name='farmer-feedback-choice']");
                    const requestDetails = feedbackContainer.querySelector("#farmer-visit-request-details");
                    const refreshFeedbackDetails = () => {
                        const selectedValue = Array.from(feedbackRadios).find((input) => input.checked)?.value || "resolved";
                        if (requestDetails) {
                            setDisplay(requestDetails, selectedValue === 'needs-assistance', 'grid');
                        }
                    };
                    feedbackRadios.forEach((input) => input.addEventListener('change', refreshFeedbackDetails));
                    refreshFeedbackDetails();
                    const feedbackCard = document.getElementById('report-farmer-feedback-card');
                    if (feedbackCard) setDisplay(feedbackCard, true, 'block');
                }
            } else if (normalizedStatus === "visit_requested" || normalizedStatus === "resolved") {
                if (workflowInput) {
                    setDisplay(workflowInput, false);
                }
                if (feedbackContainer) {
                    const reasonDisplay = report.farmerFeedbackReason ? `<p style="margin:0; font-size:0.95rem; color:#334155;"><strong>Reason:</strong> ${escapeHtml(report.farmerFeedbackReason)}</p>` : "";
                    const scheduleDisplay = Array.isArray(report.farmerSchedules) && report.farmerSchedules.length
                        ? `<div style="display:grid; gap:6px; padding-top:8px;">${report.farmerSchedules.map(s => `<div style="font-size:0.95rem; color:#0f172a;">• ${escapeHtml(s.display)}</div>`).join("")}</div>`
                        : "";
                    const message = normalizedStatus === "visit_requested"
                        ? `<p style="font-size:0.92rem; color:#334155; margin:0;">Your visit request was submitted successfully. The agriculturist will review your preferred schedules.</p>${reasonDisplay}${scheduleDisplay}`
                        : `<p style="font-size:0.92rem; color:#334155; margin:0;">Thank you! You confirmed the assessment resolved your issue.</p>`;
                    feedbackContainer.innerHTML = `
                        <div style="margin-top:10px; padding:12px; border:1px solid #e2e8f0; border-radius:12px; background:#f8fafc; display:grid; gap:12px;">
                            ${message}
                        </div>`;
                    const feedbackCard = document.getElementById('report-farmer-feedback-card');
                    if (feedbackCard) setDisplay(feedbackCard, true, 'block');
                }
            } else {
                if (feedbackContainer) {
                    feedbackContainer.innerHTML = "";
                }
                const feedbackCard = document.getElementById('report-farmer-feedback-card');
                if (feedbackCard) setDisplay(feedbackCard, false, 'block');
            }
            return;
        }

        if (workflowHelp) {
            workflowHelp.textContent = actions[0]?.help || "Advance the report to the next stage.";
        }

        if (actions.length === 0) {
            setDisplay(workflowCard, false, "block");
            return;
        }

        setDisplay(workflowCard, true, "block");
        currentWorkflowDefaultSubmitAction = actions[0]?.action || null;
        actions.forEach((action) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn-control submit-primary";
            button.innerHTML = `<i class="${action.icon}"></i> ${action.label}`;
            button.onclick = () => submitWorkflowAction(action.action);
            workflowButtons.appendChild(button);
        });

        const feedbackRadios = feedbackContainer?.querySelectorAll("input[name='farmer-feedback-choice']");
        const requestDetails = feedbackContainer?.querySelector("#farmer-visit-request-details");
        const actionButton = workflowButtons.querySelector("button");

        if (feedbackRadios && feedbackRadios.length && actionButton) {
            const refreshFormState = () => {
                const selectedValue = Array.from(feedbackRadios).find((input) => input.checked)?.value || "resolved";
                const showDetails = selectedValue === "needs-assistance";
                if (requestDetails) {
                    setDisplay(requestDetails, showDetails, "grid");
                }
                actionButton.innerHTML = `<i class="fa-solid ${showDetails ? 'fa-calendar-plus' : 'fa-check-circle'}"></i> ${showDetails ? 'Request Visit' : 'Confirm Resolved'}`;
            };
            feedbackRadios.forEach((input) => input.addEventListener("change", refreshFormState));
            refreshFormState();
        }
    }

    /* Helper functions for dynamic farmer schedule rows inside the feedback card */
    function addFarmerScheduleRow(container, dateVal = "", timeVal = "") {
        if (!container) return;
        const existing = container.querySelectorAll('.farmer-schedule-row');
        if (existing.length >= 3) return;
        const idx = existing.length + 1;
        const row = document.createElement('div');
        row.className = 'farmer-schedule-row';
        row.style.display = 'grid';
        row.style.gridTemplateColumns = '1fr';
        row.style.gap = '12px';
        row.style.padding = '14px';
        row.style.marginBottom = '14px';
        row.style.borderRadius = '16px';
        row.style.backgroundColor = '#fff';
        row.innerHTML = `
            <div style="display:grid; gap:12px;">
                <strong style="font-size:0.95rem; color:#102a43;">Preferred Schedule #${idx}</strong>
                <label style="display:grid; gap:4px; font-size:0.9rem; color:#334155;">
                    <span style="font-weight:500;">Date</span>
                    <input type="date" class="farmer-schedule-date schedule-input" value="${escapeHtml(dateVal)}">
                </label>

                <label style="display:grid; gap:4px; font-size:0.9rem; color:#334155;">
                    <span style="font-weight:500;">Time</span>
                    <input type="time" class="farmer-schedule-time schedule-input" value="${escapeHtml(timeVal)}">
                </label>
            </div>
            <button type="button" class="btn-control cancel-secondary remove-schedule-btn" style="min-height:36px; padding:10px 12px; white-space:nowrap; width:100%; margin-top:8px;">Remove</button>
        `;
        container.appendChild(row);
        row.querySelector('.remove-schedule-btn').addEventListener('click', () => { row.remove(); });
    }

    function collectFarmerSchedules(container) {
        if (!container) return [];
        const rows = Array.from(container.querySelectorAll('.farmer-schedule-row'));
        const schedules = rows.map(r => {
            const d = r.querySelector('.farmer-schedule-date')?.value || '';
            const t = r.querySelector('.farmer-schedule-time')?.value || '';
            let display = '';
            if (d && t) {
                try {
                    const dt = new Date(`${d}T${t}`);
                    display = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(dt) + ' • ' + new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).format(dt);
                } catch (e) { display = `${d} ${t}`; }
            }
            return { date: d, time: t, display };
        }).filter(s => s.date && s.time);
        return schedules.slice(0,3);
    }

    async function submitWorkflowAction(actionName) {
        const workflowInput = document.getElementById("workflow-detail-input");
        const report = currentReportModalRecord;
        if (!report?.id) {
            alert("This report is missing an identifier.");
            return;
        }

        const formData = new FormData();
        formData.append("report_id", report.id);

        if (actionName === "submit-assessment") {
            const detail = (workflowInput?.value || "").trim();
            if (!detail) {
                alert("Please provide assessment notes before submitting.");
                return;
            }
            formData.append("assessment_notes", detail);
            try {
                const response = await fetch("/agriculturist/submit-assessment", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The assessment could not be saved.");
                    return;
                }
                report.status = "assessment_issued";
                applyStatusStyle(report);
                if (typeof window.renderReportsGrid === "function") {
                    try { window.renderReportsGrid(); } catch (e) { console.debug(e); }
                }
                renderWorkflowActions(currentReportModalMode, report);
                // Close modal for agriculturist after submit
                if (currentReportModalMode === 'agriculturist') closeReportModal();
                alert(data.message || "Assessment notes saved.");
            } catch (error) {
                alert("The assessment could not be saved right now.");
            }
            return;
        }

        if (actionName === "farmer-feedback") {
            const feedbackChoice = document.querySelector("input[name='farmer-feedback-choice']:checked")?.value || "resolved";
            formData.append("confirmation", feedbackChoice === "resolved" ? "resolved" : "needs-assistance");
            if (feedbackChoice !== "resolved") {
                const reason = document.getElementById("farmer-visit-reason")?.value?.trim() || "";
                const schedulesList = document.getElementById('farmer-schedules-list');
                const schedules = collectFarmerSchedules(schedulesList);
                if (!reason || schedules.length === 0) {
                    alert("Please provide a reason and at least one preferred date/time option before submitting.");
                    return;
                }
                formData.append("reason", reason);
                schedules.forEach((s, idx) => {
                    formData.append(`preferred_date_${idx+1}`, s.date);
                    formData.append(`preferred_time_${idx+1}`, s.time || "");
                });
                // keep the schedules and reason locally so agriculturists can see them immediately
                report.farmerSchedules = schedules.map(s => ({ date: s.date, time: s.time, display: s.display }));
                report.farmerFeedbackReason = reason;
                report.farmerFeedbackConfirmation = "needs-assistance";
            } else {
                report.farmerSchedules = [];
                report.farmerFeedbackReason = "";
                report.farmerFeedbackConfirmation = "resolved";
            }
            try {
                const response = await fetch("/farmer/submit-assessment-feedback", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The feedback could not be saved.");
                    return;
                }
                report.status = feedbackChoice === "resolved" ? "resolved" : "visit_requested";
                applyStatusStyle(report);
                if (typeof window.renderReportsGrid === "function") {
                    try { window.renderReportsGrid(); } catch (e) { console.debug(e); }
                }
                renderWorkflowActions(currentReportModalMode, report);
                alert(data.message || "Feedback saved.");
            } catch (error) {
                alert("The feedback could not be saved right now.");
            }
            return;
        }

        if (actionName === "accept-visit-request" || actionName === "reject-visit-request") {
            const decision = actionName === "accept-visit-request" ? "accept" : "reject";
            const detail = (workflowInput?.value || "").trim();
            formData.append("decision", decision);
            if (decision === "accept") {
                // Allow selecting from farmer-provided schedules or a custom date/time
                const selectedIdx = document.querySelector("input[name='agri-selected-schedule']:checked")?.value;
                if (selectedIdx !== undefined && selectedIdx !== null && report.farmerSchedules && report.farmerSchedules[selectedIdx]) {
                    const picked = report.farmerSchedules[selectedIdx];
                    formData.append("preferred_date", picked.date);
                    formData.append("preferred_time", picked.time || "");
                } else {
                    const preferredDate = document.getElementById("visit-review-date")?.value || "";
                    const preferredTime = document.getElementById("visit-review-time")?.value || "";
                    if (!preferredDate || !preferredTime) {
                        alert("Please confirm the visit date and time before accepting the request.");
                        return;
                    }
                    formData.append("preferred_date", preferredDate);
                    formData.append("preferred_time", preferredTime);
                }
            } else {
                if (!detail) {
                    alert("Please add a rejection reason before submitting.");
                    return;
                }
                formData.append("reason", detail);
            }
            try {
                const response = await fetch("/agriculturist/review-visit-request", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The visit review could not be saved.");
                    return;
                }
                report.status = decision === "accept" ? "visit_scheduled" : "assessment_issued";
                applyStatusStyle(report);
                renderWorkflowActions(currentReportModalMode, report);
                if (typeof window.renderReportsGrid === "function") {
                    try { window.renderReportsGrid(); } catch (e) { console.debug(e); }
                }
                alert(data.message || "Visit request updated.");
            } catch (error) {
                alert("The visit review could not be saved right now.");
            }
            return;
        }

        if (actionName === "complete-visit") {
            const detail = (workflowInput?.value || "").trim();
            const visitImages = document.getElementById("workflow-visit-images")?.files || [];
            if (!detail) {
                alert("Please add a visit summary before submitting.");
                return;
            }
            if (!visitImages.length) {
                alert("Please upload at least one visit image before submitting.");
                return;
            }
            formData.append("visit_summary", detail);
            Array.from(visitImages).forEach((file) => formData.append("visit_images", file));
            try {
                const response = await fetch("/agriculturist/complete-visit", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The visit summary could not be saved.");
                    return;
                }
                report.status = "visit_completed";
                applyStatusStyle(report);
                renderWorkflowActions(currentReportModalMode, report);
                alert(data.message || "Visit details saved.");
            } catch (error) {
                alert("The visit summary could not be saved right now.");
            }
            return;
        }

        if (actionName === "submit-final-remarks") {
            const detail = (workflowInput?.value || "").trim();
            const additionalNotes = document.getElementById("workflow-additional-notes")?.value?.trim() || "";
            if (!detail) {
                alert("Please provide final remarks before submitting.");
                return;
            }
            formData.append("final_remarks", detail);
            if (additionalNotes) {
                formData.append("additional_notes", additionalNotes);
            }
            try {
                const response = await fetch("/agriculturist/submit-final-remarks", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The final remarks could not be saved.");
                    return;
                }
                report.status = "final_remarks_issued";
                applyStatusStyle(report);
                renderWorkflowActions(currentReportModalMode, report);
                alert(data.message || "Final remarks saved.");
            } catch (error) {
                alert("The final remarks could not be saved right now.");
            }
            return;
        }

        if (actionName === "mark-resolved") {
            const detail = (workflowInput?.value || "").trim();
            if (detail) {
                formData.append("resolution_note", detail);
            }
            try {
                const response = await fetch("/agriculturist/mark-resolved", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The case could not be marked resolved.");
                    return;
                }
                report.status = "resolved";
                applyStatusStyle(report);
                renderWorkflowActions(currentReportModalMode, report);
                alert(data.message || "The report has been marked as resolved.");
            } catch (error) {
                alert("The case could not be marked resolved right now.");
            }
            return;
        }

        alert("This workflow step is not available yet.");
    }

    async function submitExpertAssessment() {
        const expertInput = document.getElementById("expert-notes-input");
        const report = currentReportModalRecord;
        if (!report?.id) {
            alert("This report does not have a valid identifier.");
            return;
        }
        if (!expertInput) {
            return submitWorkflowAction(currentWorkflowDefaultSubmitAction || "submit-assessment");
        }

        const assessment = String(expertInput.value || "").trim();
        if (!assessment) {
            alert("Please provide expert assessment notes before submitting.");
            return;
        }

        setReportModalSubmissionState(true, "Submitting assessment…");
        try {
            const response = await fetch("/agriculturist/submit-assessment", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ report_id: report.id, assessment_notes: assessment }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) {
                alert(data.message || "The assessment could not be saved.");
                return;
            }
            report.status = "assessment_issued";
            if (!Array.isArray(report.expertRecommendations)) {
                report.expertRecommendations = [];
            }
            report.expertRecommendations.push(assessment);
            renderList(document.getElementById("report-expert-list"), report.expertRecommendations, "No expert recommendation available yet.");
            applyStatusStyle(report);
            renderWorkflowActions(currentReportModalMode, report);
            alert(data.message || "Assessment notes saved successfully.");
        } catch (error) {
            console.error("Assessment submission error:", error);
            alert("The assessment could not be submitted right now.");
        } finally {
            setReportModalSubmissionState(false);
        }
    }

    window.submitExpertValidation = function () {
        return submitExpertAssessment();
    };

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

        const isReviewed = isRecommendationIssuedStatus(report?.status || "");

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

        // Expert card visibility and input controls depend on existing assessment state
        const statusKey = getStatusKey(report?.status || "");
        const assessmentAlreadyIssued = ["assessment_issued", "recommendation_issued", "waiting_for_agriculturist_confirmation", "waiting_agriculturist_confirmation", "visit_requested", "visit_scheduled", "visit_completed", "final_remarks_issued", "resolved", "closed"].includes(statusKey) || (Array.isArray(report.expertRecommendations) && report.expertRecommendations.length > 0);
        if (expertCard) {
            setDisplay(expertCard, true, "flex");
            const expertInput = document.getElementById("expert-notes-input");
            const expertHelp = document.getElementById("expert-notes-help");
            setDisplay(expertInput, currentReportModalMode === "agriculturist" && !assessmentAlreadyIssued, "block");
            setDisplay(expertHelp, currentReportModalMode === "agriculturist" && !assessmentAlreadyIssued, "block");
        }

        // Render any farmer schedules into a dedicated display area for agriculturists
        const schedulesNode = document.getElementById("report-farmer-preferred-schedules");
        if (schedulesNode) {
            schedulesNode.innerHTML = "";
            const schedules = report.farmerSchedules || [];
            if (Array.isArray(schedules) && schedules.length) {
                const wrapper = document.createElement('div');
                wrapper.style.display = 'grid';
                wrapper.style.gap = '8px';
                const title = document.createElement('h4');
                title.style.margin = '0';
                title.style.fontSize = '0.98rem';
                title.textContent = "Farmer's Preferred Schedules";
                wrapper.appendChild(title);
                schedules.forEach((s, idx) => {
                    const row = document.createElement('label');
                    row.style.display = 'flex';
                    row.style.alignItems = 'center';
                    row.style.gap = '8px';
                    row.style.fontSize = '0.95rem';
                    row.innerHTML = `<input type="radio" name="agri-selected-schedule" value="${idx}" style="accent-color:#1d4ed8;"> ${escapeHtml(s.display)}`;
                    wrapper.appendChild(row);
                });
                schedulesNode.appendChild(wrapper);
            }
            // Only show this card to agriculturists when schedules exist
            setDisplay(schedulesNode, Array.isArray(schedules) && schedules.length && currentReportModalMode === 'agriculturist', 'block');
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