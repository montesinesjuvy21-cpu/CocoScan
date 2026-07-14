(function () {
    const SUPABASE_REPORT_IMAGE_BASE_URL =
        "https://utvltqgxqnpcqrphuojc.supabase.co/storage/v1/object/public/reports/";

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

    function getWorkflowStatusDisplayLabel(status) {
        const normalized = String(status ?? "").trim();
        const labels = {
            "under_review": "Under Review",
            "assessment_issued": "Assessment Issued",
            "visit_requested": "Visit Requested",
            "waiting_agriculturist_confirmation": "Waiting for Agriculturist Confirmation",
            "visit_scheduled": "Visit Scheduled",
            "visit_completed": "Visit Completed",
            "final_remarks_issued": "Final Remarks Issued",
            "closed": "Closed",
            "resolved": "Resolved",
        };
        return labels[normalized] || normalized || "Pending";
    }

    function isRecommendationIssuedStatus(status) {
        const normalized = String(status ?? "").trim().toLowerCase();
        return [
            "recommendation issued",
            "reviewed",
            "reviewed & issued",
            "recommendation-issued",
            "recommendation_issued",
            "final_remarks_issued",
            "resolved",
            "closed",
            "completed",
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
            statusNode.textContent = getWorkflowStatusDisplayLabel(report.status || "--");
            statusNode.style.color = ["assessment_issued", "final_remarks_issued", "resolved", "closed"].includes(String(report.status || "").trim().toLowerCase()) ? "#059669" : "#d97706";
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
        // Show agriculturist button area when in agriculturist mode; disable if already issued or reviewed
        setDisplay(agriButton, mode === "agriculturist", "flex");
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

        // Agriculturist submit button state: disable when assessment already issued or report reviewed
        if (agriButton) {
            const normalizedStatus = String(report?.status || "").trim().toLowerCase();
            const assessmentAlreadyIssued = normalizedStatus === "assessment_issued";
            const disableAgri = assessmentAlreadyIssued || isReviewed;
            agriButton.disabled = disableAgri;
            agriButton.classList.toggle("is-disabled", disableAgri);
            agriButton.setAttribute("aria-disabled", String(disableAgri));
            if (disableAgri) {
                // Gray out and show issued label
                agriButton.style.backgroundColor = "#cbd5e1";
                agriButton.style.color = "#475569";
                agriButton.innerHTML = '<i class="fa-solid fa-lock"></i> Assessment Issued';
            } else {
                // Restore default appearance
                if (agriButton.dataset.defaultHtml) {
                    agriButton.innerHTML = agriButton.dataset.defaultHtml;
                } else {
                    agriButton.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Submit Assessment';
                }
                agriButton.style.backgroundColor = "";
                agriButton.style.color = "";
            }
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
        // Show expert input textarea only to agriculturist when report not yet reviewed
        if (expertInput) {
            setDisplay(expertInput, mode === "agriculturist" && !isReviewed, "block");
        }
        const payload = { report_id: currentReportModalRecord?.id, assessment_notes: advice };
        try {
            const res = await fetch('/agriculturist/submit-assessment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                alert(data.message || 'The assessment could not be saved.');
                return;
            }
            if (currentReportModalRecord) {
                currentReportModalRecord.status = 'assessment_issued';
                applyStatusStyle(currentReportModalRecord);
                renderWorkflowActions(currentReportModalMode, currentReportModalRecord);
            }
            alert(data.message || 'Assessment saved successfully.');
            closeReportModal();
        } catch (err) {
            alert('The assessment could not be submitted right now.');
        }
    }

    function renderWorkflowActions(mode, report = currentReportModalRecord) {
        const workflowCard = document.getElementById("workflow-actions-card");
        const workflowHelp = document.getElementById("workflow-actions-help");
        const workflowButtons = document.getElementById("workflow-actions-buttons");
        const workflowInput = document.getElementById("workflow-detail-input");
        const workflowFormFields = document.getElementById("workflow-form-fields");
        if (!workflowCard || !workflowButtons) {
            return;
        }

        const normalizedStatus = String(report?.status || "").trim();
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
        if (mode === "agriculturist") {
            // Agriculturist uses the report-expert-card for assessment submission in pending view.
            // Do not create a workflow action for initial assessment here to avoid duplicating UI.
            if (normalizedStatus === "visit_requested") {
                actions.push({
                    label: "Accept Request",
                    icon: "fa-solid fa-calendar-check",
                    action: "accept-visit-request",
                    help: "Accept the visit request and confirm the visit schedule.",
                });
                actions.push({
                    label: "Reject Request",
                    icon: "fa-solid fa-ban",
                    action: "reject-visit-request",
                    help: "Reject the visit request and explain why.",
                });
                if (workflowFormFields) {
                    workflowFormFields.innerHTML = `
                        <div style="display:grid; gap:10px;">
                            <label style="font-size:0.9rem; font-weight:600; color:#334155;">Decision</label>
                            <select id="visit-review-decision" class="notes-input-box" style="min-height:auto; padding:12px 14px;">
                                <option value="accept">Accept request</option>
                                <option value="reject">Reject request</option>
                            </select>
                            <div style="display:grid; gap:8px;">
                                <label style="font-size:0.9rem; font-weight:600; color:#334155;">Preferred date</label>
                                <input id="visit-review-date" type="date" class="notes-input-box" style="min-height:auto; padding:12px 14px;">
                                <label style="font-size:0.9rem; font-weight:600; color:#334155;">Preferred time</label>
                                <input id="visit-review-time" type="time" class="notes-input-box" style="min-height:auto; padding:12px 14px;">
                            </div>
                        </div>`;
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
                            <input id="workflow-visit-images" type="file" accept="image/*" multiple class="notes-input-box" style="min-height:auto; padding:12px 14px;">
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
                    help: "Let the agriculturist know whether the assessment resolved your issue.",
                });
                if (workflowFormFields) {
                    workflowFormFields.innerHTML = `
                        <div style="display:grid; gap:10px;">
                            <label style="font-size:0.9rem; font-weight:600; color:#334155;">Did the assessment resolve your issue?</label>
                            <select id="farmer-feedback-choice" class="notes-input-box" style="min-height:auto; padding:12px 14px;">
                                <option value="resolved">Yes, my issue has been resolved.</option>
                                <option value="needs-assistance">No, I still need assistance.</option>
                            </select>
                            <div id="farmer-visit-fields" style="display:grid; gap:8px;">
                                <label style="font-size:0.9rem; font-weight:600; color:#334155;">Reason for requesting a visit</label>
                                <textarea id="farmer-visit-reason" class="notes-input-box" placeholder="Describe why you still need assistance..." style="min-height:90px;"></textarea>
                                <label style="font-size:0.9rem; font-weight:600; color:#334155;">Preferred date</label>
                                <input id="farmer-visit-date" type="date" class="notes-input-box" style="min-height:auto; padding:12px 14px;">
                                <label style="font-size:0.9rem; font-weight:600; color:#334155;">Preferred time</label>
                                <input id="farmer-visit-time" type="time" class="notes-input-box" style="min-height:auto; padding:12px 14px;">
                            </div>
                        </div>`;
                }
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
        currentWorkflowDefaultSubmitAction = actions[0]?.action || null;
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
                renderWorkflowActions(currentReportModalMode, report);
                alert(data.message || "Assessment notes saved.");
            } catch (error) {
                alert("The assessment could not be saved right now.");
            }
            return;
        }

        if (actionName === "farmer-feedback") {
            const feedbackChoice = document.getElementById("farmer-feedback-choice")?.value || "resolved";
            formData.append("confirmation", feedbackChoice === "resolved" ? "resolved" : "needs-assistance");
            if (feedbackChoice !== "resolved") {
                const reason = document.getElementById("farmer-visit-reason")?.value?.trim() || "";
                const dates = [
                    document.getElementById("farmer-visit-date-1")?.value || "",
                    document.getElementById("farmer-visit-date-2")?.value || "",
                    document.getElementById("farmer-visit-date-3")?.value || "",
                ];
                const times = [
                    document.getElementById("farmer-visit-time-1")?.value || "",
                    document.getElementById("farmer-visit-time-2")?.value || "",
                    document.getElementById("farmer-visit-time-3")?.value || "",
                ];
                if (!reason || dates.some(d => !d) || times.some(t => !t)) {
                    alert("Please provide a reason and propose three preferred date/time options before submitting.");
                    return;
                }
                formData.append("reason", reason);
                // append the three preferred date/time pairs
                dates.forEach((d, idx) => {
                    formData.append(`preferred_date_${idx+1}`, d);
                    formData.append(`preferred_time_${idx+1}`, times[idx] || "");
                });
            }
            try {
                const response = await fetch("/farmer/submit-assessment-feedback", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The feedback could not be saved.");
                    return;
                }
                report.status = feedbackChoice === "resolved" ? "waiting_agriculturist_confirmation" : "visit_requested";
                applyStatusStyle(report);
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
                const preferredDate = document.getElementById("visit-review-date")?.value || "";
                const preferredTime = document.getElementById("visit-review-time")?.value || "";
                if (!preferredDate || !preferredTime) {
                    alert("Please confirm the visit date and time before accepting the request.");
                    return;
                }
                formData.append("preferred_date", preferredDate);
                formData.append("preferred_time", preferredTime);
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

    window.submitExpertValidation = function () {
        // Prefer direct expert assessment submit if input exists
        if (document.getElementById("expert-notes-input")) {
            return submitExpertAssessment();
        }
        return submitWorkflowAction(currentWorkflowDefaultSubmitAction || "submit-assessment");
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