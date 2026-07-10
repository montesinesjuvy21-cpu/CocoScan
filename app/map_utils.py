def _normalize_text(value) -> str:
    return str(value or "").strip().lower()


def filter_map_reports(reports, search_query="", pest_filter="all"):
    """Filter map reports by location text and optional pest type."""
    search_phrase = _normalize_text(search_query)
    pest_filter_value = _normalize_text(pest_filter or "all")

    filtered_reports = []
    for report in reports:
        location_text = " ".join(
            [
                str(report.get("barangay") or ""),
                str(report.get("municipality") or ""),
                str(report.get("province") or ""),
            ]
        ).strip().lower()
        pest_text = _normalize_text(report.get("pest_type"))

        matches_search = not search_phrase or search_phrase in location_text or search_phrase in pest_text
        matches_pest = pest_filter_value == "all" or pest_text == pest_filter_value

        if matches_search and matches_pest:
            filtered_reports.append(report)

    return filtered_reports


def limit_recent_records(reports, limit=5):
    """Return the latest records while preserving the incoming order."""
    if limit is None:
        return list(reports)

    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 5

    if limit_value <= 0:
        return []

    return list(reports[:limit_value])
