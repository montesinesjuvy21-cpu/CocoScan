from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Mapping


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value

    value_str = str(value).strip()
    if not value_str:
        return None

    try:
        return datetime.fromisoformat(value_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_dashboard_chart_payload(reports: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Build chart-friendly trend and distribution data from real reports."""
    if not reports:
        return {
            "trend_labels": ["No data"],
            "trend_datasets": [
                {
                    "label": "No reports yet",
                    "data": [0],
                    "borderColor": "#94a3b8",
                    "backgroundColor": "rgba(148, 163, 184, 0.15)",
                    "borderWidth": 2,
                    "tension": 0.2,
                    "pointRadius": 3,
                    "fill": True,
                }
            ],
            "distribution_labels": ["No reports yet"],
            "distribution_data": [0],
        }

    monthly_counts: dict[str, Counter[str]] = defaultdict(Counter)
    pest_counter: Counter[str] = Counter()

    for report in reports:
        created_at = report.get("created_at") or report.get("submitted_at") or report.get("photo_taken_at")
        dt = _parse_datetime(created_at)
        if not dt:
            continue

        month_key = dt.strftime("%b")
        pest_name = str(report.get("pest_type") or "Unknown Pest").strip() or "Unknown Pest"
        monthly_counts[month_key][pest_name] += 1
        pest_counter[pest_name] += 1

    if not monthly_counts:
        return {
            "trend_labels": ["No data"],
            "trend_datasets": [
                {
                    "label": "No reports yet",
                    "data": [0],
                    "borderColor": "#94a3b8",
                    "backgroundColor": "rgba(148, 163, 184, 0.15)",
                    "borderWidth": 2,
                    "tension": 0.2,
                    "pointRadius": 3,
                    "fill": True,
                }
            ],
            "distribution_labels": ["No reports yet"],
            "distribution_data": [0],
        }

    month_labels = sorted(monthly_counts.keys(), key=lambda item: datetime.strptime(item, "%b").month)
    top_pests = [pest for pest, _ in pest_counter.most_common(3)] or ["Unknown Pest"]

    trend_datasets = []
    for pest_name in top_pests:
        trend_datasets.append(
            {
                "label": pest_name,
                "data": [monthly_counts[month].get(pest_name, 0) for month in month_labels],
                "borderColor": "#164630" if pest_name == top_pests[0] else "#d97706",
                "backgroundColor": "rgba(22, 70, 48, 0.15)" if pest_name == top_pests[0] else "rgba(217, 119, 6, 0.15)",
                "borderWidth": 2,
                "tension": 0.2,
                "pointRadius": 3,
                "fill": True,
            }
        )

    distribution_labels = [pest for pest, _ in pest_counter.most_common(5)]
    distribution_data = [pest_counter[pest] for pest in distribution_labels]

    if not distribution_labels:
        distribution_labels = ["No reports yet"]
        distribution_data = [0]

    return {
        "trend_labels": month_labels,
        "trend_datasets": trend_datasets,
        "distribution_labels": distribution_labels,
        "distribution_data": distribution_data,
    }
