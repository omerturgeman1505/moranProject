"""Parse raw job posting text into structured, bilingual sections.

Each logical section (description, requirements, …) is identified by matching
header lines against SECTION_LABEL_VARIANTS — a comprehensive list of Hebrew
and English synonyms used on Israeli job boards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

SectionKey = Literal[
    "description",
    "requirements",
    "responsibilities",
    "qualifications",
    "benefits",
    "about_company",
    "how_to_apply",
    "additional",
]

SECTION_KEYS: dict[str, SectionKey] = {
    "DESCRIPTION": "description",
    "REQUIREMENTS": "requirements",
    "RESPONSIBILITIES": "responsibilities",
    "QUALIFICATIONS": "qualifications",
    "BENEFITS": "benefits",
    "ABOUT_COMPANY": "about_company",
    "HOW_TO_APPLY": "how_to_apply",
    "ADDITIONAL": "additional",
}

SECTION_UI_LABELS: dict[SectionKey, dict[str, str]] = {
    "description": {"he": "תיאור המשרה", "en": "Job Description"},
    "requirements": {"he": "דרישות המשרה", "en": "Requirements"},
    "responsibilities": {"he": "תחומי אחריות", "en": "Responsibilities"},
    "qualifications": {"he": "השכלה וכישורים", "en": "Qualifications"},
    "benefits": {"he": "יתרונות", "en": "Benefits"},
    "about_company": {"he": "על החברה", "en": "About the Company"},
    "how_to_apply": {"he": "הגשת מועמדות", "en": "How to Apply"},
    "additional": {"he": "מידע נוסף", "en": "Additional Information"},
}

# Every known header variant for each section — Hebrew, English, abbreviations.
SECTION_LABEL_VARIANTS: dict[SectionKey, tuple[str, ...]] = {
    "description": (
        "תיאור",
        "תיאור המשרה",
        "תיאור התפקיד",
        "תיאור משרה",
        "על התפקיד",
        "על המשרה",
        "פרטי המשרה",
        "מה עושים בתפקיד",
        "התפקיד",
        "description",
        "job description",
        "role description",
        "position description",
        "about the role",
        "about this role",
        "about the job",
        "about this job",
        "the role",
        "overview",
        "summary",
        "position overview",
        "role overview",
    ),
    "requirements": (
        "דרישות",
        "דרישות המשרה",
        "דרישות התפקיד",
        "דרישות חובה",
        "דרישות מינימום",
        "דרישות בסיס",
        "דרישות סף",
        "תנאי סף",
        "תנאים נדרשים",
        "כישורים נדרשים",
        "הכישורים הנדרשים",
        "מיומנויות נדרשות",
        "ידע נדרש",
        "השכלה נדרשת",
        "כישורים",
        "ניסיון נדרש",
        "פרופיל נדרש",
        "מה צריך",
        "מה נדרש",
        "מה דרוש",
        "מה אנחנו מחפשים",
        "מה אנחנו מחפשות",
        "requirements",
        "requirement",
        "job requirements",
        "role requirements",
        "the requirements",
        "required",
        "must have",
        "must-have",
        "must haves",
        "what you need",
        "what we need",
        "what you bring",
        "what you'll bring",
        "what you'll need",
        "what you will need",
        "what we're looking for",
        "what we are looking for",
        "who you are",
        "you have",
        "you should have",
        "you'll have",
        "you will have",
        "the ideal candidate",
        "ideal candidate",
        "your profile",
        "your background",
        "experience required",
        "requirements and qualifications",
        "requirements & qualifications",
        "skills and experience",
        "skills & experience",
        "minimum requirements",
        "essential requirements",
        "key requirements",
    ),
    "responsibilities": (
        "תחומי אחריות",
        "אחריות",
        "משימות",
        "תפקידים",
        "מה תעשו",
        "מה תעשי",
        "responsibilities",
        "key responsibilities",
        "your responsibilities",
        "what you will do",
        "what you'll do",
        "what you do",
        "duties",
        "key duties",
        "day to day",
        "day-to-day",
    ),
    "qualifications": (
        "השכלה",
        "הכשרה",
        "השכלה נדרשת",
        "כישורים מקצועיים",
        "רקע אקדמי",
        "qualifications",
        "qualification",
        "minimum qualifications",
        "preferred qualifications",
        "basic qualifications",
        "required qualifications",
        "qualifications and skills",
        "qualifications & skills",
        "education",
        "educational background",
        "academic background",
        "education and experience",
        "degree",
        "degrees",
        "certifications",
        "certification",
        "skills",
        "technical skills",
        "professional skills",
    ),
    "benefits": (
        "יתרונות",
        "יתרון",
        "מה מציעים",
        "מה אנחנו מציעים",
        "מה אנחנו מציעות",
        "הטבות",
        "תנאים",
        "תנאי העסקה",
        "תנאי שכר",
        "benefits",
        "benefit",
        "what we offer",
        "what you'll get",
        "what you will get",
        "perks",
        "compensation",
        "compensation & benefits",
        "compensation and benefits",
        "our offer",
        "why join us",
    ),
    "about_company": (
        "על החברה",
        "החברה",
        "אודות",
        "אודות החברה",
        "about us",
        "about the company",
        "about our company",
        "who we are",
        "our company",
        "company overview",
    ),
    "how_to_apply": (
        "הגשת מועמדות",
        "איך להגיש",
        "להגשת מועמדות",
        "how to apply",
        "apply",
        "application",
        "application process",
        "submit your application",
    ),
    "additional": (
        "מידע נוסף",
        "פרטים נוספים",
        "הערות",
        "additional information",
        "additional info",
        "other information",
        "notes",
        "misc",
        "general",
    ),
}

# Lines that signal "nice to have" rather than hard requirements.
ADVANTAGE_VARIANTS: tuple[str, ...] = (
    "יתרון",
    "יתרונות",
    "advantage",
    "advantages",
    "nice to have",
    "nice-to-have",
    "preferred",
    "plus",
    "bonus",
    "a plus",
    "would be a plus",
)

# Heuristic: lines containing these patterns are likely requirements when no
# explicit requirements header was found.
REQUIREMENT_LINE_PATTERNS: tuple[str, ...] = (
    r"\bb\.?\s*sc\b",
    r"\bb\.?\s*eng\b",
    r"\bbachelor",
    r"\bdegree\b",
    r"\b\d+\+?\s*years?\b",
    r"\bexperience\b",
    r"\brequired\b",
    r"\bmust\b",
    r"\bproficient\b",
    r"\bsolidworks\b",
    r"\bcad\b",
    r"\bpython\b",
    r"\bmatlab\b",
    r"תואר",
    r"ניסיון",
    r"חובה",
    r"דרוש",
    r"דרושה",
    r"נדרש",
    r"נדרשת",
)

# Language block markers (optional bilingual postings).
LANGUAGE_BLOCK_VARIANTS: dict[str, tuple[str, ...]] = {
    "en": ("english version", "english", "in english", "en version"),
    "he": ("עברית", "גרסה בעברית", "in hebrew", "hebrew version", "hebrew"),
}

DEFAULT_SECTION_ORDER: tuple[SectionKey, ...] = (
    "description",
    "responsibilities",
    "requirements",
    "qualifications",
    "benefits",
    "about_company",
    "how_to_apply",
    "additional",
)

_HEADER_PREFIX_RE = re.compile(r"^[\s#*•\-–—\d.)]+")


@dataclass
class BilingualBlock:
    he: list[str] = field(default_factory=list)
    en: list[str] = field(default_factory=list)

    def has_content(self) -> bool:
        return bool(self.he or self.en)

    def to_dict(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if self.he:
            out["he"] = self.he
        if self.en:
            out["en"] = self.en
        return out


@dataclass
class ParsedJobSummary:
    sections: dict[SectionKey, BilingualBlock] = field(default_factory=dict)

    def to_dict(self) -> dict[str, dict[str, list[str]]]:
        return {
            key: block.to_dict()
            for key, block in self.sections.items()
            if block.has_content()
        }


def normalize_header(line: str) -> str:
    """Strip markdown bullets, numbering, trailing punctuation; lowercase."""
    text = line.strip()
    text = _HEADER_PREFIX_RE.sub("", text)
    text = re.sub(r"[:：\-–—•*#]+$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _variant_lookup() -> dict[str, SectionKey]:
    lookup: dict[str, SectionKey] = {}
    for key, variants in SECTION_LABEL_VARIANTS.items():
        for variant in variants:
            lookup[normalize_header(variant)] = key
    return lookup


_VARIANT_LOOKUP = _variant_lookup()


def match_section_key(line: str) -> SectionKey | None:
    normalized = normalize_header(line)
    if not normalized:
        return None
    if normalized in _VARIANT_LOOKUP:
        return _VARIANT_LOOKUP[normalized]
    # Partial match for headers like "Requirements:" embedded in longer lines.
    for variant, key in _VARIANT_LOOKUP.items():
        if len(variant) >= 4 and (
            normalized == variant
            or normalized.startswith(variant + " ")
            or normalized.endswith(" " + variant)
        ):
            return key
    return None


def is_advantage_header(line: str) -> bool:
    normalized = normalize_header(line)
    return any(normalized == normalize_header(v) for v in ADVANTAGE_VARIANTS)


def detect_line_language(line: str) -> Literal["he", "en", "mixed"]:
    hebrew = sum(1 for ch in line if "\u0590" <= ch <= "\u05ff")
    latin = sum(1 for ch in line if ch.isascii() and ch.isalpha())
    if hebrew and not latin:
        return "he"
    if latin and not hebrew:
        return "en"
    if hebrew > latin * 2:
        return "he"
    if latin > hebrew * 2:
        return "en"
    return "mixed"


def _looks_like_requirement_line(line: str) -> bool:
    low = line.lower()
    return any(re.search(pat, low, re.IGNORECASE) for pat in REQUIREMENT_LINE_PATTERNS)


def _empty_sections() -> dict[SectionKey, BilingualBlock]:
    return {key: BilingualBlock() for key in DEFAULT_SECTION_ORDER}


def _append_line(blocks: dict[SectionKey, BilingualBlock], section: SectionKey, line: str) -> None:
    lang = detect_line_language(line)
    target = blocks[section]
    if lang == "he":
        target.he.append(line)
    elif lang == "en":
        target.en.append(line)
    else:
        # Mixed lines go to both buckets so nothing is lost in either locale view.
        target.he.append(line)
        target.en.append(line)


_COLON_RE = re.compile(r"[:：]")


def _split_inline_header(line: str) -> tuple[SectionKey, str] | None:
    """If a line is "<section header>: <content>", return (key, content).

    Only short heads count as headers, so prose lines that merely contain a
    colon ("We build X: the best") are left untouched.
    """
    match = _COLON_RE.search(line)
    if not match:
        return None
    head = line[: match.start()].strip()
    rest = line[match.end():].strip()
    if not head or len(head) > 40:
        return None
    key = match_section_key(head)
    if key is None:
        return None
    return key, rest


def parse_job_summary(text: str) -> ParsedJobSummary:
    """Split raw posting text into structured bilingual sections."""
    blocks = _empty_sections()
    current: SectionKey = "description"
    lines = [ln.strip() for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]

    for line in lines:
        # Inline "Header: content" (e.g. "Requirements: 3+ years", "דרישות: תואר")
        # — switch into the matched section and keep the trailing content instead
        # of discarding it.
        inline = _split_inline_header(line)
        if inline is not None:
            current, remainder = inline
            if remainder:
                _append_line(blocks, current, remainder)
            continue

        section_key = match_section_key(line)
        if section_key is not None:
            current = section_key
            continue
        if is_advantage_header(line):
            current = "benefits"
            continue
        _append_line(blocks, current, line)

    # If no explicit requirements header, heuristically move requirement-like
    # lines out of the description block.
    if not blocks["requirements"].has_content() and blocks["description"].has_content():
        for lang in ("he", "en"):
            src = getattr(blocks["description"], lang)
            if not src:
                continue
            kept: list[str] = []
            for line in src:
                if _looks_like_requirement_line(line):
                    getattr(blocks["requirements"], lang).append(line)
                else:
                    kept.append(line)
            setattr(blocks["description"], lang, kept)

    if not any(b.has_content() for b in blocks.values()):
        blocks["additional"].he.append("פתחי את עמוד המשרה לצפייה בדרישות המלאות.")

    return ParsedJobSummary(sections={k: v for k, v in blocks.items() if v.has_content()})


def section_display_label(key: SectionKey, locale: str = "he") -> str:
    labels = SECTION_UI_LABELS.get(key, {})
    loc = "he" if locale.startswith("he") else "en"
    return labels.get(loc) or labels.get("en") or key
