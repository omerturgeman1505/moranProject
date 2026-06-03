"""Cross-reference job requirements against Moran's profile.

Detects:
  * Required years of experience (max across English + Hebrew patterns).
  * Required academic degree fields.

Then classifies each posting as 'fit' / 'review' / 'no_fit' for Moran, who has
~2 years of experience and a B.Sc. in Medical/Biomedical Engineering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Moran's profile
# ---------------------------------------------------------------------------

MORAN_YEARS = 2                         # years of professional experience
MAX_ALLOWED_YEARS = 3                   # hard cap: publish only 0-3 years
# Fields whose degree counts as a match for Moran's background.
MORAN_FRIENDLY_FIELDS = {
    "biomedical engineering", "medical engineering", "bioengineering",
    "mechanical engineering", "mechatronics", "materials engineering",
    "materials science", "chemical engineering", "industrial engineering",
    "הנדסה רפואית", "הנדסה ביו-רפואית", "הנדסה ביורפואית",
    "הנדסה ביו רפואית", "הנדסת מכונות", "הנדסת חומרים", "הנדסה כימית",
    "הנדסת תעשייה", "הנדסת תעשייה וניהול", "מכטרוניקה",
}
# Fields whose degree, if required alone, mismatches Moran's background.
MISMATCH_FIELDS = {
    "computer science", "software engineering", "computer engineering",
    "electrical engineering", "electronics engineering", "aeronautical engineering",
    "aerospace engineering",
    "מדעי המחשב", "הנדסת תוכנה", "הנדסת חשמל", "הנדסת אלקטרוניקה",
    "הנדסת מחשבים", "חשמל ואלקטרוניקה", "חשמל ומחשבים", "אוירונאוטיקה",
    "אווירונאוטיקה",
}

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Order matters: longer/more-specific phrases first to avoid partial matches.
_FIELD_VARIANTS: list[tuple[str, str]] = [
    # English — biomedical / medical
    ("biomedical engineering", "biomedical engineering"),
    ("bio-medical engineering", "biomedical engineering"),
    ("bio medical engineering", "biomedical engineering"),
    ("medical engineering", "medical engineering"),
    ("bioengineering", "bioengineering"),
    ("biomedical", "biomedical engineering"),
    # English — mechanical & related
    ("mechanical engineering", "mechanical engineering"),
    ("mechatronics engineering", "mechatronics"),
    ("mechatronics", "mechatronics"),
    ("materials engineering", "materials engineering"),
    ("materials science", "materials science"),
    ("chemical engineering", "chemical engineering"),
    ("industrial engineering", "industrial engineering"),
    # English — mismatches
    ("computer science", "computer science"),
    ("software engineering", "software engineering"),
    ("computer engineering", "computer engineering"),
    ("electrical engineering", "electrical engineering"),
    ("electronics engineering", "electronics engineering"),
    ("aeronautical engineering", "aeronautical engineering"),
    ("aerospace engineering", "aerospace engineering"),
    # Hebrew — biomedical / medical
    ("הנדסה ביו-רפואית", "הנדסה ביו-רפואית"),
    ("הנדסה ביורפואית", "הנדסה ביורפואית"),
    ("הנדסה ביו רפואית", "הנדסה ביו רפואית"),
    ("הנדסה רפואית", "הנדסה רפואית"),
    # Hebrew — mechanical & related
    ("הנדסת מכונות", "הנדסת מכונות"),
    ("הנדסת חומרים", "הנדסת חומרים"),
    ("הנדסה כימית", "הנדסה כימית"),
    ("הנדסת תעשייה וניהול", "הנדסת תעשייה וניהול"),
    ("הנדסת תעשייה", "הנדסת תעשייה"),
    ("מכטרוניקה", "מכטרוניקה"),
    # Hebrew — mismatches
    ("מדעי המחשב", "מדעי המחשב"),
    ("הנדסת תוכנה", "הנדסת תוכנה"),
    ("הנדסת חשמל", "הנדסת חשמל"),
    ("הנדסת אלקטרוניקה", "הנדסת אלקטרוניקה"),
    ("הנדסת מחשבים", "הנדסת מחשבים"),
    ("חשמל ואלקטרוניקה", "חשמל ואלקטרוניקה"),
    ("חשמל ומחשבים", "חשמל ומחשבים"),
    ("אוירונאוטיקה", "אוירונאוטיקה"),
    ("אווירונאוטיקה", "אווירונאוטיקה"),
]

# Master's degree indicators (English + Hebrew). Strict: require the degree
# token to read like an academic qualification, not a recruiter's title nor a
# US state code (e.g. "MA, USA").
_MASTER_PATTERNS = [
    re.compile(r"\bm\.?\s*sc\b\.?", re.IGNORECASE),
    re.compile(r"\bm\.?\s*eng\b\.?", re.IGNORECASE),
    re.compile(r"\bmaster'?s?\b(?=\s+(?:degree|of|in)\b)", re.IGNORECASE),
    re.compile(r"\bgraduate\s+degree\b", re.IGNORECASE),
    re.compile(r"\bpost[- ]graduate\b", re.IGNORECASE),
    re.compile(r"תואר\s+שני"),
    re.compile(r"\bמאסטר\b"),
]

# Disqualifiers that mean a Master mention is NOT a job requirement:
# recruiter signatures, location strings, "advantage" framing, etc.
_MASTER_ADVANTAGE_CUES = [
    "advantage", "advantages", "nice to have", "nice-to-have", "preferred",
    "preference", "a plus", "plus", "bonus", "would be a plus", "is a plus",
    "optional", "desirable", "preferred but not required",
    "יתרון", "יתרונות", "רצוי", "מהווה יתרון", "תהווה יתרון",
]

# Phrases around a Master mention that mean it's not a requirement (recruiter
# name/title context, or US state-style locations like "Master, MA, USA").
_MASTER_NON_REQUIREMENT_CUES = [
    "talent acquisition", "recruiter", "recruitment", "organizational behavior",
    "organizational consulting", "human resources", "people partner",
    "career growth", "ma, usa", "ma usa", ", ma ",
]


# Capture max years from a variety of phrasings.
_YEARS_PATTERNS = [
    # English
    re.compile(r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*\+?\s*years?\b", re.IGNORECASE),
    re.compile(r"\bat\s+least\s+(\d{1,2})\s+years?\b", re.IGNORECASE),
    re.compile(r"\b(?:a\s+)?minimum\s+(?:of\s+)?(\d{1,2})\s+years?\b", re.IGNORECASE),
    re.compile(r"\bmin\.?\s*(\d{1,2})\s+years?\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*\+\s*years?\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s+years?\s+(?:of\s+)?experience\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s+years?\s+\w{0,30}\s*experience\b", re.IGNORECASE),
    re.compile(r"\bexperience\s+of\s+(\d{1,2})\s+years?\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s+years?\s+(?:required|needed|exp\.?)\b", re.IGNORECASE),
    re.compile(r"\b(?:more\s+than|over)\s+(\d{1,2})\s+years?\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s+years?\s+or\s+more\b", re.IGNORECASE),
    # Hebrew
    re.compile(r"לפחות\s+(\d{1,2})\s+שנ"),
    re.compile(r"מינימום\s+(\d{1,2})\s+שנ"),
    re.compile(r"מעל\s+(\d{1,2})\s+שנ"),
    re.compile(r"(\d{1,2})\s*\+\s*שנ"),
    re.compile(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+שנ"),
    re.compile(r"(\d{1,2})\s+שנות\s+ניסיון"),
    re.compile(r"ניסיון\s+של\s+(\d{1,2})\s+שנ"),
    re.compile(r"(\d{1,2})\s+שנ(?:ות|ים)?\s+ומעלה"),
]

_HEBREW_NUMBER_WORDS = {
    "שנה": 1,
    "שנתיים": 2,
    "שתיים": 2,
    "שתי": 2,
    "שלוש": 3,
    "שלושה": 3,
    "ארבע": 4,
    "ארבעה": 4,
    "חמש": 5,
    "חמישה": 5,
    "שש": 6,
    "שישה": 6,
    "שבע": 7,
    "שבעה": 7,
    "שמונה": 8,
    "תשע": 9,
    "תשעה": 9,
    "עשר": 10,
    "עשרה": 10,
}
_HEBREW_WORD_YEARS_RE = re.compile(
    r"(?:(?:לפחות|מעל)\s+)?("
    + "|".join(re.escape(word) for word in sorted(_HEBREW_NUMBER_WORDS, key=len, reverse=True))
    + r")\s+שנ(?:ות|ים|ת)?\s+ניסיון"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FitAssessment:
    years_required: int | None        # max years asked for; None if unstated
    degree_fields: list[str]          # detected field names (deduplicated)
    fit_category: str                 # 'fit' | 'review' | 'no_fit'
    reason: str                       # human-readable explanation
    requires_master: bool = False     # M.Sc./Master required (not just 'an advantage')


def requires_master_degree(text: str) -> bool:
    """True only when a Master's is *required* — phrases tagged as advantage,
    preferred, "or B.Sc.", etc. don't count.
    """
    if not text:
        return False
    low = text.lower()
    for pat in _MASTER_PATTERNS:
        for match in pat.finditer(text if not pat.pattern.startswith("\\b") else low):
            start, end = match.span()
            # ±90 chars context window, lowercased for cue matching.
            window = (text[max(0, start - 90):min(len(text), end + 90)]).lower()
            if any(cue in window for cue in _MASTER_ADVANTAGE_CUES):
                continue
            if any(cue in window for cue in _MASTER_NON_REQUIREMENT_CUES):
                continue
            # "B.Sc., M.Sc., or PhD" / "B.Sc. or M.Sc." → B.Sc. acceptable.
            # [\s\S] (not .) so newline-separated bullets ("Bachelor\nOR\nMaster")
            # still bridge correctly.
            bachelor = r"(?:b\.?\s*sc|b\.?\s*eng|b\.?\s*a|bachelor)"
            master = r"(?:m\.?\s*sc|m\.?\s*eng|master'?s?)"
            if re.search(rf"\b{bachelor}\b[\s\S]{{0,60}}?(?:\bor\b|/)", window):
                continue
            if re.search(rf"(?:\bor\b|/)[\s\S]{{0,60}}?\b{master}\b", window):
                continue
            if re.search(rf"\b{master}\b[\s\S]{{0,60}}?(?:\bor\b|/)[\s\S]{{0,60}}?\b{bachelor}\b", window):
                continue
            # Hebrew "תואר ראשון או שני" / "תואר ראשון או תואר שני".
            if "תואר ראשון או" in window:
                continue
            return True
    return False


def parse_years_required(text: str) -> int | None:
    if not text:
        return None
    found: list[int] = []
    for pat in _YEARS_PATTERNS:
        for match in pat.finditer(text):
            for grp in match.groups():
                if grp and grp.isdigit():
                    n = int(grp)
                    if 0 < n <= 25:    # ignore noise like "100 years"
                        found.append(n)
    for match in _HEBREW_WORD_YEARS_RE.finditer(text):
        found.append(_HEBREW_NUMBER_WORDS[match.group(1)])
    return max(found) if found else None


def parse_degree_fields(text: str) -> list[str]:
    if not text:
        return []
    low = text.lower()
    found: list[str] = []
    for variant, canonical in _FIELD_VARIANTS:
        if variant.isascii():
            if re.search(rf"\b{re.escape(variant)}\b", low):
                if canonical not in found:
                    found.append(canonical)
        elif variant in text:
            if canonical not in found:
                found.append(canonical)
    return found


def classify_degree(fields: list[str]) -> str:
    """Returns 'match' / 'mismatch' / 'unknown'."""
    if not fields:
        return "unknown"
    friendly = [f for f in fields if f in MORAN_FRIENDLY_FIELDS]
    mismatched = [f for f in fields if f in MISMATCH_FIELDS]
    if friendly:
        return "match"
    if mismatched and not friendly:
        return "mismatch"
    return "unknown"


def evaluate_fit(text: str) -> FitAssessment:
    years = parse_years_required(text)
    fields = parse_degree_fields(text)
    degree = classify_degree(fields)
    master = requires_master_degree(text)

    # M.Sc./Master is a hard exclusion — the job is removed from the system.
    if master:
        return FitAssessment(
            years_required=years,
            degree_fields=fields,
            fit_category="no_fit",
            reason="הדרישה היא לתואר שני (M.Sc/Master) — לא מתאים למורן",
            requires_master=True,
        )

    # Degree mismatch overrides everything — wrong field is a hard no.
    if degree == "mismatch":
        return FitAssessment(
            years_required=years,
            degree_fields=fields,
            fit_category="no_fit",
            reason="הדרישה היא לתואר בתחום שאינו הנדסה רפואית/מכונות",
        )

    # Heavy experience requirement.
    if years is not None and years > MAX_ALLOWED_YEARS:
        return FitAssessment(
            years_required=years,
            degree_fields=fields,
            fit_category="no_fit",
            reason=f"נדרשות {years} שנות ניסיון",
        )

    # Borderline: 3 years (Moran has 2, often companies are flexible).
    if years is not None and years == MAX_ALLOWED_YEARS:
        return FitAssessment(
            years_required=years,
            degree_fields=fields,
            fit_category="review",
            reason=f"נדרשות {years} שנות ניסיון (גבולי)",
        )

    # No specific field stated but heavy years still ok — Moran fits.
    return FitAssessment(
        years_required=years,
        degree_fields=fields,
        fit_category="fit",
        reason=(
            "תאם פרופיל" if degree == "match"
            else "ללא מגבלת תואר/ניסיון חוסמת"
        ),
    )
