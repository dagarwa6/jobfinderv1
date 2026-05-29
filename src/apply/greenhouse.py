"""Greenhouse ATS form field mapping.

Maps standard Greenhouse form field names to applicant profile values.
Greenhouse uses predictable field names (first_name, last_name, email, phone)
plus numbered custom questions (question_NNNN) whose labels vary per company.
"""
from __future__ import annotations

import re

# Standard Greenhouse field name → profile path
STANDARD_FIELDS = {
    "first_name": ("personal", "first_name"),
    "last_name": ("personal", "last_name"),
    "preferred_name": ("personal", "preferred_name"),
    "email": ("personal", "email"),
    "phone": ("personal", "phone"),
}

# Label substring → profile path for custom text questions
LABEL_TO_PROFILE = [
    ("linkedin", ("links", "linkedin")),
    ("website", ("links", "website")),
    ("github", ("links", "github")),
    ("portfolio", ("links", "portfolio")),
]

# Label patterns → answer for custom questions
LABEL_TO_ANSWER = [
    (r"how did you hear about .*(this job|this position|this role)", ("standard_answers", "how_hear_about_job")),
    (r"how did you hear about", ("standard_answers", "how_hear_about_job")),
]

# Select-type questions: label pattern → preferred option text
SELECT_PATTERNS = [
    (r"gender", "I don't wish to answer"),
    (r"race|ethnicity", "I don't wish to answer"),
    (r"veteran", "No, I am not a protected veteran"),
    (r"disability", "I don't wish to answer"),
    (r"how did you hear about this job", "Company Website"),
]

# Sponsorship / work auth patterns
SPONSORSHIP_PATTERNS = [
    (r"(require|need).*(sponsor|visa)", "No"),
    (r"lawfully authorized|authorized to work|eligible to work", "Yes"),
    (r"able to meet this requirement", "Yes"),
]


def resolve_value(profile: dict, path: tuple[str, ...]) -> str:
    """Walk a (section, key) path in the profile dict."""
    obj = profile
    for k in path:
        obj = obj.get(k, "")
        if not obj:
            return ""
    return str(obj)


def map_standard_field(field_name: str, profile: dict) -> str | None:
    """Return profile value for a known Greenhouse field name, or None."""
    path = STANDARD_FIELDS.get(field_name)
    if path:
        return resolve_value(profile, path)
    return None


def map_custom_text(label: str, profile: dict) -> str | None:
    """Try to match a custom question label to a profile value."""
    label_lower = label.lower()

    for substr, path in LABEL_TO_PROFILE:
        if substr in label_lower:
            return resolve_value(profile, path)

    for pattern, path in LABEL_TO_ANSWER:
        if re.search(pattern, label_lower):
            return resolve_value(profile, path)

    for pattern, answer in SPONSORSHIP_PATTERNS:
        if re.search(pattern, label_lower):
            return answer

    return None


def best_select_option(label: str, options: list[str]) -> str | None:
    """Pick the best option for a select dropdown based on question label."""
    label_lower = label.lower()

    for pattern, preferred in SELECT_PATTERNS:
        if re.search(pattern, label_lower):
            for opt in options:
                if preferred.lower() in opt.lower():
                    return opt
            return None

    for pattern, answer in SPONSORSHIP_PATTERNS:
        if re.search(pattern, label_lower):
            for opt in options:
                if answer.lower() in opt.lower():
                    return opt
            return None

    return None
