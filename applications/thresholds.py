from __future__ import annotations

from backend.config import load_preferences

SAFE_EMAIL_MINIMUM_SCORE = 80.0
SAFE_AUTO_PREPARE_MINIMUM_SCORE = 80.0


def effective_email_threshold(preferences: dict | None = None) -> float:
    values = preferences or load_preferences()
    return max(SAFE_EMAIL_MINIMUM_SCORE, float(values.get("email_minimum_score", SAFE_EMAIL_MINIMUM_SCORE) or SAFE_EMAIL_MINIMUM_SCORE))


def effective_auto_prepare_threshold(preferences: dict | None = None) -> float:
    values = preferences or load_preferences()
    configured = values.get("auto_prepare_score", SAFE_AUTO_PREPARE_MINIMUM_SCORE)
    return max(SAFE_AUTO_PREPARE_MINIMUM_SCORE, float(configured or SAFE_AUTO_PREPARE_MINIMUM_SCORE))
