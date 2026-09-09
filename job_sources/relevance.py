from __future__ import annotations

import re


SOUTH_AFRICA_TERMS = {
    "south africa",
    "gauteng",
    "pretoria",
    "centurion",
    "midrand",
    "johannesburg",
    "sandton",
    "randburg",
    "roodepoort",
    "cape town",
    "durban",
    "kwazulu natal",
    "western cape",
    "eastern cape",
    "free state",
    "limpopo",
    "mpumalanga",
    "north west",
    "northern cape",
}


def south_africa_relevant(location: str, body: str = "") -> bool:
    """Keep roles explicitly located in, or remotely open to, South Africa."""
    location_text = re.sub(r"\s+", " ", (location or "").lower())
    body_text = re.sub(r"\s+", " ", (body or "").lower())
    if any(term in location_text for term in SOUTH_AFRICA_TERMS):
        return True
    remote = any(term in location_text for term in ("remote", "worldwide", "anywhere"))
    return remote and ("south africa" in body_text or "africa timezone" in body_text)


def board_company_name(token: str) -> str:
    words = token.replace("-", " ").split()
    return " ".join(word.upper() if len(word) <= 3 else word.title() for word in words)
