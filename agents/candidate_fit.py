from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from backend.database import connect, row


FAMILY_ALIASES = {
    "marketing": ("marketing", "brand assistant", "marketing assistant", "marketing coordinator", "marketing officer"),
    "digital_marketing": ("digital marketing", "email marketing", "seo", "campaign", "marketing automation"),
    "social_media": ("social media", "community manager", "social content", "content creator"),
    "content": ("content", "copywriting", "copywriter", "editorial", "content coordinator", "content assistant"),
    "communications": ("communications", "communication officer", "communications assistant", "public relations", "pr assistant"),
    "customer_service": ("customer service", "customer support", "client service", "customer experience", "client support"),
    "sales_support": ("sales support", "sales assistant", "sales coordinator", "lead generation", "business development assistant"),
    "administration": ("administrator", "administrative assistant", "administration", "receptionist", "office assistant", "office administrator"),
    "operations": ("operations coordinator", "operations assistant", "operations support", "business operations"),
    "project_support": ("project coordinator", "project support", "project assistant", "project administrator"),
    "ecommerce": ("e-commerce", "ecommerce", "shopify", "online store"),
    "web_content": ("web content", "website content", "cms", "wordpress content", "web assistant"),
    "web_development": ("web developer", "frontend", "front-end", "react developer", "website developer"),
    "graduate": ("graduate programme", "graduate program", "graduate role", "graduate opportunity"),
    "creative_media": ("video editor", "motion designer", "graphic designer", "multimedia", "video editing"),
    "business_development": ("business development", "account development", "new business"),
}

SEARCH_TITLES = {
    "marketing": ("marketing assistant", "marketing coordinator", "junior marketing", "marketing officer"),
    "digital_marketing": ("digital marketing assistant", "digital marketing coordinator", "junior digital marketing"),
    "social_media": ("social media assistant", "social media coordinator", "junior social media"),
    "content": ("content assistant", "content coordinator", "content creator"),
    "communications": ("communications assistant", "communications coordinator"),
    "customer_service": ("customer service", "customer support", "client service"),
    "sales_support": ("sales support", "sales coordinator", "sales assistant"),
    "administration": ("administrative assistant", "administrator", "receptionist"),
    "operations": ("operations assistant", "operations coordinator"),
    "project_support": ("project assistant", "project coordinator", "project support"),
    "ecommerce": ("ecommerce assistant", "e-commerce assistant", "shopify assistant"),
    "web_content": ("web content assistant", "website content assistant"),
    "web_development": ("junior web developer", "frontend assistant", "junior frontend developer"),
    "graduate": ("marketing graduate", "graduate programme", "business graduate"),
}


def _text(value) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    return str(value or "")


def normalize(value) -> str:
    value = re.sub(r"<[^>]+>", " ", _text(value))
    value = value.replace("&amp;", " and ").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", value.lower()).strip()


def _experience_years(cv_text: str, profile: dict) -> float:
    source = cv_text + "\n" + _text(profile.get("experience", []))
    current = datetime.utcnow().year
    starts = []
    ends = []
    for start, end in re.findall(r"\b(20\d{2})\s*[-–]\s*(present|20\d{2})\b", source, flags=re.I):
        start_year = int(start)
        end_year = current if end.lower() == "present" else int(end)
        if 1990 <= start_year <= current and start_year <= end_year <= current:
            starts.append(start_year)
            ends.append(end_year)
    if not starts:
        return 0.0
    # Use elapsed career span rather than summing overlapping roles.
    return float(max(0, min(current, max(ends)) - min(starts)))


def _family_strengths(profile: dict, cv_text: str) -> dict[str, float]:
    targets = normalize(profile.get("target_roles", []))
    skills = normalize(profile.get("skills", []))
    experience = normalize(profile.get("experience", []))
    cv = normalize(cv_text)
    strengths: dict[str, float] = {}
    for family, aliases in FAMILY_ALIASES.items():
        strength = 0.0
        if any(alias in targets for alias in aliases):
            strength = 1.0
        elif any(alias in skills or alias in experience for alias in aliases):
            strength = 0.82
        elif any(alias in cv for alias in aliases):
            strength = 0.65
        # Adjacent evidence: the CV has creative tools, but that does not make
        # specialist editor/designer jobs a primary target role.
        if family == "creative_media" and any(tool in cv for tool in ("premiere pro", "photoshop", "illustrator", "capcut")):
            strength = max(strength, 0.48)
        if family == "business_development" and any(term in cv for term in ("lead generation", "sales support", "client communication")):
            strength = max(strength, 0.52)
        if strength:
            strengths[family] = strength
    return strengths


def build_candidate_fit_profile(profile: dict, cv_text: str) -> dict:
    payload = json.dumps(profile, sort_keys=True, ensure_ascii=False) + "\n" + cv_text
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    family_strengths = _family_strengths(profile, cv_text)
    skills = [normalize(item) for item in profile.get("skills", []) if normalize(item)]
    tools = [normalize(item) for item in profile.get("tools", []) if normalize(item)]
    education = [normalize(item) for item in profile.get("education", []) if normalize(item)]
    target_roles = [normalize(item) for item in profile.get("target_roles", []) if normalize(item)]
    raw = normalize(cv_text + " " + _text(profile))
    queries = []
    for role in target_roles:
        if role and role not in queries:
            queries.append(role)
    for family, strength in sorted(family_strengths.items(), key=lambda item: item[1], reverse=True):
        if strength < 0.65:
            continue
        for query in SEARCH_TITLES.get(family, ()):
            if query not in queries:
                queries.append(query)
    return {
        "fingerprint": fingerprint,
        "families": family_strengths,
        "skills": skills,
        "tools": tools,
        "education": education,
        "target_roles": target_roles,
        "experience_years": _experience_years(cv_text, profile),
        "has_drivers_licence": bool(normalize(profile.get("drivers_licence"))) or "driver's licence" in raw or "drivers licence" in raw,
        "has_own_vehicle": bool(normalize(profile.get("own_vehicle"))) or "own vehicle" in raw or "own reliable transport" in raw,
        "search_queries": queries[:30],
    }


def get_candidate_fit_profile(profile: dict, cv_text: str) -> dict:
    built = build_candidate_fit_profile(profile, cv_text)
    try:
        cached = row("SELECT value FROM settings WHERE key=?", ("candidate_fit_profile",))
        if cached:
            value = json.loads(cached["value"])
            if value.get("fingerprint") == built["fingerprint"]:
                return value
        with connect() as db:
            payload = json.dumps(built, ensure_ascii=False)
            db.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                ("candidate_fit_profile", payload),
            )
    except Exception:
        # Scoring remains available in tests/local preview even when a durable DB
        # is not configured. Production normally persists this cache in Neon.
        pass
    return built


def targeted_preferences(preferences: dict, fit: dict) -> dict:
    result = dict(preferences)
    queries = []
    for value in fit.get("search_queries", []):
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        if slug and slug not in queries:
            queries.append(slug)
    # Keep user-specified queries only when they remain close to a supported
    # family; the generated CV-derived queries take priority.
    for value in preferences.get("careers24_queries", []):
        slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
        if slug and slug not in queries:
            queries.append(slug)
    result["careers24_queries"] = queries[:24]
    return result
