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
        const notes = reportData.notes || reportData.farmer_notes || reportData.field_notes || "";
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
            availabilitySlots: normalizeAvailabilitySlots(reportData.availability_slots || reportData.availability || reportData.availabilitySlots || reportData.farmer_availability || feedbackData.schedules?.map((item) => item.date ? `${item.date} ${item.time || "Morning"}`.trim() : "") || []),
            agriBookedSchedules: normalizeAvailabilitySlots(reportData.agri_booked_schedules || reportData.agri_booked_slots || reportData.booked_schedules || []),
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

            const availabilityMatch = raw.match(/Availability:\s*\[(.*?)\]/i);
            if (availabilityMatch) {
                const availabilitySlots = availabilityMatch[1]
                    .split(",")
                    .map((slot) => String(slot || "").trim())
                    .filter(Boolean);
                feedback.schedules = availabilitySlots.map((slot) => ({ date: slot, time: "", display: slot }));
            }

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

    const TIME_WINDOW_DEFINITIONS = {
        morning: { label: "Morning", shortLabel: "Morning", range: "8:00 AM - 12:00 PM" },
        afternoon: { label: "Afternoon", shortLabel: "Afternoon", range: "1:00 PM - 5:00 PM" },
    };

    function normalizeAvailabilitySlots(value) {
        if (Array.isArray(value)) {
            return value
                .map((item) => {
                    if (typeof item === "string") return item.trim();
                    if (item && typeof item === "object") {
                        const date = item.date || item.day || "";
                        const windowName = item.window || item.timeWindow || item.time || item.windowKey || "";
                        if (date) {
                            return windowName ? `${date} ${String(windowName)}`.trim() : date;
                        }
                    }
                    return "";
                })
                .filter(Boolean);
        }

        if (typeof value === "string") {
            const trimmed = value.trim();
            if (!trimmed) return [];
            if (trimmed.startsWith("[")) {
                try {
                    const parsed = JSON.parse(trimmed);
                    return normalizeAvailabilitySlots(parsed);
                } catch (e) {
                    return [];
                }
            }
            return trimmed
                .split(/,|\n|;/)
                .map((slot) => slot.trim())
                .filter(Boolean);
        }

        return [];
    }

    function parseAvailabilitySlot(slot) {
        const cleaned = String(slot || "").trim();
        if (!cleaned) return null;
        const match = cleaned.match(/^(\d{4}-\d{2}-\d{2})\s+(.+)$/i);
        if (!match) return { date: cleaned, windowKey: "morning" };
        const [, date, windowValue] = match;
        const lowerValue = String(windowValue).trim().toLowerCase();
        if (lowerValue.includes("afternoon")) return { date, windowKey: "afternoon", windowLabel: "Afternoon" };
        if (lowerValue.includes("morning")) return { date, windowKey: "morning", windowLabel: "Morning" };
        return { date, windowKey: "morning", windowLabel: windowValue };
    }

    function buildAvailabilitySlot(dateValue, windowKey) {
        const normalizedWindow = TIME_WINDOW_DEFINITIONS[windowKey] ? windowKey : "morning";
        return `${dateValue} ${TIME_WINDOW_DEFINITIONS[normalizedWindow].label}`;
    }

    function formatAvailabilitySlotLabel(slot) {
        const parsed = parseAvailabilitySlot(slot);
        if (!parsed) return String(slot || "");
        try {
            const formatter = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
            const dateValue = new Date(`${parsed.date}T12:00:00`);
            return `${formatter.format(dateValue)} - ${parsed.windowLabel || TIME_WINDOW_DEFINITIONS[parsed.windowKey]?.label || "Morning"}`;
        } catch (e) {
            return String(slot || "");
        }
    }

    function getNextAvailabilityDates(count = 5) {
        const dates = [];
        const base = new Date();
        for (let index = 0; index < count; index += 1) {
            const current = new Date(base);
            current.setDate(base.getDate() + index);
            const year = current.getFullYear();
            const month = String(current.getMonth() + 1).padStart(2, "0");
            const day = String(current.getDate()).padStart(2, "0");
            dates.push(`${year}-${month}-${day}`);
        }
        return dates;
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
            "awaiting_confirmed_schedule": "Awaiting Confirmed Schedule",
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
            "awaiting_confirmed_schedule": { backgroundColor: "#eff6ff", color: "#1d4ed8" },
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
        const scanSubmitButton = document.getElementById("report-scan-submit-btn");
        const agriSubmitButton = document.getElementById("report-agri-submit-btn");
        const cancelButton = document.getElementById("report-modal-cancel-btn");
        const actionButtons = [scanSubmitButton, agriSubmitButton].filter(Boolean);

        actionButtons.forEach((button) => {
            if (!button) return;
            const shouldDisable = isSubmitting;
            button.disabled = shouldDisable;
            button.classList.toggle("is-disabled", shouldDisable);
            button.setAttribute("aria-busy", isSubmitting ? "true" : "false");

                if (isSubmitting) {
                if (!button.dataset.defaultHtml) {
                    button.dataset.defaultHtml = button.innerHTML;
                }
                const icon = "fa-solid fa-spinner fa-spin";
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

    function renderList(node, items, emptyText, showIcon = true) {
        if (!node) return;
        node.innerHTML = "";

        if (!items || items.length === 0) {
            const li = document.createElement("li");
            if (emptyText === "No expert recommendation available yet.") {
                li.style.listStyle = "none";
                li.style.margin = "0";
                li.style.padding = "0";
                li.innerHTML = `
                <div style="background-color: #fffbeb; color: #92400e; padding: 12px 16px; border-radius: 8px; font-size: 0.92rem; margin-top: 4px; display: flex; align-items: center; gap: 10px; border: 1px solid #fcd34d;">
                    <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.2rem; color:#d97706;"></i> 
                    <span style="font-weight: 500;">${escapeHtml(emptyText)}</span>
                </div>`;
            } else if (showIcon) {
                li.innerHTML = `<i class="fa-solid fa-circle-info" style="color: #d97706;"></i> <span>${escapeHtml(emptyText)}</span>`;
            } else {
                li.textContent = emptyText;
            }
            node.appendChild(li);
            return;
        }

        items.forEach((item) => {
            const li = document.createElement("li");
            if (showIcon) {
                li.innerHTML = `<i class="fa-solid fa-circle-check"></i> <span>${escapeHtml(item)}</span>`;
            } else {
                li.textContent = String(item ?? "");
            }
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
        const assessmentAlreadyIssued = ["assessment_issued", "recommendation_issued", "waiting_for_agriculturist_confirmation", "waiting_agriculturist_confirmation", "awaiting_confirmed_schedule", "visit_requested", "visit_scheduled", "visit_completed", "final_remarks_issued", "resolved", "closed"].includes(statusKey) || (Array.isArray(report.expertRecommendations) && report.expertRecommendations.length > 0);

        setDisplay(scanButton, mode === "scan", "flex");
        // Hide follow-up/farmer button (removed from UI)
        // Show agriculturist submit only when in agriculturist mode and no recommendation/assessment has been issued
        setDisplay(agriButton, mode === "agriculturist" && !assessmentAlreadyIssued, "flex");
        setDisplay(cancelButton, true, "inline-flex");

        scanOnlyNodes.forEach((node) => setDisplay(node, mode === "scan", "block"));
        readonlyOnlyNodes.forEach((node) => setDisplay(node, mode !== "scan", "block"));

        // The follow-up control has been removed from the modal UI. Follow-up flows are handled
        // via the feedback/workflow cards rendered by `renderWorkflowActions` when appropriate.

        // Agriculturist submit button state: disable when assessment already issued or report reviewed
        if (agriButton) {
            const disableAgri = assessmentAlreadyIssued;
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
            const allowExpertInput = mode === "agriculturist" && !assessmentAlreadyIssued;
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
            renderList(document.getElementById("report-expert-list"), report.expertRecommendations, "No expert recommendation available yet.", false);
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

    function formatVisitChatTimestamp(value) {
        if (!value) return "";
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return String(value);
        return new Intl.DateTimeFormat("en-US", {
            timeZone: "Asia/Manila",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: true,
        }).format(parsed);
    }

    async function loadVisitDiscussion(report) {
        if (!report?.id) return;
        try {
            const response = await fetch(`/reports/${report.id}/visit-discussion`);
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) {
                return;
            }
            report.visitChats = Array.isArray(data.messages) ? data.messages : [];
            report.schedule = data.schedule || null;
            report.visitScheduleStamp = data.schedule_stamp || "";
            report.visitArchived = Boolean(data.is_archived);
            report.visitImages = Array.isArray(data.visit_images) ? data.visit_images : [];
            report.visit_summary = data.report?.visit_summary || "";
            report.visitRescheduleReason = data.visit_reschedule_reason || "";
            report.visitRescheduledAt = data.visit_rescheduled_at || "";
            report.visitRescheduledBy = data.visit_rescheduled_by || "";
            report.visitScheduleTitle = data.schedule_title || (report.visitRescheduleReason ? "Reschedule Requested" : "Visit Scheduled");
            report.status = data.status || report.status;
            if (report.status && typeof report.status === "string") {
                report.status = report.status;
            }
        } catch (error) {
            console.warn("Unable to load visit discussion", error);
        }
    }

    function renderVisitDiscussionCard(mode, report) {
        const workflowCard = document.getElementById("workflow-actions-card");
        const workflowInput = document.getElementById("workflow-detail-input");
        const feedbackContainer = document.getElementById("report-farmer-feedback");
        const feedbackCard = document.getElementById("report-farmer-feedback-card");
        if (!feedbackContainer || !feedbackCard) {
            return;
        }

        const isArchived = Boolean(report?.visitArchived);
        const isAgriculturist = mode === "agriculturist";
        const chats = Array.isArray(report?.visitChats) ? report.visitChats : [];
        const statusLabel = getWorkflowStatusDisplayLabel(report?.status || "");
        const scheduleTitle = report?.visitScheduleTitle || (report?.visitRescheduleReason ? "Reschedule Requested" : "Visit Scheduled");
        const statusText = isArchived ? scheduleTitle : statusLabel;
        const messagePlaceholder = isAgriculturist ? "Type a message..." : "Type a message to reply...";
        const messageCount = chats.length;
        const messageLabel = `${messageCount} ${messageCount === 1 ? "message" : "messages"}`;
        const isExpanded = Boolean(report?.visitDiscussionExpanded);

        const hasPendingReschedule = Boolean(report?.visitRescheduleReason);
        const bannerStyle = hasPendingReschedule 
            ? "background:#fffbeb; color:#b45309;" // Yellow/Orange
            : "background:#ecfdf5; color:#065f46;"; // Green

        feedbackContainer.innerHTML = `
            <div style="display:grid; gap:16px; padding:16px 0;">

               <button id="visit-discussion-toggle" type="button"
                aria-expanded="${isExpanded ? "true" : "false"}"
                style="
                    display:flex;
                    align-items:center;
                    justify-content:space-between;
                    width:100%;
                    padding:10px 14px;
                    border:1px solid #bfdbfe;
                    border-radius:999px;
                    background:#eff6ff;
                    color:#1d4ed8;
                    font-weight:700;
                    text-align:left;
                    cursor:pointer;
                    box-shadow:inset 0 1px 2px rgba(59,130,246,0.08);
                ">

                <!-- Left -->
                <span style="
                    display:flex;
                    align-items:center;
                    gap:10px;
                    min-width:0;
                    flex:1;
                    white-space:nowrap;
                    overflow:hidden;
                ">

                    <span style="
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                        width:24px;
                        height:24px;
                        border-radius:50%;
                        background:#dbeafe;
                        color:#2563eb;
                        border:1px solid #93c5fd;
                        font-size:0.85rem;
                        font-weight:700;
                        line-height:1;
                        flex-shrink:0;
                    ">
                        ${messageCount}
                    </span>


                    <!-- Title -->
                    <span style="
                        font-size:0.90rem;
                        font-weight:600;
                        white-space:nowrap;
                        overflow:hidden;
                        text-overflow:ellipsis;
                    ">
                        Visit Request Discussion
                    </span>

                </span>

                <!-- Chevron -->
                <span style="
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    width:30px;
                    height:30px;
                    border-radius:50%;
                    background:#dbeafe;
                    color:#2563eb;
                    flex-shrink:0;
                    transform:rotate(${isExpanded ? 90 : 0}deg);
                    transition:transform .2s ease;
                ">
                    <i class="fa-solid fa-chevron-right"></i>
                </span>

            </button>
                <div id="visit-discussion-body" style="display:${isExpanded ? "grid" : "none"}; gap:10px;">
                    <div id="visit-discussion-messages-container" style="display:grid; gap:8px; padding:10px; border:1px solid #e2e8f0; border-radius:16px; background:#fff; max-height:320px; overflow-y:auto;">
                        ${chats.length ? chats.map((chat) => {
                            const isAgriculturistMessage = String(chat.sender_label || "").toLowerCase() === "agriculturist";
                            return `
                                <div style="display:flex; justify-content:${isAgriculturistMessage ? "flex-end" : "flex-start"};">
                                    <div style="max-width:82%; display:grid; gap:4px;">
                                        <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.04em; padding:${isAgriculturistMessage ? "0 0 0 8px" : "0 8px 0 0"};">${escapeHtml(chat.sender_label || "Farmer")}</div>
                                        <div style="padding:10px 12px; border-radius:16px; background:${isAgriculturistMessage ? "#ecfdf5" : "#f8fafc"}; color:#0f172a; box-shadow:0 1px 2px rgba(15,23,42,0.06);">
                                            <div style="font-size:0.9rem; line-height:1.5;">${escapeHtml(chat.message || "")}</div>
                                            <div style="margin-top:6px; font-size:0.72rem; color:#64748b;">${escapeHtml(formatVisitChatTimestamp(chat.created_at) || "Just now")}</div>
                                        </div>
                                    </div>
                                </div>`;
                        }).join("") : '<div style="font-size:0.9rem; color:#64748b;">No discussion messages yet.</div>'}
                    </div>
                    ${isArchived ? "" : `
                        <div style="display:grid; gap:10px;">
                            <textarea id="visit-discussion-input" class="notes-input-box" placeholder="${escapeHtml(messagePlaceholder)}" style="min-height:84px;"></textarea>
                            <div style="display:flex; justify-content:flex-end; gap:8px; flex-wrap:wrap;">
                                <button type="button" id="visit-discussion-send-btn" class="btn-control submit-primary">Send</button>
                            </div>
                        </div>
                    `}
                </div>
                ${report?.visitScheduleStamp ? `<div style="padding:10px 12px; border-radius:14px; ${bannerStyle} font-size:0.92rem; font-weight:600;">${escapeHtml(scheduleTitle)}<br>${escapeHtml(report.visitScheduleStamp)}</div>` : ""}
                ${(hasPendingReschedule && !isArchived) ? `
                    <div style="background:#eff6ff; color:#1e3a8a; padding:12px 14px; border-radius:8px; border:1px solid #bfdbfe; font-size:0.9rem; display:flex; align-items:center; gap:10px; font-family: sans-serif;">
                        <strong>Tip:</strong> Click the "Visit Request Discussion" button to chat and finalize a new date and time.
                    </div>
                ` : ""}
                ${(hasPendingReschedule && isAgriculturist) ? `<button type="button" id="visit-discussion-finalize-btn" class="btn-control submit-primary" style="justify-self:start; margin-top:4px;">Finalize Schedule</button>` : ""}
                ${isArchived ? `<div style="font-size:0.9rem; color:#475569; line-height:1.5;">The scheduling discussion has been closed.</div>` : ""}
                ${isArchived ? `<button type="button" id="request-reschedule-btn" class="btn-control submit-primary" style="justify-self:start;">Request Reschedule</button>` : ""}
            </div>`;

        const toggleButton = feedbackContainer.querySelector('#visit-discussion-toggle');
        if (toggleButton) {
            toggleButton.addEventListener('click', () => {
                report.visitDiscussionExpanded = !Boolean(report.visitDiscussionExpanded);
                renderVisitDiscussionCard(mode, report);
            });
        }

        const finalizeBtn = feedbackContainer.querySelector('#visit-discussion-finalize-btn');
        if (finalizeBtn) {
            finalizeBtn.addEventListener('click', () => {
                openFinalizeVisitScheduleModal(report);
            });
        }

        const sendButton = feedbackContainer.querySelector('#visit-discussion-send-btn');
        if (sendButton) {
            sendButton.addEventListener('click', async () => {
                const messageInput = feedbackContainer.querySelector('#visit-discussion-input');
                const message = messageInput?.value?.trim() || "";
                if (!message) {
                    alert("Please type a message before sending.");
                    return;
                }
                
                // Disable button and input to prevent double sending
                sendButton.disabled = true;
                sendButton.textContent = "Sending...";
                messageInput.disabled = true;

                // Save scroll position of the modal wrapper to prevent jumping
                const modalRoot = getModalRoot();
                let scrollContainer = modalRoot;
                if (modalRoot) {
                    const descendants = modalRoot.querySelectorAll('*');
                    for (const el of descendants) {
                        const style = getComputedStyle(el);
                        if (el.scrollHeight > el.clientHeight && (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                            scrollContainer = el;
                            break;
                        }
                    }
                }
                const savedScrollTop = scrollContainer ? scrollContainer.scrollTop : 0;

                try {
                    const response = await fetch(`/reports/${report.id}/visit-chat`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ message }),
                    });
                    const data = await response.json().catch(() => ({}));
                    if (!response.ok || !data.success) {
                        alert(data.message || "The message could not be saved.");
                        sendButton.disabled = false;
                        sendButton.textContent = "Send";
                        messageInput.disabled = false;
                        return;
                    }
                    await loadVisitDiscussion(report);
                    renderWorkflowActions(currentReportModalMode, report);
                    
                    if (scrollContainer) {
                        requestAnimationFrame(() => {
                            scrollContainer.scrollTop = savedScrollTop;
                        });
                    }
                } catch (error) {
                    alert("The message could not be sent right now.");
                    sendButton.disabled = false;
                    sendButton.textContent = "Send";
                    messageInput.disabled = false;
                }
            });
        }
        
        const messageInput = feedbackContainer.querySelector('#visit-discussion-input');
        if (messageInput && sendButton) {
            messageInput.addEventListener('keydown', (e) => {
                if (e.ctrlKey && e.key === 'Enter') {
                    e.preventDefault();
                    if (!sendButton.disabled) {
                        sendButton.click();
                    }
                }
            });
        }

        const confirmButton = feedbackContainer.querySelector('#confirm-visit-schedule-btn');
        if (confirmButton) {
            confirmButton.addEventListener('click', () => openFinalizeVisitScheduleModal(report));
        }

        const requestRescheduleButton = feedbackContainer.querySelector('#request-reschedule-btn');
        if (requestRescheduleButton) {
            requestRescheduleButton.addEventListener('click', () => openRequestRescheduleModal(report));
        }

        const messagesContainer = feedbackContainer.querySelector('#visit-discussion-messages-container');
        if (messagesContainer && isExpanded) {
            setTimeout(() => {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }, 10);
        }

        if (workflowInput) {
            workflowInput.value = "";
            setDisplay(workflowInput, false);
        }
        if (workflowCard) {
            setDisplay(workflowCard, false, "block");
        }
        setDisplay(feedbackCard, true, "block");
    }

    function openRequestRescheduleModal(report) {
        const existingModal = document.getElementById("visit-reschedule-mini-modal");
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement("div");
        modal.id = "visit-reschedule-mini-modal";
        modal.style.position = "fixed";
        modal.style.inset = "0";
        modal.style.background = "rgba(15, 23, 42, 0.48)";
        modal.style.display = "flex";
        modal.style.alignItems = "center";
        modal.style.justifyContent = "center";
        modal.style.padding = "20px";
        modal.style.zIndex = "4000";
        modal.innerHTML = `
            <div style="width:min(100%, 430px); background:#fff; border-radius:20px; box-shadow:0 20px 50px rgba(15,23,42,0.22); padding:28px; display:grid; gap:20px;">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:14px;">
                    <div style="font-size:1.05rem; font-weight:700; color:#102a43;">Request Reschedule</div>
                    <button type="button" id="visit-reschedule-modal-close" class="btn-control cancel-secondary" style="width: auto; min-height: 34px; padding: 8px 12px; border-radius: 999px; background: #dc2626; color: #ffffff; border: 1px solid #dc2626; box-shadow: none;">Close</button>
                </div>
                <div style="display:grid; gap:14px;">
                    <label style="display:grid; gap:10px; font-size:0.98rem; color:#334155;">
                        <span style="font-weight:700;">Reason</span>
                        <select id="visit-reschedule-reason" class="schedule-input" style="padding:12px 14px; border-radius:12px; border:1px solid #e6e6e6; height:48px; line-height:20px; box-sizing:border-box; font-size:1rem;">
                            <option value="Emergency">Emergency</option>
                            <option value="Bad weather">Bad weather</option>
                            <option value="Personal conflict">Personal conflict</option>
                            <option value="Other">Other</option>
                        </select>
                    </label>
                    <div id="visit-reschedule-other-wrapper" style="display:none;">
                        <label style="display:grid; gap:10px; font-size:0.98rem; color:#334155;">
                            <span style="font-weight:700;">Reason Details</span>
                            <textarea id="visit-reschedule-other-details" class="notes-input-box" placeholder="Add more details..." style="min-height:140px; padding:18px;"></textarea>
                        </label>
                    </div>
                </div>
                <button type="button" id="visit-reschedule-save-btn" class="btn-control submit-primary" style="width:100%; padding:16px 20px; border-radius:14px;">Submit Request</button>
            </div>`;
        document.body.appendChild(modal);

        const reasonSelect = modal.querySelector('#visit-reschedule-reason');
        const otherWrapper = modal.querySelector('#visit-reschedule-other-wrapper');
        const toggleOtherInput = () => {
            if (otherWrapper) {
                otherWrapper.style.display = reasonSelect?.value === 'Other' ? 'block' : 'none';
            }
        };
        reasonSelect?.addEventListener('change', toggleOtherInput);
        toggleOtherInput();

        modal.querySelector('#visit-reschedule-modal-close')?.addEventListener('click', () => modal.remove());
        modal.querySelector('#visit-reschedule-save-btn')?.addEventListener('click', async () => {
            const reason = reasonSelect?.value || "";
            const details = modal.querySelector('#visit-reschedule-other-details')?.value?.trim() || "";
            if (reason === 'Other' && !details) {
                alert("Please provide reason details for 'Other'.");
                return;
            }
            const finalReason = reason === 'Other' ? `${reason}: ${details}` : reason;
            if (!finalReason) {
                alert("Please select a reason before submitting the reschedule request.");
                return;
            }
            try {
                const response = await fetch(`/reports/${report.id}/request-reschedule`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ reason: finalReason }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The reschedule request could not be submitted.");
                    return;
                }
                report.visitArchived = false;
                report.visitDiscussionExpanded = true;
                report.visitScheduleTitle = "Visit Scheduled";
                await loadVisitDiscussion(report);
                renderWorkflowActions(currentReportModalMode, report);
                modal.remove();
                alert(data.message || "Reschedule request submitted.");
            } catch (error) {
                alert("The reschedule request could not be submitted right now.");
            }
        });
    }

    function openFinalizeVisitScheduleModal(report) {
        const existingModal = document.getElementById("visit-schedule-mini-modal");
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement("div");
        modal.id = "visit-schedule-mini-modal";
        modal.style.position = "fixed";
        modal.style.inset = "0";
        modal.style.background = "rgba(15, 23, 42, 0.48)";
        modal.style.display = "flex";
        modal.style.alignItems = "center";
        modal.style.justifyContent = "center";
        modal.style.padding = "20px";
        modal.style.zIndex = "4000";
        modal.innerHTML = `
            <div style="width:min(100%, 430px); background:#fff; border-radius:18px; box-shadow:0 20px 50px rgba(15,23,42,0.22); padding:28px; display:grid; gap:20px;">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:14px;">
                    <div style="font-size:1.05rem; font-weight:700; color:#102a43;">Finalize Visit Schedule</div>
                    <button type="button" id="visit-schedule-modal-close" class="btn-control cancel-secondary" style="width: auto; min-height: 34px; padding: 8px 12px; border-radius: 999px; background: #dc2626; color: #ffffff; border: 1px solid #dc2626; box-shadow: none;">Close</button>
                </div>
                <div style="display:grid; gap:14px;">
                    <label style="display:grid; gap:8px; font-size:0.96rem; color:#334155;">
                        <span style="font-weight:700;">Select the agreed date</span>
                        <input id="visit-confirmed-date" type="date" class="schedule-input" style="padding:12px 14px; border-radius:12px; border:1px solid #e6e6e6; min-height:48px;">
                    </label>
                    <label style="display:grid; gap:8px; font-size:0.96rem; color:#334155;">
                        <span style="font-weight:700;">Start Time</span>
                        <select id="visit-start-time" class="schedule-input" style="padding:12px 14px; border-radius:12px; border:1px solid #e6e6e6; min-height:48px; background-color:#fff;">
                            <option value="" disabled selected>Select start time</option>
                            <option value="08:00">8:00 AM</option><option value="08:30">8:30 AM</option>
                            <option value="09:00">9:00 AM</option><option value="09:30">9:30 AM</option>
                            <option value="10:00">10:00 AM</option><option value="10:30">10:30 AM</option>
                            <option value="11:00">11:00 AM</option><option value="11:30">11:30 AM</option>
                            <option value="12:00">12:00 PM</option><option value="12:30">12:30 PM</option>
                            <option value="13:00">1:00 PM</option><option value="13:30">1:30 PM</option>
                            <option value="14:00">2:00 PM</option><option value="14:30">2:30 PM</option>
                            <option value="15:00">3:00 PM</option><option value="15:30">3:30 PM</option>
                            <option value="16:00">4:00 PM</option><option value="16:30">4:30 PM</option>
                            <option value="17:00">5:00 PM</option>
                        </select>
                    </label>
                    <label style="display:grid; gap:8px; font-size:0.96rem; color:#334155;">
                        <span style="font-weight:700;">End Time</span>
                        <select id="visit-end-time" class="schedule-input" style="padding:12px 14px; border-radius:12px; border:1px solid #e6e6e6; min-height:48px; background-color:#fff;">
                            <option value="" disabled selected>Select end time</option>
                            <option value="08:00">8:00 AM</option><option value="08:30">8:30 AM</option>
                            <option value="09:00">9:00 AM</option><option value="09:30">9:30 AM</option>
                            <option value="10:00">10:00 AM</option><option value="10:30">10:30 AM</option>
                            <option value="11:00">11:00 AM</option><option value="11:30">11:30 AM</option>
                            <option value="12:00">12:00 PM</option><option value="12:30">12:30 PM</option>
                            <option value="13:00">1:00 PM</option><option value="13:30">1:30 PM</option>
                            <option value="14:00">2:00 PM</option><option value="14:30">2:30 PM</option>
                            <option value="15:00">3:00 PM</option><option value="15:30">3:30 PM</option>
                            <option value="16:00">4:00 PM</option><option value="16:30">4:30 PM</option>
                            <option value="17:00">5:00 PM</option>
                        </select>
                    </label>
                </div>
                <button type="button" id="visit-schedule-save-btn" class="btn-control submit-primary" style="width:100%; padding:16px 20px; border-radius:14px;">Save Schedule</button>
            </div>`;
        document.body.appendChild(modal);

        modal.querySelector('#visit-schedule-modal-close')?.addEventListener('click', () => modal.remove());
        modal.querySelector('#visit-schedule-save-btn')?.addEventListener('click', async () => {
            const confirmedDate = modal.querySelector('#visit-confirmed-date')?.value || "";
            const startTime = modal.querySelector('#visit-start-time')?.value || "";
            const endTime = modal.querySelector('#visit-end-time')?.value || "";
            if (!confirmedDate || !startTime || !endTime) {
                alert("Please enter the confirmed date and visit window.");
                return;
            }
            try {
                const response = await fetch("/agriculturist/finalize-visit-schedule", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ request_id: report?.id, confirmed_date: confirmedDate, start_time: startTime, end_time: endTime, status: "Visit Scheduled" }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The schedule could not be finalized.");
                    return;
                }
                report.status = "Visit Scheduled";
                report.visitArchived = true;
                report.visitDiscussionExpanded = false;
                report.visitScheduleTitle = data.schedule_title || "Visit Scheduled";
                report.visitScheduleStamp = data.schedule_stamp || "";
                await loadVisitDiscussion(report);
                applyStatusStyle(report);
                renderWorkflowActions(currentReportModalMode, report);
                if (typeof window.renderReportsGrid === "function") {
                    try { window.renderReportsGrid(); } catch (e) { console.debug(e); }
                }
                modal.remove();
                alert(data.message || "The visit schedule has been finalized.");
            } catch (error) {
                alert("The schedule could not be finalized right now.");
            }
        });
    }

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

        workflowButtons.innerHTML = "";
        currentWorkflowDefaultSubmitAction = null;
        if (workflowFormFields) {
            workflowFormFields.innerHTML = "";
        }
        const existingWarning = document.getElementById("visit-scheduled-warning-banner");
        if (existingWarning) existingWarning.remove();
        const existingNotesLabel = document.getElementById("visit-scheduled-notes-label");
        if (existingNotesLabel) existingNotesLabel.remove();
        if (workflowInput) {
            workflowInput.value = "";
            workflowInput.disabled = false;
            workflowInput.style.display = "block";
            workflowInput.placeholder = "Add notes, a reason, availability, or the selected schedule...";
        }
        const workflowHeader = workflowCard.querySelector('h4');
        if (workflowHeader) {
            workflowHeader.innerHTML = '<i class="fa-solid fa-route"></i> Workflow Actions';
        }

        const actions = [];
        const discussionStatuses = ["awaiting_confirmed_schedule", "visit_requested", "visit_scheduled"];
        const normalizedStatus = getStatusKey(report?.status || "");
        const recommendationIssued = isRecommendationIssuedStatus(report?.status || "");
        const isVisitDiscussionState = discussionStatuses.includes(normalizedStatus);

        if (mode === "farmer") {
            setDisplay(workflowCard, false);
        }
        if (feedbackContainer) {
            feedbackContainer.innerHTML = "";
            const feedbackCard = document.getElementById('report-farmer-feedback-card');
            if (feedbackCard) setDisplay(feedbackCard, false, 'block');
        }

        if (isVisitDiscussionState) {
            renderVisitDiscussionCard(mode, report);
            // Allow the agriculturist to see the workflow actions to complete the scheduled visit
            if (mode === "farmer" || normalizedStatus !== "visit_scheduled") {
                return;
            }
        }

        if (mode === "agriculturist") {
            // Agriculturist uses the report-expert-card for assessment submission in pending view.
            // Do not create a workflow action for initial assessment here to avoid duplicating UI.
            if (normalizedStatus === "visit_requested") {
                if (workflowFormFields) {
                    workflowFormFields.innerHTML = `
                    <div style="display:grid; gap:10px;">
                        <label style="font-size:0.9rem; font-weight:600; color:#334155;">Decision</label>
                        <select id="visit-review-decision" style="min-height:auto; padding:10px 12px; width:100%; box-sizing:border-box;">
                            <option value="accept">Accept request</option>
                            <option value="reject">Reject request</option>
                        </select>
                    </div>`;
                }
                if (feedbackContainer) {
                    const availabilityOptions = normalizeAvailabilitySlots(report.availabilitySlots || report.farmerSchedules || []);
                    const bookedSchedules = normalizeAvailabilitySlots(report.agriBookedSchedules || []);
                    const optionMarkup = availabilityOptions.length
                        ? availabilityOptions.map((slot) => {
                            const parsed = parseAvailabilitySlot(slot);
                            const conflict = bookedSchedules.some((candidate) => {
                                const parsedCandidate = parseAvailabilitySlot(candidate);
                                return parsedCandidate?.date === parsed?.date && parsedCandidate?.windowKey === parsed?.windowKey;
                            });
                            const statusText = conflict ? '⚠️ You have a conflict' : '🟢 Both of you are free!';
                            return `
                                <label style="display:grid; gap:6px; padding:10px 12px; border:1px solid ${conflict ? '#f59e0b' : '#cbd5e1'}; border-radius:12px; background:#fff;">
                                    <div style="display:flex; align-items:center; gap:8px;">
                                        <input type="radio" name="agri-availability-choice" value="${escapeHtml(slot)}" ${conflict ? '' : 'checked'}>
                                        <span style="font-weight:600; color:#0f172a;">${escapeHtml(formatAvailabilitySlotLabel(slot))}</span>
                                    </div>
                                    <div style="font-size:0.82rem; color:${conflict ? '#b45309' : '#065f46'}; padding-left:24px;">${escapeHtml(statusText)}</div>
                                </label>`;
                        }).join("")
                        : `<p style="margin:0; font-size:0.95rem; color:#64748b;">No availability was submitted yet.</p>`;

                    feedbackContainer.innerHTML = `
                        <div style="display:grid; gap:14px; padding:4px 0;">
                            <div style="border:1px solid #e2e8f0; border-radius:14px; padding:14px; background:#f8fafc; display:grid; gap:10px;">
                                <div style="font-size:0.95rem; font-weight:700; color:#102a43;">Follow-up</div>
                                <div style="font-size:0.9rem; color:#334155;">Farmer's Available Schedules</div>
                                <div style="display:grid; gap:10px;">${optionMarkup}</div>
                            </div>
                            <div style="display:grid; gap:10px;">
                                <label style="font-size:0.9rem; font-weight:600; color:#334155;">Does any of these schedules work?</label>
                                <select id="agri-schedule-decision" style="min-height:auto; padding:10px 12px; width:100%; box-sizing:border-box;">
                                    <option value="yes">Yes</option>
                                    <option value="no">No</option>
                                </select>
                                <div id="agri-proposed-schedule" style="display:none; display:grid; gap:10px;">
                                    <label style="display:grid; gap:6px; font-size:0.9rem; color:#334155;">
                                        <span style="font-weight:600;">Proposed date</span>
                                        <input id="agri-proposed-date" type="date" class="schedule-input">
                                    </label>
                                    <label style="display:grid; gap:6px; font-size:0.9rem; color:#334155;">
                                        <span style="font-weight:600;">Time window</span>
                                        <select id="agri-proposed-window" class="schedule-input" style="height:44px;">
                                            <option value="morning">Morning (8:00 AM - 12:00 PM)</option>
                                            <option value="afternoon">Afternoon (1:00 PM - 5:00 PM)</option>
                                        </select>
                                    </label>
                                </div>
                                <div style="display:flex; flex-wrap:wrap; gap:8px;">
                                    <button type="button" id="agri-confirm-schedule-btn" class="btn-control submit-primary">Confirm Selected Schedule</button>
                                    <button type="button" id="agri-propose-schedule-btn" class="btn-control cancel-secondary">Propose Schedule</button>
                                </div>
                            </div>
                            <div style="font-size:0.9rem; color:#64748b;">Status: Awaiting for Farmer Conf.</div>
                        </div>`;
                    const decisionSelect = feedbackContainer.querySelector('#agri-schedule-decision');
                    const proposedScheduleBlock = feedbackContainer.querySelector('#agri-proposed-schedule');
                    const confirmButton = feedbackContainer.querySelector('#agri-confirm-schedule-btn');
                    const proposeButton = feedbackContainer.querySelector('#agri-propose-schedule-btn');
                    const refreshDecisionView = () => {
                        const isNo = decisionSelect?.value === 'no';
                        setDisplay(proposedScheduleBlock, isNo, 'grid');
                        if (confirmButton) confirmButton.style.display = isNo ? 'none' : 'inline-flex';
                        if (proposeButton) proposeButton.style.display = isNo ? 'inline-flex' : 'inline-flex';
                    };
                    decisionSelect?.addEventListener('change', refreshDecisionView);
                    confirmButton?.addEventListener('click', () => submitWorkflowAction('confirm-selected-schedule'));
                    proposeButton?.addEventListener('click', () => submitWorkflowAction('propose-selected-schedule'));
                    refreshDecisionView();
                    const feedbackCard = document.getElementById('report-farmer-feedback-card');
                    if (feedbackCard) setDisplay(feedbackCard, true, 'block');
                }
            } else if (normalizedStatus === "visit_scheduled") {
                if (workflowHeader) {
                    workflowHeader.innerHTML = '<i class="fa-solid fa-list-check"></i> Visit Summary';
                }
                let isVisitTimePassed = true;
                if (report.schedule && report.schedule.confirmed_date) {
                    const endTime = report.schedule.end_time || '23:59:59';
                    const scheduledEndTime = new Date(`${report.schedule.confirmed_date}T${endTime}`);
                    if (new Date() < scheduledEndTime) {
                        isVisitTimePassed = false;
                    }
                }
                const disabledReason = "You can only complete the visit after the scheduled time has passed.";
                
                actions.push({
                    label: "Complete Visit",
                    icon: "fa-solid fa-circle-check",
                    action: "complete-visit",
                    help: "Provide a summary and upload images to complete this record.",
                    disabled: !isVisitTimePassed,
                    disabledReason: disabledReason
                });
                if (workflowInput) {
                    workflowInput.placeholder = "Enter your visit summary notes here...";
                    workflowInput.disabled = !isVisitTimePassed;
                    workflowInput.style.backgroundColor = isVisitTimePassed ? "" : "#f1f5f9";
                    workflowInput.style.display = "block";
                    
                    let warningHtml = '';
                    if (!isVisitTimePassed) {
                        warningHtml = `
                        <div id="visit-scheduled-warning-banner" style="background-color: #fffbeb; color: #92400e; padding: 12px 16px; border-radius: 8px; font-size: 0.92rem; margin-bottom: 16px; display: flex; align-items: center; gap: 10px; border: 1px solid #fcd34d;">
                            <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.2rem;"></i> 
                            <span style="font-weight: 500;">You can only complete the visit after the scheduled time has passed.</span>
                        </div>`;
                    }
                    const labelHtml = `<label id="visit-scheduled-notes-label" style="font-size:0.9rem; font-weight:600; color:#334155; display:block; margin-bottom:8px;">Notes</label>`;
                    workflowInput.insertAdjacentHTML('beforebegin', warningHtml + labelHtml);
                }
                if (workflowFormFields) {
                    workflowFormFields.innerHTML = `
                        <div style="display:grid; gap:10px;">
                            <label style="font-size:0.9rem; font-weight:600; color:#334155;">Visit Images</label>
                            <div class="modern-micro-upload-zone" onclick="${isVisitTimePassed ? "this.querySelector('input').click()" : ""}" style="${isVisitTimePassed ? 'cursor:pointer;' : 'cursor:not-allowed; opacity:0.6;'}">
                                <i class="fa-solid fa-cloud-arrow-up"></i>
                                <span>Upload Visit Images</span>
                                <p>Tap to open your phone gallery directory</p>
                                <input id="workflow-visit-images" type="file" accept="image/*" multiple style="display:none;" ${!isVisitTimePassed ? 'disabled' : ''} onchange="
                                    const files = this.files;
                                    const txt = this.parentElement.querySelector('p');
                                    if (files.length) txt.textContent = files.length + ' file(s) selected';
                                    else txt.textContent = 'Tap to open your phone gallery directory';
                                ">
                            </div>
                        </div>`;
                }
            } else if (normalizedStatus === "resolved" && report.visit_summary) {
                if (workflowHeader) {
                    workflowHeader.innerHTML = '<i class="fa-solid fa-clipboard-check"></i> Visit Summary';
                }
                if (workflowInput) {
                    setDisplay(workflowInput, false);
                }
                if (workflowFormFields) {
                    const visitSummaryHtml = `
                        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:16px; margin-bottom:16px;">
                            <h5 style="margin:0 0 8px 0; font-size:0.95rem; color:#0f172a; font-weight:600;">Visit Summary</h5>
                            <p style="margin:0; font-size:0.9rem; color:#475569; line-height:1.5;">${escapeHTML(report.visit_summary)}</p>
                            ${(report.visitImages && report.visitImages.length > 0) ? `
                                <div style="display:flex; gap:8px; overflow-x:auto; margin-top:12px; padding-bottom:4px;">
                                    ${report.visitImages.map(url => `<img src="${url}" style="height:80px; width:120px; object-fit:cover; border-radius:8px; border:1px solid #cbd5e1; cursor:pointer;" onclick="window.open('${url}', '_blank')">`).join('')}
                                </div>
                            ` : ''}
                        </div>
                    `;
                    workflowFormFields.innerHTML = visitSummaryHtml;
                }
            }
        } else if (mode === "farmer") {
            // Show farmer feedback card when an assessment or recommendation has been issued.
            if (recommendationIssued) {
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
                        <div style="display:grid; gap:14px; padding:6px 0;">
                            <div style="display:grid; gap:8px;">
                                <p style="font-size:0.92rem; color:#334155; margin:0; line-height:1.55;">
                                    Did the initial recommendation and expert assessment resolve your issue?<br>
                                    <em style="font-size:0.72rem; color:#64748b;">If not, you can request an on-site visit and continue the workflow.</em>
                                </p>
                                <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:0;">
                                    <label style="display:flex; align-items:center; gap:8px; font-weight:600; color:#102a43;">
                                        <input type="radio" name="farmer-feedback-choice" value="resolved" checked style="accent-color:#059669;"> Yes
                                    </label>
                                    <label style="display:flex; align-items:center; gap:8px; font-weight:600; color:#102a43;">
                                        <input type="radio" name="farmer-feedback-choice" value="needs-assistance" style="accent-color:#be185d;"> No
                                    </label>
                                </div>
                            </div>
                            <div id="farmer-visit-reason-section" style="display:none; display:grid; gap:8px;">
                                <label style="font-size:0.9rem; font-weight:600; color:#334155;">Reason for requesting a visit</label>
                                <textarea id="farmer-visit-reason" class="notes-input-box" placeholder="Describe why you still need assistance..." style="min-height:110px; width:100%; box-sizing:border-box; padding:14px 16px;"></textarea>
                            </div>
                            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:4px;">
                                <button id="farmer-submit-feedback-btn" class="btn-control submit-primary" type="button">Submit</button>
                            </div>
                        </div>`;
                    const feedbackRadios = feedbackContainer.querySelectorAll("input[name='farmer-feedback-choice']");
                    const reasonSection = feedbackContainer.querySelector("#farmer-visit-reason-section");
                    const refreshReasonDisplay = () => {
                        const selectedValue = Array.from(feedbackRadios).find((input) => input.checked)?.value || "resolved";
                        if (reasonSection) {
                            setDisplay(reasonSection, selectedValue === 'needs-assistance', 'grid');
                        }
                    };
                    feedbackRadios.forEach((input) => input.addEventListener('change', refreshReasonDisplay));
                    refreshReasonDisplay();
                    const submitFeedbackBtn = feedbackContainer.querySelector('#farmer-submit-feedback-btn');
                    if (submitFeedbackBtn) {
                        submitFeedbackBtn.addEventListener('click', () => submitWorkflowAction('farmer-feedback'));
                    }
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
                        
                    let visitSummaryBlock = "";
                    if (normalizedStatus === "resolved" && report.visit_summary) {
                        visitSummaryBlock = `
                            <div style="background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:16px; margin-top:12px;">
                                <h5 style="margin:0 0 8px 0; font-size:0.95rem; color:#0f172a; font-weight:600;">Visit Summary</h5>
                                <p style="margin:0; font-size:0.9rem; color:#475569; line-height:1.5;">${escapeHTML(report.visit_summary)}</p>
                                ${(report.visitImages && report.visitImages.length > 0) ? `
                                    <div style="display:flex; gap:8px; overflow-x:auto; margin-top:12px; padding-bottom:4px;">
                                        ${report.visitImages.map(url => `<img src="${url}" style="height:80px; width:120px; object-fit:cover; border-radius:8px; border:1px solid #cbd5e1; cursor:pointer;" onclick="window.open('${url}', '_blank')">`).join('')}
                                    </div>
                                ` : ''}
                            </div>
                        `;
                    }
                    
                    const message = normalizedStatus === "visit_requested"
                        ? `<p style="font-size:0.92rem; color:#334155; margin:0;">Your visit request was submitted successfully. The agriculturist will review your preferred schedules.</p>${reasonDisplay}${scheduleDisplay}`
                        : (report.visit_summary 
                            ? `<p style="font-size:0.92rem; color:#334155; margin:0;">The agriculturist has completed the visit and marked the issue as resolved.</p>${visitSummaryBlock}` 
                            : `<p style="font-size:0.92rem; color:#334155; margin:0;">Thank you! You confirmed the assessment resolved your issue.</p>`);
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
            if (normalizedStatus === "resolved" && report.visit_summary) {
                setDisplay(workflowCard, true, "block");
            } else {
                setDisplay(workflowCard, false, "block");
            }
            return;
        }

        setDisplay(workflowCard, true, "block");
        currentWorkflowDefaultSubmitAction = actions[0]?.action || null;
        actions.forEach((action) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn-control submit-primary";
            button.innerHTML = `<i class="${action.icon}"></i> ${action.label}`;
            if (action.disabled) {
                button.disabled = true;
                button.style.backgroundColor = "#cbd5e1";
                button.style.color = "#475569";
                button.innerHTML = action.label;
                button.style.cursor = "not-allowed";
                button.title = action.disabledReason || "This action is currently disabled.";
            } else {
                button.onclick = () => submitWorkflowAction(action.action);
            }
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
                    <select class="farmer-schedule-time schedule-input" style="padding:12px 14px; border-radius:12px; border:1px solid #e6e6e6; min-height:48px; background-color:#fff;">
                        <option value="" disabled ${!timeVal ? "selected" : ""}>Select time</option>
                        ${['08:00', '08:30', '09:00', '09:30', '10:00', '10:30', '11:00', '11:30', '12:00', '12:30', '13:00', '13:30', '14:00', '14:30', '15:00', '15:30', '16:00', '16:30', '17:00'].map(val => {
                            let h = parseInt(val.substring(0, 2), 10);
                            let ampm = h < 12 ? 'AM' : 'PM';
                            let h12 = h <= 12 ? h : h - 12;
                            if (h12 === 0) h12 = 12;
                            let display = h12 + val.substring(2) + ' ' + ampm;
                            return `<option value="${val}" ${timeVal === val ? "selected" : ""}>${display}</option>`;
                        }).join('')}
                    </select>
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
            formData.append("confirmation", feedbackChoice);
            if (feedbackChoice === "resolved") {
                formData.append("reason", "");
                report.farmerFeedbackConfirmation = "resolved";
            } else {
                const reason = document.getElementById("farmer-visit-reason")?.value?.trim() || "";
                if (!reason) {
                    alert("Please provide a reason before submitting the visit request.");
                    return;
                }
                formData.append("reason", reason);
                report.farmerFeedbackReason = reason;
                report.farmerFeedbackConfirmation = "needs-assistance";
            }
            try {
                const response = await fetch("/farmer/submit-assessment-feedback", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The feedback could not be saved.");
                    return;
                }
                report.status = feedbackChoice === "resolved" ? "resolved" : "Awaiting Confirmed Schedule";
                if (feedbackChoice !== "resolved") {
                    report.visitArchived = false;
                    report.visitScheduleStamp = "";
                }
                applyStatusStyle(report);
                if (typeof window.renderReportsGrid === "function") {
                    try { window.renderReportsGrid(); } catch (e) { console.debug(e); }
                }
                if (feedbackChoice !== "resolved") {
                    await loadVisitDiscussion(report);
                }
                renderWorkflowActions(currentReportModalMode, report);
                alert(data.message || "Feedback saved.");
            } catch (error) {
                alert("The feedback could not be saved right now.");
            }
            return;
        }

        if (actionName === "confirm-selected-schedule") {
            const selectedSlot = document.querySelector("input[name='agri-availability-choice']:checked")?.value;
            const parsed = parseAvailabilitySlot(selectedSlot);
            formData.append("decision", "accept");
            if (parsed?.date) {
                formData.append("preferred_date", parsed.date);
                formData.append("preferred_time", parsed.windowLabel || TIME_WINDOW_DEFINITIONS[parsed.windowKey]?.label || "Morning");
            }
            try {
                const response = await fetch("/agriculturist/review-visit-request", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The selected schedule could not be saved.");
                    return;
                }
                report.status = "visit_scheduled";
                applyStatusStyle(report);
                renderWorkflowActions(currentReportModalMode, report);
                alert(data.message || "Visit scheduled successfully.");
            } catch (error) {
                alert("The selected schedule could not be saved right now.");
            }
            return;
        }

        if (actionName === "propose-selected-schedule") {
            const proposedDate = document.getElementById("agri-proposed-date")?.value || "";
            const proposedWindow = document.getElementById("agri-proposed-window")?.value || "morning";
            const preferredTime = TIME_WINDOW_DEFINITIONS[proposedWindow]?.label || "Morning";
            formData.append("decision", "accept");
            if (!proposedDate) {
                alert("Please select a proposed date before continuing.");
                return;
            }
            formData.append("preferred_date", proposedDate);
            formData.append("preferred_time", preferredTime);
            try {
                const response = await fetch("/agriculturist/review-visit-request", { method: "POST", body: formData });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    alert(data.message || "The proposed schedule could not be saved.");
                    return;
                }
                report.status = "visit_scheduled";
                applyStatusStyle(report);
                renderWorkflowActions(currentReportModalMode, report);
                alert(data.message || "Visit scheduled successfully.");
            } catch (error) {
                alert("The proposed schedule could not be saved right now.");
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
                report.status = "resolved";
                applyStatusStyle(report);
                await loadVisitDiscussion(report);
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
                formData.append("feedback", additionalNotes);
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
            renderList(document.getElementById("report-expert-list"), report.expertRecommendations, "No expert recommendation available yet.", false);
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

    async function openReportModal(reportData = {}, mode = "farmer") {
        const modalRoot = getModalRoot();
        if (!modalRoot) {
            return;
        }

        currentReportModalMode = mode || "farmer";
        currentReportModalRecord = normalizeReportData({ ...reportData, mode: currentReportModalMode });

        const report = currentReportModalRecord;
        // Debug: log status and expert recommendations to help trace visibility issues
        try { console.debug("[report_modal] opening report", { id: report.id, status: report.status, expertRecommendations: report.expertRecommendations }); } catch (e) { /* noop */ }
        await loadVisitDiscussion(report);

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
        renderList(document.getElementById("report-expert-list"), report.expertRecommendations, "No expert recommendation available yet.", false);

        applyStatusStyle(report);
        applyModeState(currentReportModalMode, report);
        renderWorkflowActions(currentReportModalMode, report);

        // Expert card visibility and input controls depend on existing assessment state
        const statusKey = getStatusKey(report?.status || "");
        const assessmentAlreadyIssued = ["assessment_issued", "recommendation_issued", "waiting_for_agriculturist_confirmation", "waiting_agriculturist_confirmation", "awaiting_confirmed_schedule", "visit_requested", "visit_scheduled", "visit_completed", "final_remarks_issued", "resolved", "closed"].includes(statusKey) || (Array.isArray(report.expertRecommendations) && report.expertRecommendations.length > 0);
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