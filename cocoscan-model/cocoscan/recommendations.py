from typing import Dict, List

RISK_FACTORS = {
    "Rhinoceros Beetle": [
        "Poor farm sanitation",
        "Decaying logs",
        "Breeding sites",
        "Warm night temperatures",
        "Strong wind",
        "Previous infestation",
    ],
    "Brontispa": [
        "Nursery area",
        "Dense vegetation",
        "Shaded environment",
        "Poor sanitation",
        "Previous infestation",
    ],
}

RECOMMENDATIONS = {
    "Rhinoceros Beetle": {
        "Mild": [
            "Improve farm sanitation",
            "Remove breeding sites",
            "Install pheromone traps",
            "Monitor weekly",
        ],
        "Moderate": [
            "Improve farm sanitation",
            "Install pheromone traps",
            "Use green Muscardine fungus log traps",
            "Apply biological treatment",
            "Use light traps at night",
        ],
        "Severe": [
            "Perform immediate intervention",
            "Increase trap density",
            "Apply biological control",
            "Remove infested breeding materials",
            "Consult an agricultural technician",
        ],
    },
    "Brontispa": {
        "Mild": [
            "Prune affected leaves",
            "Monitor infestation levels",
            "Maintain field sanitation",
        ],
        "Moderate": [
            "Prune damaged leaves",
            "Release earwigs for natural control",
            "Release Tetrastichus parasitoids",
            "Spray white Muscardine fungus",
        ],
        "Severe": [
            "Prune heavily infested leaves",
            "Apply biological control",
            "Use approved pesticide early morning",
            "Quarantine nursery area if necessary",
        ],
    },
}


def assess_risk(pest: str, risk_score: int) -> str:
    if risk_score <= 30:
        return "Low"
    if risk_score <= 60:
        return "Medium"
    return "High"


def urgency_from_risk(risk_level: str, severity: str) -> str:
    if risk_level == "High" or severity == "Severe":
        return "High"
    if severity == "Moderate":
        return "Medium"
    return "Low"


def recommend_actions(pest: str, severity: str, risk_score: int) -> Dict[str, object]:
    risk_level = assess_risk(pest, risk_score)
    urgency = urgency_from_risk(risk_level, severity)
    recommendations = RECOMMENDATIONS.get(pest, {}).get(severity, [])
    return {
        "pest": pest,
        "severity": severity,
        "risk": risk_level,
        "urgency": urgency,
        "recommendation": recommendations,
        "risk_factors": RISK_FACTORS.get(pest, []),
    }
