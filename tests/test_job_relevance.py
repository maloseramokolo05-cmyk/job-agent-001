from agents.candidate_fit import build_candidate_fit_profile, targeted_preferences
from agents.scoring import score_job


PROFILE = {
    "education": ["Bachelor of Business Administration (BBA) in Marketing | Completed", "National Senior Certificate"],
    "skills": [
        "digital marketing", "social media management", "content planning", "campaign planning",
        "SEO fundamentals", "market research", "lead generation", "customer engagement",
        "customer support", "sales support", "administrative support", "project coordination",
        "website development", "e-commerce support",
    ],
    "tools": [
        "Canva", "CapCut", "Adobe Photoshop", "Adobe Illustrator", "Adobe Premiere Pro",
        "HubSpot", "Salesforce", "Zoho", "Microsoft Excel", "Microsoft Word", "Microsoft PowerPoint",
        "React", "TypeScript", "JavaScript", "GitHub", "Vercel", "Shopify",
    ],
    "experience": [
        "Melo Web Solutions | Freelance Web Developer & Digital Solutions | 2026 - Present",
        "The Zinhle Foundation | Social Media Manager / Marketing Support | 2025 - Present",
        "Unsponsored Souls | Marketing & Operations Support | 2023 - 2025",
    ],
    "target_roles": [
        "Marketing Assistant", "Marketing Coordinator", "Digital Marketing Assistant",
        "Social Media Assistant", "Content Coordinator", "Customer Service", "Sales Support",
        "Administrator", "Operations Coordinator", "Project Support", "E-commerce Assistant",
        "Web Content Assistant", "Graduate Programme",
    ],
    "drivers_licence": "",
    "own_vehicle": "",
    "transport": "public transportation",
    "work_preferences": ["remote", "hybrid", "on-site"],
}

CV = """
TUMELO RAMOKOLO
Marketing Graduate | Digital Marketing | Freelance Web Developer
BBA Marketing graduate with practical experience across digital marketing, social media,
customer engagement, business operations and freelance website development.
Melo Web Solutions | Freelance Web Developer & Digital Solutions | 2026 - Present
The Zinhle Foundation | Social Media Manager / Marketing Support | 2025 - Present
Unsponsored Souls | Marketing & Operations Support | 2023 - 2025
Social media management, campaign planning, content scheduling, SEO fundamentals, market research.
Canva, CapCut, Adobe Photoshop, Illustrator, Premiere Pro, HubSpot, Salesforce, Zoho.
React, TypeScript, JavaScript, Shopify operations, customer support, lead generation and project coordination.
Bachelor of Business Administration (BBA) in Marketing | Completed
"""

PREFERENCES = {
    "priority_locations": ["Pretoria", "Centurion", "Midrand", "Johannesburg", "Gauteng"],
    "job_categories": ["marketing", "digital marketing", "social media", "content", "customer service", "administration"],
    "allow_other_sa_locations": True,
    "careers24_queries": ["marketing", "administrator", "customer-service"],
}


def scored(title, description, requirements="", location="Pretoria", work_mode=""):
    return score_job(
        {"title": title, "description": description, "requirements": requirements, "location": location, "work_mode": work_mode, "salary": ""},
        PROFILE,
        PREFERENCES,
        CV,
    )


def test_candidate_fit_profile_comes_from_verified_evidence():
    fit = build_candidate_fit_profile(PROFILE, CV)
    assert fit["families"]["marketing"] >= 0.8
    assert fit["families"]["social_media"] >= 0.8
    assert fit["families"]["web_development"] >= 0.6
    assert fit["has_drivers_licence"] is False
    assert fit["has_own_vehicle"] is False
    assert fit["experience_years"] >= 3


def test_search_queries_are_generated_from_candidate_fit():
    fit = build_candidate_fit_profile(PROFILE, CV)
    prefs = targeted_preferences(PREFERENCES, fit)
    assert "marketing-assistant" in prefs["careers24_queries"]
    assert "digital-marketing-assistant" in prefs["careers24_queries"]
    assert "social-media-assistant" in prefs["careers24_queries"]


def test_marketing_social_media_assistant_is_strong_match():
    result = scored(
        "Marketing & Social Media Assistant",
        "Support social media planning, content creation, marketing administration, website updates and HubSpot.",
        "Experience supporting social media or digital marketing. Canva, CapCut and strong written communication.",
        work_mode="remote",
    )
    assert result["score"] >= 80
    assert result["classification"] in {"Strong Match", "Excellent Match"}


def test_admin_customer_support_can_be_relevant_without_being_over_scored():
    result = scored(
        "Customer Service & Administrative Assistant",
        "Handle customer enquiries, maintain records, coordinate tasks and provide administrative support.",
        "Customer support experience, Microsoft Excel and professional communication.",
    )
    assert result["score"] >= 65
    assert result["score"] < 95


def test_senior_marketing_director_is_not_recommended():
    result = scored(
        "Senior Marketing Director",
        "Lead enterprise marketing strategy, manage large teams and own executive budgets.",
        "Minimum 8 years of experience in senior marketing leadership required.",
    )
    assert result["score"] < 60


def test_accountant_with_casa_is_rejected():
    result = scored(
        "Senior Accountant",
        "Own financial reporting, audits and tax compliance.",
        "CA(SA) essential. Minimum 5 years of accounting experience required.",
    )
    assert result["score"] <= 39
    assert result["rejection_reason"]


def test_java_software_engineer_is_rejected():
    result = scored(
        "Software Engineer",
        "Develop enterprise Java backend systems and distributed services.",
        "5+ years of experience in Java engineering required.",
    )
    assert result["score"] <= 42


def test_vehicle_sales_role_with_licence_and_experience_gap_is_low():
    result = scored(
        "Pre-Owned Vehicle Sales Executive",
        "Sell pre-owned vehicles, negotiate deals and achieve dealership targets.",
        "3-5 years of experience in a similar automotive sales environment. Valid South African driver's licence required.",
    )
    assert result["score"] < 60
    assert result["mandatory_missing_requirements"]


def test_trade_marketing_role_with_own_vehicle_requirement_is_low():
    result = scored(
        "Trade Marketing Consultant",
        "Field marketing across Gauteng, secure physical branding sites and support agent growth.",
        "Own reliable vehicle essential and valid driver's licence. Proven trade marketing or field marketing experience required.",
    )
    assert result["score"] < 60


def test_motion_editor_with_five_year_requirement_is_not_excellent():
    result = scored(
        "Online Editor",
        "Edit long and short form video, colour grade footage and create motion graphics.",
        "5-7 years of experience in social editing. After Effects and Premiere Pro. Relevant tertiary education in film or media.",
        location="Johannesburg",
    )
    assert result["score"] < 60


def test_generic_sales_does_not_get_high_score_from_common_keywords():
    result = scored(
        "Sales Representative",
        "Develop customers, communicate with clients and achieve sales targets.",
        "Proven sales experience and strong communication skills.",
    )
    assert result["score"] < 80
