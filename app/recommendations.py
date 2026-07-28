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
    "Rhinoceros Beetle": [
        "Improve farm sanitation and remove breeding sites",
        "Install pheromone traps and green Muscardine fungus log traps",
        "Apply biological treatment or use light traps at night",
        "Monitor weekly and consult an agricultural technician for severe cases",
    ],
    "Brontispa": [
        "Prune and safely dispose of infested leaves",
        "Maintain field sanitation and monitor infestation levels",
        "Release earwigs and Tetrastichus parasitoids for natural control",
        "Spray white Muscardine fungus",
        "Use approved pesticide early morning for severe infestations",
    ],
    "Healthy Coconut Leaf": [
        "Continue regular monitoring",
        "Maintain current sanitation practices",
    ]
}


def assess_risk(pest: str, risk_score: int) -> str:
    """Assess risk level based on pest type and risk score."""
    if risk_score <= 30:
        return "Low"
    if risk_score <= 60:
        return "Medium"
    return "High"


def urgency_from_risk(risk_level: str) -> str:
    """Determine urgency level from risk."""
    if risk_level == "High":
        return "High"
    if risk_level == "Medium":
        return "Medium"
    return "Low"


def recommend_actions(pest: str, risk_score: int = 50) -> Dict[str, object]:
    """
    Generate action recommendations for a detected pest.
    
    Args:
        pest: Type of pest detected
        risk_score: Risk assessment score (0-100)
    
    Returns:
        Dictionary with recommendations and risk assessment
    """
    risk_level = assess_risk(pest, risk_score)
    urgency = urgency_from_risk(risk_level)
    
    # Get recommendations for the pest, default to empty list
    recommendations = RECOMMENDATIONS.get(pest, [])
    risk_factors = RISK_FACTORS.get(pest, [])
    
    return {
        "pest": pest,
        "risk": risk_level,
        "urgency": urgency,
        "recommendation": recommendations,
        "risk_factors": risk_factors,
    }
