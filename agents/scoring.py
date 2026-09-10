from __future__ import annotations

import re
from html import unescape

from agents.candidate_fit import FAMILY_ALIASES, build_candidate_fit_profile, normalize

WEIGHTS = {
    "role_alignment": 30,
    "experience_alignment": 20,
    "skills_alignment": 15,
    "responsibilities_alignment": 10,
    "education_alignment": 10,
    "seniority_alignment": 5,
    "location_alignment": 5,
    "preference_alignment": 5,
}

STOP = {
    "and", "the", "with", "for", "from", "you", "your", "our", "this", "that", "will", "are", "job", "role",
    "have", "has", "into", "work", "working", "skills", "skill", "experience", "required", "requirements", "candidate",
    "team", "business", "company", "support", "good", "strong", "ability", "excellent", "using", "within", "across",
    "about", "their", "they", "them", "who", "what", "when", "where", "which", "more", "other", "also", "such",
    "must", "minimum", "preferred", "essential", "responsibilities", "responsibility", "including", "knowledge",
}

UNSUPPORTED_TITLE_PROFESSIONS = {
    "finance_advisory": ("financial advisor", "financial adviser", "wealth specialist", "wealth advisor", "investment advisor"),
    "accounting": ("accountant", "chartered accountant", "bookkeeper", "tax accountant", "audit manager"),
    "engineering": ("engineer", "engineering technologist", "quantity surveyor"),
    "healthcare": ("nurse", "pharmacist", "doctor", "clinical", "medical officer"),
    "trade": ("electrician", "millwright", "mechanic", "motor vehicle technician", "diesel technician", "artisan"),
    "specialist_software": ("software engineer", "backend engineer", "data scientist", "devops engineer", "java developer"),
    "legal": ("attorney", "lawyer", "legal counsel"),
}

QUALIFICATION_DOMAINS = {
    "accounting": ("accounting", "finance", "ca(sa)", "saica", "acca"),
    "engineering": ("engineering", "beng", "bsc eng"),
    "film_media": ("film", "cinematography", "broadcast", "motion design"),
    "healthcare": ("nursing", "medicine", "pharmacy"),
    "law": ("law degree", "llb"),
}

SENIORITY_ORDER = {
    "graduate": 0,
    "junior": 1,
    "assistant": 1,
    "coordinator": 2,
    "officer": 2,
    "specialist": 3,
    "mid": 3,
    "manager": 4,
    "senior": 5,
    "head": 6,
    "director": 7,
    "executive": 7,
}


def _plain(value) -> str:
    return normalize(unescape(str(value or "")))


def _terms(value) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9+#.]{3,}", _plain(value))
        if token not in STOP and not token.isdigit()
    }


def classify(score: float) -> str:
    if score >= 90:
        return "Excellent Match"
    if score >= 80:
        return "Strong Match"
    if score >= 70:
        return "Good Match"
    if score >= 60:
        return "Possible Match"
    return "Low Match"


def _job_family(title: str, body: str) -> tuple[str | None, float]:
    title_text = _plain(title)
    body_text = _plain(body)
    best_family = None
    best_confidence = 0.0
    for family, aliases in FAMILY_ALIASES.items():
        if any(alias in title_text for alias in aliases):
            confidence = 1.0
        elif any(alias in body_text[:2500] for alias in aliases):
            confidence = 0.62
        else:
            continue
        if confidence > best_confidence:
            best_family = family
            best_confidence = confidence
    return best_family, best_confidence


def _seniority(title: str) -> str:
    text = _plain(title)
    for level in ("director", "head", "senior", "manager", "specialist", "coordinator", "officer", "assistant", "junior", "graduate"):
        if re.search(rf"\b{level}\b", text):
            return level
    if "executive" in text:
        if "assistant" not in text and any(x in text for x in ("chief", "executive director", "executive manager")):
            return "executive"
    if "mid-level" in text or "mid level" in text:
        return "mid"
    return "mid"


def _required_years(text: str) -> float | None:
    plain = _plain(text)
    values: list[float] = []
    patterns = (
        r"(?:minimum(?: of)?\s*)?(\d{1,2})\s*\+?\s*(?:years|yrs)(?:['’]?)\s+(?:of\s+)?experience",
        r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:years|yrs)(?:['’]?)\s+(?:of\s+)?experience",
        r"(?:at least|minimum of)\s*(\d{1,2})\s*(?:years|yrs)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, plain):
            groups = [float(v) for v in match.groups() if v]
            if groups:
                values.append(min(groups))
    return max(values) if values else None


def _mandatory_lines(text: str) -> list[str]:
    raw = unescape(str(text or ""))
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</(?:li|p|div|ul|ol)>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    lines = []
    for item in re.split(r"[\n\r]+|[•●✓✔]", raw):
        line = re.sub(r"\s+", " ", item).strip(" -:\t")
        lower = line.lower()
        if 5 <= len(line) <= 300 and any(marker in lower for marker in ("must ", "required", "essential", "non-negotiable", "minimum", "valid driver's", "valid drivers", "own reliable", "own transport")):
            lines.append(line)
    return lines[:25]


def _specialist_title_mismatch(title: str, fit: dict) -> str | None:
    text = _plain(title)
    candidate_text = " ".join(fit.get("target_roles", []) + fit.get("skills", []))
    for domain, phrases in UNSUPPORTED_TITLE_PROFESSIONS.items():
        if any(phrase in text for phrase in phrases) and not any(phrase in candidate_text for phrase in phrases):
            return f"The vacancy is primarily a {domain.replace('_', ' ')} profession not supported by the verified CV."
    return None


def _transport_missing(mandatory: list[str], fit: dict) -> list[str]:
    missing = []
    for line in mandatory:
        lower = line.lower()
        if ("driver" in lower and "licen" in lower) and not fit.get("has_drivers_licence"):
            missing.append(line)
        if any(term in lower for term in ("own vehicle", "own reliable transport", "own transport")) and not fit.get("has_own_vehicle"):
            missing.append(line)
    return missing


def _qualification_alignment(body: str, fit: dict, mandatory: list[str]) -> tuple[float, list[str]]:
    plain = _plain(body)
    education = " ".join(fit.get("education", []))
    missing = []
    mentions_qualification = any(term in plain for term in ("degree", "diploma", "bachelor", "bba", "qualification", "matric"))
    if not mentions_qualification:
        return 1.0, missing
    if "matric" in plain or "grade 12" in plain:
        base = 1.0
    elif any(term in plain for term in ("marketing", "business", "bachelor", "degree")) and any(term in education for term in ("marketing", "business", "bachelor", "bba")):
        base = 1.0
    else:
        base = 0.75
    for _domain, markers in QUALIFICATION_DOMAINS.items():
        relevant_line = next((line for line in mandatory if any(marker in line.lower() for marker in markers)), None)
        if relevant_line and not any(marker in education for marker in markers):
            missing.append(relevant_line)
            base = min(base, 0.15)
    if "red seal" in plain and "red seal" not in education:
        missing.append("Qualified trade / Red Seal requirement is not supported by the verified CV")
        base = min(base, 0.05)
    return base, missing


def _location_alignment(job: dict, preferences: dict) -> float:
    location = _plain(job.get("location", ""))
    work_mode = _plain(job.get("work_mode", ""))
    priorities = [_plain(item) for item in preferences.get("priority_locations", [])]
    if "remote" in work_mode or ("south africa" in location and "remote" in _plain(job.get("description", ""))):
        return 1.0
    if any(priority and priority in location for priority in priorities):
        return 1.0
    if any(term in location for term in ("gauteng", "johannesburg", "sandton", "randburg", "midrand", "pretoria", "centurion")):
        return 0.85
    if preferences.get("allow_other_sa_locations") and any(term in location for term in ("south africa", "cape town", "durban", "western cape", "kwazulu", "eastern cape", "limpopo", "mpumalanga", "free state")):
        return 0.55
    return 0.25


def score_job(job: dict, profile: dict, preferences: dict, cv_text: str = "", fit_profile: dict | None = None):
    fit = fit_profile or build_candidate_fit_profile(profile, cv_text)
    title = str(job.get("title", ""))
    description = str(job.get("description", ""))
    requirements = str(job.get("requirements", ""))
    body = f"{title}\n{description}\n{requirements}"
    plain = _plain(body)
    family, family_confidence = _job_family(title, body)
    family_strength = float(fit.get("families", {}).get(family, 0.0)) if family else 0.0

    role_ratio = family_strength * family_confidence
    if family is None:
        role_ratio = 0.18
    elif family_strength == 0:
        role_ratio = 0.08

    required_years = _required_years(requirements or description)
    candidate_years = float(fit.get("experience_years") or 0)
    if required_years is None:
        experience_ratio = 0.9 if role_ratio >= 0.65 else 0.55 if role_ratio >= 0.4 else 0.25
        year_gap = 0.0
    else:
        year_gap = max(0.0, required_years - candidate_years)
        if year_gap <= 0:
            experience_ratio = 1.0
        elif year_gap <= 1:
            experience_ratio = 0.68
        elif year_gap <= 2:
            experience_ratio = 0.38
        else:
            experience_ratio = 0.1

    candidate_phrases = list(dict.fromkeys(fit.get("skills", []) + fit.get("tools", [])))
    matched_skills = sorted({phrase for phrase in candidate_phrases if len(phrase) >= 3 and phrase in plain})
    skill_phrase_ratio = min(1.0, len(matched_skills) / 6.0)
    candidate_terms = _terms(" ".join(candidate_phrases))
    job_terms = _terms(requirements or description)
    token_overlap = len(candidate_terms & job_terms)
    token_ratio = min(1.0, token_overlap / 18.0)
    skills_ratio = min(1.0, skill_phrase_ratio * 0.75 + token_ratio * 0.25)

    cv_terms = _terms(cv_text)
    high_signal_overlap = len((cv_terms & job_terms) - {"marketing", "customer", "communication", "management"})
    responsibility_ratio = min(1.0, (role_ratio * 0.65) + min(1.0, high_signal_overlap / 24.0) * 0.35)

    mandatory = _mandatory_lines(requirements or description)
    education_ratio, qualification_missing = _qualification_alignment(body, fit, mandatory)
    transport_missing = _transport_missing(mandatory, fit)

    seniority = _seniority(title)
    seniority_rank = SENIORITY_ORDER[seniority]
    if seniority_rank <= 2:
        seniority_ratio = 1.0
    elif seniority == "specialist":
        seniority_ratio = 0.75 if role_ratio >= 0.7 else 0.45
    elif seniority == "mid":
        seniority_ratio = 0.8 if role_ratio >= 0.65 else 0.5
    elif seniority == "manager":
        seniority_ratio = 0.55 if role_ratio >= 0.8 and candidate_years >= 3 else 0.25
    elif seniority == "senior":
        seniority_ratio = 0.25
    else:
        seniority_ratio = 0.05

    location_ratio = _location_alignment(job, preferences)
    work_mode = _plain(job.get("work_mode", ""))
    preferred_modes = {_plain(item) for item in profile.get("work_preferences", [])}
    preference_ratio = 1.0 if not work_mode or not preferred_modes or any(mode in work_mode for mode in preferred_modes) else 0.65

    ratios = {
        "role_alignment": role_ratio,
        "experience_alignment": experience_ratio,
        "skills_alignment": skills_ratio,
        "responsibilities_alignment": responsibility_ratio,
        "education_alignment": education_ratio,
        "seniority_alignment": seniority_ratio,
        "location_alignment": location_ratio,
        "preference_alignment": preference_ratio,
    }
    numeric_breakdown = {key: round(max(0.0, min(1.0, ratios[key])) * weight, 1) for key, weight in WEIGHTS.items()}
    total = round(sum(numeric_breakdown.values()), 1)

    mandatory_missing = list(dict.fromkeys(transport_missing + qualification_missing))
    rejection_reasons: list[str] = []
    specialist_mismatch = _specialist_title_mismatch(title, fit)
    if specialist_mismatch:
        rejection_reasons.append(specialist_mismatch)
        total = min(total, 25.0)
    if family and family_strength == 0:
        rejection_reasons.append(f"The job's primary role family ({family.replace('_', ' ')}) is not supported by the verified CV.")
        total = min(total, 45.0)
    if transport_missing:
        rejection_reasons.append("A mandatory driver's licence/own-transport requirement is not supported by the verified candidate profile.")
        total = min(total, 49.0)
    if qualification_missing:
        rejection_reasons.append("A mandatory specialist qualification is not supported by the verified CV.")
        total = min(total, 39.0)
    if required_years is not None and year_gap >= 3:
        mandatory_missing.append(f"Vacancy requires about {required_years:g}+ years of relevant experience; verified CV supports about {candidate_years:g} years overall.")
        rejection_reasons.append("Required experience is materially above the verified career span.")
        total = min(total, 42.0)
    elif required_years is not None and year_gap >= 2:
        mandatory_missing.append(f"Vacancy requires about {required_years:g}+ years of relevant experience; verified CV supports about {candidate_years:g} years overall.")
        total = min(total, 55.0)
    if seniority in {"director", "head", "executive"}:
        rejection_reasons.append("Vacancy seniority is far above the verified CV.")
        total = min(total, 30.0)
    elif seniority == "senior" and candidate_years < 5:
        rejection_reasons.append("Senior-level title is above the verified career span.")
        total = min(total, 55.0)
    elif seniority == "manager" and role_ratio < 0.75:
        total = min(total, 58.0)

    candidate_evidence = _plain(cv_text + " " + " ".join(candidate_phrases) + " " + " ".join(fit.get("education", [])))
    for line in mandatory:
        lower = line.lower()
        if "essential" not in lower and "non-negotiable" not in lower:
            continue
        line_terms = _terms(line)
        evidence_terms = _terms(candidate_evidence)
        niche = [term for term in line_terms - evidence_terms if len(term) >= 5]
        if len(niche) >= 2 and not any(skill in lower for skill in matched_skills):
            mandatory_missing.append(line)
            total = min(total, 49.0)
            if "Essential requirement is not evidenced by the verified CV." not in rejection_reasons:
                rejection_reasons.append("Essential requirement is not evidenced by the verified CV.")

    total = round(max(0.0, total), 1)
    classification = classify(total)
    fit_reason = (
        f"Role family: {family.replace('_', ' ') if family else 'unclear'}; "
        f"verified family strength {round(family_strength * 100)}%; "
        f"matched evidence: {', '.join(matched_skills[:6]) if matched_skills else 'limited direct skill evidence'}."
    )
    reasoning = (" ".join(rejection_reasons) + " " + fit_reason).strip() if rejection_reasons else fit_reason
    missing = list(dict.fromkeys(mandatory_missing))[:12]
    evidence = {
        "job_family": family,
        "family_strength": round(family_strength, 3),
        "required_years": required_years,
        "candidate_years": candidate_years,
        "seniority": seniority,
        "matched_skills": matched_skills[:12],
        "mandatory_missing": missing,
        "rejection_reasons": rejection_reasons,
    }
    return {
        "score": total,
        "classification": classification,
        "breakdown": numeric_breakdown,
        "evidence": evidence,
        "matched_skills": matched_skills[:12],
        "mandatory_missing_requirements": missing,
        "missing_requirements": missing,
        "fit_reason": fit_reason,
        "rejection_reason": " ".join(rejection_reasons),
        "reasoning": reasoning,
    }
