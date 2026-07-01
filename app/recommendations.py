"""
Recommendation engine for pest management actions based on pest type, severity, and risk assessment.
"""

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
    "Healthy Coconut Leaf": []
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
    "Healthy Coconut Leaf": {
        "Mild": ["Continue regular monitoring", "Maintain current sanitation practices"],
        "Moderate": ["Continue regular monitoring", "Maintain current sanitation practices"],
        "Severe": ["Continue regular monitoring", "Maintain current sanitation practices"],
    }
}


def assess_risk(pest: str, risk_score: int) -> str:
    """Assess risk level based on pest type and risk score."""
    if risk_score <= 30:
        return "Low"
    if risk_score <= 60:
        return "Medium"
    return "High"


def urgency_from_risk(risk_level: str, severity: str) -> str:
    """Determine urgency level from risk and severity."""
    if risk_level == "High" or severity == "Severe":
        return "High"
    if severity == "Moderate":
        return "Medium"
    return "Low"


def recommend_actions(pest: str, severity: str, risk_score: int = 50) -> Dict[str, object]:
    """
    Generate action recommendations for a detected pest.
    
    Args:
        pest: Type of pest detected
        severity: Severity level (Mild, Moderate, Severe)
        risk_score: Risk assessment score (0-100)
    
    Returns:
        Dictionary with recommendations and risk assessment
    """
    risk_level = assess_risk(pest, risk_score)
    urgency = urgency_from_risk(risk_level, severity)
    
    # Get recommendations for the pest and severity, default to empty list
    recommendations = RECOMMENDATIONS.get(pest, {}).get(severity, [])
    risk_factors = RISK_FACTORS.get(pest, [])
    
    return {
        "pest": pest,
        "severity": severity,
        "risk": risk_level,
        "urgency": urgency,
        "recommendation": recommendations,
        "risk_factors": risk_factors,
    }
